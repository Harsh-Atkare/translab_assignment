import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.logging_setup import new_request_id, request_id_ctx, setup_logging
from app.routes import chat, documents, health

cfg = get_settings()
setup_logging(cfg.log_level, cfg.log_json)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    Path(cfg.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(cfg.chroma_dir).mkdir(parents=True, exist_ok=True)

    log.info(
        "starting up",
        extra={"ctx_env": cfg.app_env, "ctx_model": cfg.chat_model},
    )

    if not cfg.gemini_api_key:

        log.warning("GEMINI_API_KEY is not set; uploads and questions will fail")

    yield
    log.info("shutting down")


app = FastAPI(
    title="Enterprise AI Knowledge Assistant",
    description="Upload PDFs, ask questions, get answers with page citations.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_context(request: Request, call_next):

    rid = request.headers.get("X-Request-ID") or new_request_id()
    token = request_id_ctx.set(rid)

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_ctx.reset(token)


Instrumentator(excluded_handlers=["/metrics", "/healthz", "/readyz"]).instrument(
    app
).expose(app, endpoint="/metrics", include_in_schema=False)

app.include_router(health.router)
app.include_router(documents.router)
app.include_router(chat.router)

ROOT = Path(__file__).resolve().parent.parent


def ui_dir() -> Path | None:
    for candidate in (ROOT / "frontend_dist", ROOT / "frontend" / "dist"):
        if (candidate / "index.html").is_file():
            return candidate
    return None


_ui = ui_dir()

if _ui:
    app.mount("/assets", StaticFiles(directory=_ui / "assets"), name="assets")
else:

    log.warning("no frontend build found - run `make ui` (the API still works)")


@app.get("/", include_in_schema=False)
def index():
    current = ui_dir()

    if current is None:
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Frontend not built. Run `make ui`, or use the API "
                "directly at /docs."
            },
        )

    return FileResponse(current / "index.html")

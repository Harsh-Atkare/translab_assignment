from fastapi import APIRouter

from app.config import get_settings
from app.rag import store

router = APIRouter(tags=["health"])


@router.get("/healthz")
def liveness():
    """Liveness probe. Deliberately does no I/O.

    If this touched Chroma or Gemini, a slow dependency would get the pod
    killed and restarted in a loop, which makes an outage worse.
    """
    return {"status": "ok"}


@router.get("/readyz")
def readiness():
    """Readiness probe. This one is allowed to check dependencies."""
    cfg = get_settings()
    checks = {"vector_store": False, "api_key": bool(cfg.gemini_api_key)}
    detail = None

    try:
        store.count()
        checks["vector_store"] = True
    except store.EmbeddingMismatch as exc:
        detail = str(exc)
    except Exception as exc:
        detail = str(exc)

    ready = all(checks.values())
    body = {"status": "ready" if ready else "degraded", "checks": checks}

    if detail:
        body["detail"] = detail

    return body


@router.get("/api/info")
def info():
    cfg = get_settings()
    return {
        "env": cfg.app_env,
        "chat_model": cfg.chat_model,
        "embed_model": cfg.embed_model,
        "embed_dim": cfg.embed_dim,
        "chunk_size": cfg.chunk_size,
        "chunk_overlap": cfg.chunk_overlap,
        "top_k": cfg.top_k,
        "thinking_budget": "auto" if cfg.thinking_budget is None else cfg.thinking_budget,
        "max_output_tokens": cfg.max_output_tokens,
        "request_timeout": cfg.request_timeout,
        "embed_concurrency": cfg.embed_concurrency,
        "api_key_set": bool(cfg.gemini_api_key),
        "documents": len(store.list_documents()),
        "chunks": store.count(),
    }

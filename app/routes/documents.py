import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.metrics import DOCUMENTS_TOTAL, ERRORS
from app.rag import pipeline, store
from app.rag.gemini import friendly_error, is_upstream

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", status_code=201)
async def upload(file: UploadFile = File(...)):
    cfg = get_settings()

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    body = await file.read()

    if not body:
        raise HTTPException(400, "That file is empty.")

    if len(body) > cfg.max_upload_bytes:
        raise HTTPException(
            413, f"File is larger than the {cfg.max_upload_mb} MB limit."
        )

    try:
        result = pipeline.ingest(body, file.filename)
    except ValueError as exc:
    
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        ERRORS.labels(stage="ingest").inc()

        if is_upstream(exc):
            log.warning(
                "ingest failed for %s: %s",
                file.filename,
                str(exc).split("{")[0].strip(),
            )
        else:
            log.exception("ingest failed for %s", file.filename)

        raise HTTPException(502, friendly_error(exc)) from exc

    DOCUMENTS_TOTAL.set(len(store.list_documents()))
    return result


@router.get("")
def list_all():
    docs = store.list_documents()
    DOCUMENTS_TOTAL.set(len(docs))
    return {"documents": docs, "total_chunks": store.count()}


@router.delete("/{doc_id}")
def remove(doc_id: str):
    removed = store.delete(doc_id)

    if removed == 0:
        raise HTTPException(404, "No document with that id.")

    DOCUMENTS_TOTAL.set(len(store.list_documents()))
    return {"doc_id": doc_id, "chunks_removed": removed}

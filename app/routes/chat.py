import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.metrics import ERRORS
from app.rag import pipeline
from app.rag.gemini import friendly_error, is_upstream

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    doc_id: str | None = None 


@router.post("/ask")
def ask(payload: Question):
    try:
        return pipeline.ask(payload.question.strip(), payload.doc_id)
    except RuntimeError as exc:
       
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        ERRORS.labels(stage="query").inc()

        if is_upstream(exc):

            log.warning("question failed: %s", str(exc).split("{")[0].strip())
        else:
            log.exception("question failed")

        raise HTTPException(502, friendly_error(exc)) from exc

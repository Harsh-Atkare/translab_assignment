import logging
import time
import uuid

from app.config import get_settings
from app.metrics import CHUNKS_INDEXED, INGEST_SECONDS, QUERY_SECONDS, STAGE_SECONDS
from app.rag import gemini, store
from app.rag.pdf import chunk_pages, extract_pages

log = logging.getLogger(__name__)


def ingest(pdf_bytes: bytes, filename: str) -> dict:
    """PDF bytes in, indexed chunks out."""
    cfg = get_settings()
    started = time.perf_counter()
    doc_id = uuid.uuid4().hex[:12]

    pages = extract_pages(pdf_bytes)
    chunks = chunk_pages(pages, cfg.chunk_size, cfg.chunk_overlap)

    if not chunks:
        raise ValueError("PDF parsed but produced no usable text chunks.")

    vectors = gemini.embed([c.text for c in chunks])
    store.add(doc_id, filename, chunks, vectors)

    elapsed = time.perf_counter() - started
    INGEST_SECONDS.observe(elapsed)
    CHUNKS_INDEXED.inc(len(chunks))

    log.info(
        "indexed %s",
        filename,
        extra={"ctx_doc_id": doc_id, "ctx_chunks": len(chunks), "ctx_seconds": round(elapsed, 2)},
    )

    return {
        "doc_id": doc_id,
        "filename": filename,
        "pages": len(pages),
        "chunks": len(chunks),
        "seconds": round(elapsed, 2),
    }


def ask(question: str, doc_id: str | None = None) -> dict:
    cfg = get_settings()
    started = time.perf_counter()

    if store.count() == 0:
        return {
            "answer": "No documents have been uploaded yet. Upload a PDF first.",
            "sources": [],
            "seconds": 0.0,
        }

    t0 = time.perf_counter()
    query_vector = gemini.embed([question], is_query=True)[0]
    t_embed = time.perf_counter() - t0

    t0 = time.perf_counter()
    hits = store.search(query_vector, cfg.top_k, doc_id)
    t_search = time.perf_counter() - t0

    STAGE_SECONDS.labels(stage="embed_query").observe(t_embed)
    STAGE_SECONDS.labels(stage="vector_search").observe(t_search)

    if not hits or hits[0]["score"] < 0.25:
        return {
            "answer": (
                "I could not find anything relevant in the uploaded documents for that question."
            ),
            "sources": [],
            "seconds": round(time.perf_counter() - started, 2),
        }

    t0 = time.perf_counter()
    text = gemini.answer(question, hits)
    t_generate = time.perf_counter() - t0
    STAGE_SECONDS.labels(stage="generate").observe(t_generate)

    elapsed = time.perf_counter() - started
    QUERY_SECONDS.observe(elapsed)

    timings = {
        "embed": round(t_embed, 2),
        "search": round(t_search, 2),
        "generate": round(t_generate, 2),
    }

    log.info(
        "answered question",
        extra={
            "ctx_hits": len(hits),
            "ctx_seconds": round(elapsed, 2),
            "ctx_timings": timings,
        },
    )

    return {
        "answer": text,
        "sources": [
            {
                "page": h["page"],
                "filename": h["filename"],
                "score": h["score"],
                "excerpt": h["text"][:280] + ("..." if len(h["text"]) > 280 else ""),
            }
            for h in hits
        ],
        "seconds": round(elapsed, 2),
        "timings": timings,
    }

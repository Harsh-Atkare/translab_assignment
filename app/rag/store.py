import logging
import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

log = logging.getLogger(__name__)

_collection = None
_lock = threading.Lock()


def collection():
    """Persistent Chroma collection, created on first use.

    Chroma's client isn't thread safe to construct, and uvicorn will happily
    call this from several workers at once on the first request, hence the lock.
    """
    global _collection

    if _collection is not None:
        return _collection

    with _lock:
        if _collection is not None:
            return _collection

        cfg = get_settings()
        Path(cfg.chroma_dir).mkdir(parents=True, exist_ok=True)

        chroma = chromadb.PersistentClient(
            path=cfg.chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        _collection = chroma.get_or_create_collection(
            name=cfg.collection,
            metadata={
                "hnsw:space": "cosine",

                "embed_model": cfg.embed_model,
                "embed_dim": cfg.embed_dim,
            },
        )

        _check_fingerprint(_collection, cfg)
        log.info("chroma ready at %s (%d vectors)", cfg.chroma_dir, _collection.count())

    return _collection


class EmbeddingMismatch(RuntimeError):
    pass


def _check_fingerprint(coll, cfg) -> None:

    if coll.count() == 0:
        return 

    meta = coll.metadata or {}
    was_model = meta.get("embed_model")
    was_dim = meta.get("embed_dim")

    if was_model and was_model != cfg.embed_model:
        raise EmbeddingMismatch(
            f"This index was built with '{was_model}' but GEMINI_EMBED_MODEL is now "
            f"'{cfg.embed_model}'. The vectors are not comparable. "
            f"Delete {cfg.chroma_dir} and re-upload your documents "
            f"(or run `make reset`)."
        )

    if was_dim and int(was_dim) != cfg.embed_dim:
        raise EmbeddingMismatch(
            f"This index has {was_dim}-dimensional vectors but EMBED_DIM is "
            f"{cfg.embed_dim}. Delete {cfg.chroma_dir} and re-upload "
            f"(or run `make reset`)."
        )


def add(doc_id: str, filename: str, chunks, vectors: list[list[float]]) -> None:
    collection().add(
        ids=[f"{doc_id}:{c.index}" for c in chunks],
        embeddings=vectors,
        documents=[c.text for c in chunks],
        metadatas=[
            {"doc_id": doc_id, "filename": filename, "page": c.page} for c in chunks
        ],
    )


def search(vector: list[float], top_k: int, doc_id: str | None = None) -> list[dict]:
    where = {"doc_id": doc_id} if doc_id else None

    res = collection().query(
        query_embeddings=[vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )


    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]

    return [
        {
            "text": doc,
            "page": meta.get("page"),
            "filename": meta.get("filename"),
            "doc_id": meta.get("doc_id"),
            "score": round(1 - dist, 4), 
        }
        for doc, meta, dist in zip(docs, metas, dists, strict=True)
    ]


def list_documents() -> list[dict]:
    res = collection().get(include=["metadatas"])

    seen: dict[str, dict] = {}
    for meta in res["metadatas"]:
        doc_id = meta["doc_id"]
        entry = seen.setdefault(
            doc_id, {"doc_id": doc_id, "filename": meta["filename"], "chunks": 0}
        )
        entry["chunks"] += 1

    return sorted(seen.values(), key=lambda d: d["filename"])


def delete(doc_id: str) -> int:
    before = collection().count()
    collection().delete(where={"doc_id": doc_id})
    return before - collection().count()


def count() -> int:
    return collection().count()

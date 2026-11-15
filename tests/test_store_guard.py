import tempfile

import pytest


def test_mismatched_embedding_model_is_rejected(monkeypatch, sample_pdf):
    """Swapping GEMINI_EMBED_MODEL on an existing index must fail loudly.

    Without this guard the app keeps serving, retrieval quietly returns
    nothing useful, and there is no error anywhere to point at.
    """
    from fastapi.testclient import TestClient

    import app.config as config
    from app.main import app as fastapi_app
    from app.rag import store

    fresh_dir = tempfile.mkdtemp(prefix="chroma-guard-")
    config.get_settings.cache_clear()
    monkeypatch.setenv("CHROMA_DIR", fresh_dir)
    monkeypatch.setenv("GEMINI_EMBED_MODEL", "model-a")
    store._collection = None

    with TestClient(fastapi_app) as client:
        r = client.post(
            "/api/documents",
            files={"file": ("doc.pdf", sample_pdf, "application/pdf")},
        )
        assert r.status_code == 201
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_EMBED_MODEL", "model-b")
    store._collection = None

    with pytest.raises(store.EmbeddingMismatch, match="model-a"):
        store.count()
    config.get_settings.cache_clear()
    store._collection = None


def test_empty_index_accepts_any_model(monkeypatch):
    import app.config as config
    from app.rag import store

    config.get_settings.cache_clear()
    monkeypatch.setenv("CHROMA_DIR", tempfile.mkdtemp(prefix="chroma-empty-"))
    monkeypatch.setenv("GEMINI_EMBED_MODEL", "anything-at-all")
    store._collection = None

    assert store.count() == 0

    config.get_settings.cache_clear()
    store._collection = None

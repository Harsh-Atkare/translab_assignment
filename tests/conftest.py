import hashlib
import os
import tempfile

import pytest

os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ["CHROMA_DIR"] = tempfile.mkdtemp(prefix="chroma-test-")
os.environ["LOG_JSON"] = "false"


def _fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    return [(b - 128) / 128 for b in (digest * 24)[:768]]


@pytest.fixture(autouse=True)
def stub_gemini(monkeypatch):
    from app.rag import gemini

    monkeypatch.setattr(
        gemini, "embed", lambda texts, is_query=False: [_fake_vector(t) for t in texts]
    )
    monkeypatch.setattr(
        gemini,
        "answer",
        lambda question, passages: f"Answer from {len(passages)} passages.",
    )


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_pdf() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    for body in (
        "Employment Agreement. " + ("The notice period is ninety days. " * 30),
        "Annexure B. " + ("Annual leave is twenty four working days. " * 30),
    ):
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(40, 40, 560, 780), body, fontsize=11)

    data = doc.tobytes()
    doc.close()
    return data

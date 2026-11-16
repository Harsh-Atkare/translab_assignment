"""Regression tests for embedding batch handling.

gemini-embedding-2 reads a list of strings as one interleaved multimodal
input and returns a single vector, where gemini-embedding-001 returns one
per string. Feeding that straight into Chroma failed with
"Unequal lengths for fields: ids: 49 ... embeddings: 1".
"""

import pytest

from app.rag import gemini


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeResult:
    def __init__(self, embeddings):
        self.embeddings = embeddings


@pytest.fixture(autouse=True)
def stub_gemini():
    """Override conftest's autouse stub.

    Every other test file wants gemini.embed faked out. This file is testing
    gemini.embed itself, so it needs the real one - we fake the SDK call
    underneath it instead.
    """
    yield


@pytest.fixture(autouse=True)
def reset_batch_flag():
    gemini._batching_works = True
    yield
    gemini._batching_works = True


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda _: None)


def _install(monkeypatch, behaviour):
    """Replace the SDK call with a fake and record how it was called."""
    calls = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            calls.append(list(contents))
            return FakeResult(behaviour(list(contents)))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())
    return calls


def test_model_that_batches_uses_one_call(monkeypatch):
    calls = _install(monkeypatch, lambda c: [FakeEmbedding([0.1] * 768) for _ in c])

    vectors = gemini.embed([f"chunk {i}" for i in range(49)])

    assert len(vectors) == 49
    assert len(calls) == 1


def test_model_that_coalesces_falls_back_per_chunk(monkeypatch):
    """The actual bug: 49 inputs in, 1 vector out."""
    calls = _install(monkeypatch, lambda c: [FakeEmbedding([0.2] * 768)])

    vectors = gemini.embed([f"chunk {i}" for i in range(49)])

    assert len(vectors) == 49, "must return one vector per input"

    assert len(calls) == 50
    assert all(len(c) == 1 for c in calls[1:])


def test_fallback_is_remembered_across_calls(monkeypatch):
    calls = _install(monkeypatch, lambda c: [FakeEmbedding([0.3] * 768)])

    gemini.embed(["a", "b"])
    first_round = len(calls)
    gemini.embed(["c", "d"])

    assert len(calls) - first_round == 2


def test_empty_input_makes_no_api_call(monkeypatch):
    calls = _install(monkeypatch, lambda c: [])
    assert gemini.embed([]) == []
    assert calls == []


def test_unexpected_count_raises_rather_than_corrupting_the_index(monkeypatch):

    _install(monkeypatch, lambda c: [FakeEmbedding([0.4] * 768)] * 2)

    with pytest.raises(RuntimeError, match="vectors for"):
        gemini.embed(["only one"])


def test_query_and_document_use_different_task_types(monkeypatch):
    seen = []

    class FakeModels:
        def embed_content(self, model, contents, config):
            seen.append(config.task_type)
            return FakeResult([FakeEmbedding([0.5] * 768) for _ in contents])

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())

    gemini.embed(["doc"])
    gemini.embed(["question"], is_query=True)

    assert seen == ["RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY"]

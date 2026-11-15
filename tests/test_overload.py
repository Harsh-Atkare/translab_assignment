import pytest

import app.config as config
from app.rag import gemini


@pytest.fixture(autouse=True)
def stub_gemini():
    yield


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda _: None)


@pytest.fixture(autouse=True)
def clean_settings():
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


DEADLINE = (
    "504 DEADLINE_EXCEEDED. {'error': {'code': 504, 'message': 'Deadline "
    "expired before operation could complete.', 'status': "
    "'DEADLINE_EXCEEDED'}}"
)

OVERLOAD = (
    "503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is "
    "currently experiencing high demand.', 'status': 'UNAVAILABLE'}}"
)

PASSAGES = [{"page": 1, "text": "context"}]


class FakeResponse:
    def __init__(self, text="An answer."):
        self.text = text
        self.candidates = []


def _install(monkeypatch, behaviour):
    calls = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            return behaviour(model, len(calls))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())
    return calls


def test_overload_is_classified_correctly():
    assert gemini._is_overloaded(RuntimeError(OVERLOAD))
    assert not gemini._is_throttled(RuntimeError(OVERLOAD))


def test_504_deadline_is_treated_as_overload():
    assert gemini._is_overloaded(RuntimeError(DEADLINE))
    assert gemini.is_upstream(RuntimeError(DEADLINE))

    msg = gemini.friendly_error(RuntimeError(DEADLINE))
    assert "busy" in msg.lower()
    assert "{" not in msg


def test_overload_fails_immediately(monkeypatch):
    """No retrying - one attempt, then the error."""
    calls = _install(
        monkeypatch, lambda model, n: (_ for _ in ()).throw(RuntimeError(OVERLOAD))
    )

    with pytest.raises(RuntimeError, match="503"):
        gemini.answer("q?", PASSAGES)

    assert len(calls) == 1


def test_non_retryable_errors_are_not_retried(monkeypatch):
    calls = _install(
        monkeypatch,
        lambda model, n: (_ for _ in ()).throw(ValueError("400 INVALID_ARGUMENT")),
    )

    with pytest.raises(ValueError):
        gemini.answer("q?", PASSAGES)

    assert len(calls) == 1


def test_friendly_error_hides_the_json_blob():
    msg = gemini.friendly_error(RuntimeError(OVERLOAD))

    assert "busy" in msg.lower()
    assert "try again" in msg.lower()
    assert "{" not in msg  # no raw payload


def test_friendly_error_distinguishes_rate_limiting():
    msg = gemini.friendly_error(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert "rate limit" in msg.lower()
    assert "free tier" in msg.lower()




def test_upstream_failures_are_classified_for_logging():
    assert gemini.is_upstream(RuntimeError(OVERLOAD))
    assert gemini.is_upstream(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert gemini.is_upstream(RuntimeError("404 NOT_FOUND"))


def test_real_bugs_still_get_a_traceback():
    assert not gemini.is_upstream(TypeError("'NoneType' object is not subscriptable"))
    assert not gemini.is_upstream(KeyError("page"))

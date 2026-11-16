"""Per-day quota exhaustion is a different failure from per-minute throttling.

Seen in the wild:

    429 RESOURCE_EXHAUSTED ... 'Quota exceeded for metric:
    generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash,
    description: Generate content requests per day limit exceeded on Free
    Tier' ... 'retryDelay': '80462s'

Twenty requests per day, per project, per model. Retrying is useless - the
reset is 22 hours away - so this must fail immediately with a message that
says when it resets and that switching GEMINI_MODEL gives a fresh
allowance.
"""

import pytest

import app.config as config
from app.rag import gemini

DAILY_QUOTA = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded "
    "your current quota... Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.8-flash, description: Generate content "
    "requests per day limit exceeded on Free Tier.', 'status': "
    "'RESOURCE_EXHAUSTED', 'details': [{'@type': "
    "'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '80462s'}]}}"
)

PER_MINUTE = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'Quota "
    "exceeded for metric: generate_requests_per_minute', 'details': "
    "[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
    "'retryDelay': '31s'}]}}"
)

PASSAGES = [{"page": 1, "text": "context"}]


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


def test_daily_quota_is_distinguished_from_per_minute():
    assert gemini._is_daily_quota(RuntimeError(DAILY_QUOTA))
    assert not gemini._is_daily_quota(RuntimeError(PER_MINUTE))

    assert gemini._is_throttled(RuntimeError(DAILY_QUOTA))
    assert gemini._is_throttled(RuntimeError(PER_MINUTE))


def test_retry_delay_is_parsed():
    assert gemini._retry_after(RuntimeError(DAILY_QUOTA)) == 80462
    assert gemini._retry_after(RuntimeError(PER_MINUTE)) == 31
    assert gemini._retry_after(RuntimeError("no retry info here")) is None


def test_daily_quota_fails_once(monkeypatch):
    """One attempt, and the message says when it resets."""
    calls = _install(
        monkeypatch,
        lambda model, n: (_ for _ in ()).throw(RuntimeError(DAILY_QUOTA)),
    )

    with pytest.raises(RuntimeError):
        gemini.answer("q?", PASSAGES)

    assert len(calls) == 1, "must not retry a daily quota"


def test_per_minute_throttle_also_fails_immediately(monkeypatch):
    """Both kinds of 429 fail fast now; only the message differs."""
    calls = _install(monkeypatch, lambda model, n: (_ for _ in ()).throw(RuntimeError(PER_MINUTE)))

    with pytest.raises(RuntimeError):
        gemini.answer("q?", PASSAGES)

    assert len(calls) == 1


def test_error_message_says_when_it_resets_and_what_to_do():
    msg = gemini.friendly_error(RuntimeError(DAILY_QUOTA))

    assert "daily free-tier quota" in msg.lower()
    assert "22h" in msg
    assert "GEMINI_MODEL" in msg
    assert "{" not in msg

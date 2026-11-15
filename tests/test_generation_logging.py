import pytest

from app.rag import gemini


@pytest.fixture(autouse=True)
def stub_gemini():
    yield


class FakeResponse:
    text = "An answer."
    candidates = []


def test_logs_before_and_after(monkeypatch, caplog):
    class FakeModels:
        def generate_content(self, model, contents, config):
            return FakeResponse()

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())

    with caplog.at_level("INFO", logger="app.rag.gemini"):
        gemini.answer("q?", [{"page": 1, "text": "ctx"}])

    messages = [r.message for r in caplog.records]
    assert any("generating answer" in m for m in messages)
    assert any("generation finished" in m for m in messages)


def test_missing_key_raises_clearly(monkeypatch):
    import app.config as config

    gemini._client = None
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        gemini.client()

    gemini._client = None
    config.get_settings.cache_clear()


def test_client_is_built_with_a_timeout(monkeypatch):
    import app.config as config

    captured = {}

    class FakeClient:
        def __init__(self, api_key, http_options=None):
            captured["timeout"] = http_options.timeout if http_options else None

    gemini._client = None
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("REQUEST_TIMEOUT", "45")
    monkeypatch.setattr(gemini.genai, "Client", FakeClient)

    gemini.client()
    assert captured["timeout"] == 45_000, "SDK takes milliseconds"

    gemini._client = None
    config.get_settings.cache_clear()


def test_default_timeout_is_two_minutes(monkeypatch):
    import app.config as config

    captured = {}

    class FakeClient:
        def __init__(self, api_key, http_options=None):
            captured["timeout"] = http_options.timeout if http_options else None

    gemini._client = None
    config.get_settings.cache_clear()
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("REQUEST_TIMEOUT", raising=False)
    monkeypatch.setattr(gemini.genai, "Client", FakeClient)

    gemini.client()
    assert captured["timeout"] == 120_000

    gemini._client = None
    config.get_settings.cache_clear()

"""Regression tests for empty model responses.

gemini-3.8-flash is a thinking model. With max_output_tokens=1024 it spent
the whole budget on internal reasoning, came back after 35 seconds with
finish_reason=MAX_TOKENS and no text, and the UI rendered a blank answer
with nothing in the logs to explain it.
"""

import pytest

from app.rag import gemini


class FakeFinishReason:
    def __init__(self, name):
        self.name = name


class FakeCandidate:
    def __init__(self, reason):
        self.finish_reason = FakeFinishReason(reason) if reason else None


class FakeResponse:
    def __init__(self, text, reason=None):
        self.text = text
        self.candidates = [FakeCandidate(reason)]


@pytest.fixture(autouse=True)
def stub_gemini():
    """Override conftest's stub - this file tests gemini.answer itself."""
    yield


def _install(monkeypatch, response):
    captured = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            captured["config"] = config
            captured["model"] = model
            return response

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())
    return captured


PASSAGES = [{"page": 1, "text": "The notice period is ninety days."}]


def test_normal_answer_passes_through(monkeypatch):
    _install(monkeypatch, FakeResponse("Ninety days. [page 1]"))
    assert gemini.answer("notice period?", PASSAGES) == "Ninety days. [page 1]"


def test_max_tokens_with_no_text_explains_itself(monkeypatch):
    """The actual bug. Must not return an empty string."""
    _install(monkeypatch, FakeResponse("", reason="MAX_TOKENS"))

    with pytest.raises(RuntimeError) as err:
        gemini.answer("notice period?", PASSAGES)

    msg = str(err.value)
    assert "THINKING_BUDGET" in msg
    assert "MAX_OUTPUT_TOKENS" in msg


def test_whitespace_only_counts_as_empty(monkeypatch):
    _install(monkeypatch, FakeResponse("   \n  "))

    with pytest.raises(RuntimeError):
        gemini.answer("q?", PASSAGES)


def test_safety_block_says_so(monkeypatch):
    _install(monkeypatch, FakeResponse("", reason="SAFETY"))

    with pytest.raises(RuntimeError, match="blocked"):
        gemini.answer("q?", PASSAGES)


def test_thinking_is_disabled_by_default(monkeypatch):
    import app.config as config

    config.get_settings.cache_clear()
    monkeypatch.delenv("THINKING_BUDGET", raising=False)

    captured = _install(monkeypatch, FakeResponse("ok"))
    gemini.answer("q?", PASSAGES)

    assert captured["config"].thinking_config.thinking_budget == 0
    assert captured["config"].max_output_tokens == 2048
    config.get_settings.cache_clear()


def test_thinking_budget_auto_omits_the_field(monkeypatch):
    import app.config as config

    config.get_settings.cache_clear()
    monkeypatch.setenv("THINKING_BUDGET", "auto")

    captured = _install(monkeypatch, FakeResponse("ok"))
    gemini.answer("q?", PASSAGES)

    assert captured["config"].thinking_config is None
    config.get_settings.cache_clear()


def test_model_rejecting_thinking_config_is_retried_without_it(monkeypatch):
    import app.config as config

    config.get_settings.cache_clear()
    monkeypatch.setenv("THINKING_BUDGET", "0")

    attempts = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            attempts.append(config.thinking_config)
            if config.thinking_config is not None:
                raise ValueError("thinking_config is not supported for this model")
            return FakeResponse("fallback answer")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(gemini, "client", lambda: FakeClient())

    assert gemini.answer("q?", PASSAGES) == "fallback answer"
    assert len(attempts) == 2
    assert attempts[1] is None

    config.get_settings.cache_clear()

import json
import logging

from app.logging_setup import JsonFormatter, request_id_ctx, setup_logging


def test_third_party_noise_is_suppressed():

    setup_logging("INFO", as_json=False)

    for name in ("httpx", "httpcore", "chromadb", "google_genai"):
        assert logging.getLogger(name).level == logging.WARNING, name


def test_our_own_loggers_stay_at_info():
    setup_logging("INFO", as_json=False)
    assert logging.getLogger("app.rag.pipeline").getEffectiveLevel() == logging.INFO


def test_warnings_from_noisy_libraries_still_get_through():
    setup_logging("INFO", as_json=False)
    assert logging.getLogger("google_genai").isEnabledFor(logging.WARNING)


def test_json_formatter_shape():
    token = request_id_ctx.set("abc123")
    try:
        record = logging.LogRecord(
            name="app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="indexed %s",
            args=("file.pdf",),
            exc_info=None,
        )
        record.ctx_chunks = 12

        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_ctx.reset(token)

    assert payload["msg"] == "indexed file.pdf"
    assert payload["request_id"] == "abc123"
    assert payload["level"] == "INFO"
    assert payload["chunks"] == 12 
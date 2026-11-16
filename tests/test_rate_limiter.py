import threading
import time

from app.rag.gemini import RateLimiter


def test_stays_under_the_limit_within_a_minute():
    limiter = RateLimiter(per_minute=5)

    started = time.monotonic()
    for _ in range(5):
        limiter.acquire()

    assert time.monotonic() - started < 0.5


def test_blocks_once_the_window_is_full(monkeypatch):
    limiter = RateLimiter(per_minute=2)
    slept = []

    monkeypatch.setattr("app.rag.gemini.time.sleep", lambda s: (slept.append(s), _advance(limiter)))

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert slept, "expected the third call to block"


def _advance(limiter):

    limiter._times = type(limiter._times)(t - 61 for t in limiter._times)


def test_is_thread_safe():
    """The embedding fallback hits this from a thread pool."""
    limiter = RateLimiter(per_minute=1000)
    errors = []

    def hammer():
        try:
            for _ in range(50):
                limiter.acquire()
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(limiter._times) == 400

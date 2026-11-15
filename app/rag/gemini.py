import logging
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types

from app.config import get_settings

log = logging.getLogger(__name__)

_client: genai.Client | None = None

# Free tier is rate limited per minute, so batch embeddings rather than firing
# one request per chunk. 50 is comfortably under the payload limit.

# no. of max chunks
EMBED_BATCH = 50

SLOW_GENERATION_SECONDS = 15


# per-minute rate limit
DAILY_QUOTA_THRESHOLD = 300


_batching_works = True


class RateLimiter:
    """Token bucket over a sliding minute.

    The per-chunk path sends one request per chunk, and the free tier counts
    requests per minute. Sleeping a fixed amount between calls wastes most of
    the budget; this only blocks once the minute is actually full, so the
    requests go out as fast as the quota allows.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()

                while self._times and now - self._times[0] >= 60:
                    self._times.popleft()

                if len(self._times) < self.per_minute:
                    self._times.append(now)
                    return

                wait = 60 - (now - self._times[0]) + 0.05

            time.sleep(wait)


_limiter: RateLimiter | None = None
_limiter_lock = threading.Lock()


def limiter() -> RateLimiter:
    global _limiter

    if _limiter is None:
        with _limiter_lock:
            if _limiter is None:
                _limiter = RateLimiter(get_settings().embed_rpm)

    return _limiter

SYSTEM_PROMPT = """You are a document assistant for an internal knowledge base.

Answer using ONLY the context passages below. The passages come from PDFs the
user uploaded.

Rules:
- If the context does not contain the answer, say so plainly. Do not guess.
- Cite the page you used, like [page 3]. Cite every claim.
- Be concise. No preamble, no "based on the context provided".
"""


def client() -> genai.Client:
    global _client

    if _client is None:
        cfg = get_settings()

        if not cfg.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Grab a free key at "
                "https://aistudio.google.com/app/apikey and put it in .env"
            )

        _client = genai.Client(
            api_key=cfg.gemini_api_key,
            http_options=types.HttpOptions(timeout=cfg.request_timeout * 1000),
        )

    return _client


def embed(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """Embed a list of strings, one vector out per string in.

    Documents and queries get different task types - this is a real accuracy
    win with Gemini embeddings and costs nothing to do.
    """
    global _batching_works

    if not texts:
        return []

    cfg = get_settings()
    task = "RETRIEVAL_QUERY" if is_query else "RETRIEVAL_DOCUMENT"
    vectors: list[list[float]] = []

    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]

        if _batching_works:
            got = _embed_call(batch, task, cfg)


            if len(got) == len(batch):
                vectors.extend(got)
                continue

            log.warning(
                "%s returned %d embeddings for %d inputs - it does not batch; "
                "falling back to one request per chunk for the rest of this process",
                cfg.embed_model,
                len(got),
                len(batch),
            )
            _batching_works = False

        vectors.extend(_embed_one_by_one(batch, task, cfg))

    if len(vectors) != len(texts):

        raise RuntimeError(
            f"Embedding returned {len(vectors)} vectors for {len(texts)} inputs."
        )

    return vectors


def _embed_call(batch: list[str], task: str, cfg) -> list[list[float]]:
    result = client().models.embed_content(
        model=cfg.embed_model,
        contents=batch,
        config=types.EmbedContentConfig(
            task_type=task,
            output_dimensionality=cfg.embed_dim,
        ),
    )
    return [e.values for e in (result.embeddings or [])]


def _embed_one_by_one(batch: list[str], task: str, cfg) -> list[list[float]]:
    """Fallback path: one API call per chunk, run in parallel.

    Sequentially this was the slowest thing in the app by a wide margin -
    50 chunks meant 50 round trips end to end. Most of that time is network
    wait, so a small thread pool collapses it to roughly
    (chunks / workers) x latency. The rate limiter keeps us inside the free
    tier's per-minute quota rather than racing into 429s.
    """
    started = time.perf_counter()

    def one(text: str) -> list[list[float]]:
        limiter().acquire()
        return _embed_call([text], task, cfg)

    with ThreadPoolExecutor(max_workers=cfg.embed_concurrency) as pool:
        # executor.map preserves input order, which matters - these vectors
        # are zipped back against their chunks by position.
        results = list(pool.map(one, batch))

    out = [vec for result in results for vec in result]

    log.info(
        "embedded %d chunks individually in %.1fs (concurrency %d)",
        len(batch),
        time.perf_counter() - started,
        cfg.embed_concurrency,
    )
    return out


def answer(question: str, passages: list[dict]) -> str:
    cfg = get_settings()

    context = "\n\n---\n\n".join(
        f"[page {p['page']}]\n{p['text']}" for p in passages
    )
    prompt = f"{SYSTEM_PROMPT}\n\nCONTEXT:\n{context}\n\nQUESTION: {question}"

    log.info(
        "generating answer",
        extra={
            "ctx_model": cfg.chat_model,
            "ctx_passages": len(passages),
            "ctx_prompt_chars": len(prompt),
        },
    )

    started = time.perf_counter()
    response = _generate(prompt, cfg, cfg.chat_model)
    elapsed = time.perf_counter() - started

    if elapsed > SLOW_GENERATION_SECONDS:
        log.warning(
            "generation took %.1fs - if this is consistent, check THINKING_BUDGET "
            "(currently %s) and TOP_K",
            elapsed,
            "auto" if cfg.thinking_budget is None else cfg.thinking_budget,
        )
    else:
        log.info("generation finished in %.1fs", elapsed)

    text = (response.text or "").strip()

    if not text:
        raise RuntimeError(_explain_empty(response, cfg))

    return text


def _is_missing_model(exc: Exception) -> bool:
    """404: the model does not exist, or this key cannot reach it.

    Google retires models and restricts older ones to existing users, so a
    name that worked last month can start returning 404 for a new key.
    """
    text = str(exc)
    return "404" in text or "NOT_FOUND" in text.upper()


def _generate(prompt: str, cfg, model: str):
    """One generate_content call, with thinking configured.

    The thinking models spend output tokens on internal reasoning before they
    write anything. With a small max_output_tokens the whole budget goes on
    reasoning, the response hits MAX_TOKENS, and .text comes back empty after
    a long wait - which looks exactly like a hang. For grounded Q&A over
    retrieved passages the reasoning buys very little, so it is off by
    default and the output budget is generous.
    """
    config = types.GenerateContentConfig(
        temperature=0.2,  
        max_output_tokens=cfg.max_output_tokens,
    )

    if cfg.thinking_budget is not None:
        config.thinking_config = types.ThinkingConfig(
            thinking_budget=cfg.thinking_budget
        )

    try:
        return client().models.generate_content(
            model=model, contents=prompt, config=config
        )
    except Exception as exc:

        if cfg.thinking_budget is None or "thinking" not in str(exc).lower():
            raise

        log.warning("%s rejected thinking_config, retrying without", model)
        config.thinking_config = None
        return client().models.generate_content(
            model=model, contents=prompt, config=config
        )


def _explain_empty(response, cfg) -> str:
    """Turn an empty response into something actionable.

    An empty string rendered into the UI as a blank answer is the worst
    possible outcome - it looks like the app is broken with nothing to go on.
    """
    reason = None
    candidates = getattr(response, "candidates", None) or []

    if candidates:
        reason = getattr(candidates[0], "finish_reason", None)
        reason = getattr(reason, "name", None) or str(reason) if reason else None

    if reason == "MAX_TOKENS":
        return (
            f"The model returned no text: it used the whole "
            f"{cfg.max_output_tokens}-token output budget before answering. "
            f"Raise MAX_OUTPUT_TOKENS, or set THINKING_BUDGET=0 to stop "
            f"{cfg.chat_model} spending the budget on internal reasoning."
        )

    if reason in {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"}:
        return f"The model blocked this response ({reason}). Try rephrasing the question."

    return (
        "The model returned an empty response"
        + (f" (finish reason: {reason})" if reason else "")
        + ". Check the model name with `make models`."
    )


def _is_overloaded(exc: Exception) -> bool:
    """Google could not serve the request in time: 503 or 504.

    503 UNAVAILABLE is the model being saturated. 504 DEADLINE_EXCEEDED is
    Google's own backend giving up mid-generation - their deadline, not
    ours, which is why it arrives as a ServerError with a JSON body rather
    than a client timeout. Both mean the same thing to a user: try again.
    """
    text = str(exc).upper()
    return (
        "503" in text
        or "504" in text
        or "UNAVAILABLE" in text
        or "DEADLINE_EXCEEDED" in text
    )


def _is_throttled(exc: Exception) -> bool:
    """429: we have exceeded our own quota."""
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text.upper()


def _retry_after(exc: Exception) -> int | None:
    """Seconds Google says to wait, from the RetryInfo in a 429 payload."""
    match = re.search(r"'retryDelay':\s*'(\d+)s'", str(exc))
    return int(match.group(1)) if match else None


def _is_daily_quota(exc: Exception) -> bool:
    """A 429 for the per-day quota rather than the per-minute rate limit.

    These are very different failures wearing the same status code. The
    per-minute one clears in under a minute and retrying is right. The daily
    one tells you to come back in 22 hours - retrying is pointless, and the
    free tier's daily allowance for a single model can be as low as 20
    requests.

    The quota is per project *per model*, so switching GEMINI_MODEL to
    another Flash model is the only useful response - which is what the
    error message says.
    """
    if not _is_throttled(exc):
        return False

    text = str(exc)
    if "PerDay" in text or "per day" in text.lower():
        return True

    delay = _retry_after(exc)
    return delay is not None and delay > DAILY_QUOTA_THRESHOLD


def is_upstream(exc: Exception) -> bool:
    """True for failures that are Google's state, not a bug in this app.

    Worth separating because these deserve a one-line log, not a fifty-line
    traceback. A stack trace for "the model is busy" buries the real errors
    and looks alarming on a screen during a demo.
    """
    return _is_overloaded(exc) or _is_throttled(exc) or _is_missing_model(exc)


def friendly_error(exc: Exception) -> str:
    """Turn an SDK exception into something a user can act on.

    The raw exception is a JSON blob from Google. Dumping that into the UI
    tells a user nothing and looks like the app crashed.
    """
    if _is_overloaded(exc):
        return (
            "The model is busy and could not finish in time. This is on "
            "Google's side and usually clears within a minute - try again. "
            "If it keeps happening, switch GEMINI_MODEL to a lighter model."
        )

    if _is_daily_quota(exc):
        delay = _retry_after(exc)
        when = ""

        if delay:
            hours, minutes = divmod(delay // 60, 60)
            when = f" It resets in about {hours}h {minutes}m."

        return (
            "This model's daily free-tier quota is used up." + when +
            " The quota is per model, so switching GEMINI_MODEL to another "
            "Flash model gives you a fresh allowance today."
        )

    if _is_throttled(exc):
        return (
            "Rate limit reached on the Gemini free tier. Wait a minute and "
            "try again."
        )

    if _is_missing_model(exc):
        return (
            "This model is not available to your API key. Google retires "
            "models and restricts older ones to existing users. Run "
            "`make models` to see what your key can reach, then set "
            "GEMINI_MODEL to one of those names."
        )

    return f"The model call failed: {str(exc)[:300]}"

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=False)


class Settings:
    """Everything configurable lives here so nothing is hardcoded in the app.

    Model names are env vars on purpose - Google renames Gemini models fairly
    often, and I don't want a redeploy to be a code change. Run
    `python scripts/list_models.py` to see what your key actually has access to.
    """

    def __init__(self) -> None:
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")

        self.chat_model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

        self.max_output_tokens = int(os.getenv("MAX_OUTPUT_TOKENS", "2048"))

        self.request_timeout = int(os.getenv("REQUEST_TIMEOUT", "120"))

        budget = os.getenv("THINKING_BUDGET", "0").strip().lower()
        self.thinking_budget = None if budget in {"auto", "", "none"} else int(budget)
        self.embed_model = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-2")
        self.embed_dim = int(os.getenv("EMBED_DIM", "768"))

        self.embed_concurrency = int(os.getenv("EMBED_CONCURRENCY", "8"))
        self.embed_rpm = int(os.getenv("EMBED_RPM", "90"))

        self.chunk_size = int(os.getenv("CHUNK_SIZE", "1200"))
        self.chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "200"))
        self.top_k = int(os.getenv("TOP_K", "4"))

        self.chroma_dir = os.getenv("CHROMA_DIR", "./data/chroma")
        self.upload_dir = os.getenv("UPLOAD_DIR", "./data/uploads")
        self.collection = os.getenv("CHROMA_COLLECTION", "documents")

        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_json = os.getenv("LOG_JSON", "true").lower() == "true"
        self.app_env = os.getenv("APP_ENV", "local")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

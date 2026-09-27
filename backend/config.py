import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_upload_bytes: int = int(os.getenv("SCHOLARSYNC_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))
    max_pages: int = int(os.getenv("SCHOLARSYNC_MAX_PAGES", "100"))
    max_text_chars: int = int(os.getenv("SCHOLARSYNC_MAX_TEXT_CHARS", "1000000"))
    structured_max_text_chars: int = int(os.getenv("SCHOLARSYNC_STRUCTURED_MAX_TEXT_CHARS", "200000"))
    max_structured_facts: int = int(os.getenv("SCHOLARSYNC_MAX_STRUCTURED_FACTS", "100"))
    gemini_model: str = os.getenv("SCHOLARSYNC_GEMINI_MODEL", "gemini-3.8-flash")
    gemini_timeout_ms: int = int(os.getenv("SCHOLARSYNC_GEMINI_TIMEOUT_MS", "30000"))
    gemini_daily_request_limit: int = int(os.getenv("SCHOLARSYNC_GEMINI_DAILY_REQUEST_LIMIT", "5"))
    gemini_max_output_tokens: int = int(os.getenv("SCHOLARSYNC_GEMINI_MAX_OUTPUT_TOKENS", "4096"))


settings = Settings()

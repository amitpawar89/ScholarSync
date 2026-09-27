import asyncio
import random
import threading
import time
from datetime import date
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import types

from .config import settings


class GeminiConfigurationError(RuntimeError):
    """Raised when Gemini cannot be configured from the environment."""


class GeminiDailyLimitError(RuntimeError):
    """Raised before a request would exceed the local free-tier budget."""


class GeminiServiceError(RuntimeError):
    """Raised after bounded transient retries are exhausted."""


class GeminiPermanentError(RuntimeError):
    """Raised for authentication, invalid-request, model, or policy failures."""


def get_remaining_request_budget() -> int:
    """Return the remaining per-process courtesy budget for Gemini attempts."""
    with _budget_lock:
        if date.today() != _budget_date:
            return settings.gemini_daily_request_limit
        return max(0, settings.gemini_daily_request_limit - _daily_request_count)


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    """Create Gemini only when first needed, and cache that client."""
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiConfigurationError("GEMINI_API_KEY is not configured")
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=settings.gemini_timeout_ms),
    )


_request_lock = threading.Lock()
_budget_lock = threading.Lock()
_budget_date = date.today()
_daily_request_count = 0


def build_generation_config(response_schema: dict | None = None) -> types.GenerateContentConfig:
    kwargs: dict[str, Any] = {
        "max_output_tokens": settings.gemini_max_output_tokens,
        "thinking_config": types.ThinkingConfig(thinking_level="low"),
    }
    if response_schema is not None:
        kwargs["response_mime_type"] = "application/json"
        kwargs["response_schema"] = response_schema
    return types.GenerateContentConfig(**kwargs)


def _retry_delay(error: Exception, attempt: int) -> float | None:
    message = str(error).upper()
    status = str(getattr(error, "status_code", "") or getattr(error, "code", ""))
    status = status.split(".")[-1]
    if status in {"400", "401", "403", "404", "422"} or any(token in message for token in ("INVALID_ARGUMENT", "UNAUTHENTICATED", "PERMISSION_DENIED", "NOT_FOUND", "SAFETY")):
        return None
    if "429" in message or "RESOURCE_EXHAUSTED" in message or status == "429":
        base = min(2 ** (attempt - 1), 8)
        return base + random.uniform(0, 0.25)
    if "503" in message or "UNAVAILABLE" in message or status == "503":
        base = min(2 ** (attempt - 1), 8)
        return base + random.uniform(0, 0.25)
    return None


def _reserve_request() -> None:
    global _budget_date, _daily_request_count
    today = date.today()
    with _budget_lock:
        if today != _budget_date:
            _budget_date = today
            _daily_request_count = 0
        if _daily_request_count >= settings.gemini_daily_request_limit:
            raise GeminiDailyLimitError("Daily free-tier Gemini request limit reached")
        _daily_request_count += 1


def call_gemini_with_retry(client: Any, model: str, prompt: str, **kwargs: Any) -> Any:
    """Serialize requests and retry only 429/503 failures up to three attempts."""
    last_error: Exception | None = None
    with _request_lock:
        for attempt in range(1, 4):
            _reserve_request()
            try:
                return client.models.generate_content(model=model, contents=prompt, **kwargs)
            except Exception as error:
                last_error = error
                delay = _retry_delay(error, attempt)
                if delay is None or attempt == 3:
                    break
                print(f"Gemini busy on attempt {attempt}; retrying in {delay:.2f}s")
                time.sleep(delay)
    if last_error is not None and _retry_delay(last_error, 1) is None:
        raise GeminiPermanentError("Gemini request was rejected") from last_error
    raise GeminiServiceError("Gemini is busy, please try again later") from last_error


async def call_gemini_async(client: Any, model: str, prompt: str, **kwargs: Any) -> Any:
    return await asyncio.to_thread(call_gemini_with_retry, client, model, prompt, **kwargs)

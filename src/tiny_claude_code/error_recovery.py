"""Retry and fallback handling for LLM calls."""
from __future__ import annotations
import time
from typing import Any, Callable

class ErrorHandler:
    """Wrap LLM calls with simple retry, token growth, and model fallback."""

    def __init__(self, max_retries: int=3, backoff_seconds: tuple[float, ...]=(2.0, 4.0, 8.0), fallback_models: list[str] | None=None, sleep: Callable[[float], None]=time.sleep) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def chat(self, client: Any, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None=None, system: str | None=None, max_tokens: int=8000) -> Any:
        raise NotImplementedError('TODO: implement chat')

    def _backoff(self, attempt: int) -> float:
        raise NotImplementedError('TODO: implement _backoff')

    def _status_code(self, exc: Exception) -> int | None:
        raise NotImplementedError('TODO: implement _status_code')

    def _retry_after(self, exc: Exception) -> float | None:
        raise NotImplementedError('TODO: implement _retry_after')

    def _is_token_limit(self, exc: Exception) -> bool:
        raise NotImplementedError('TODO: implement _is_token_limit')

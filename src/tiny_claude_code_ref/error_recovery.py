"""Retry and fallback handling for LLM calls."""

from __future__ import annotations

import time
from typing import Any, Callable


class ErrorHandler:
    """Wrap LLM calls with simple retry, token growth, and model fallback."""

    def __init__(
        self,
        max_retries: int = 3,
        backoff_seconds: tuple[float, ...] = (2.0, 4.0, 8.0),
        fallback_models: list[str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.fallback_models = fallback_models or []
        self.sleep = sleep

    def chat(
        self,
        client: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
        max_tokens: int = 8000,
    ) -> Any:
        models = [getattr(client, "model", None)] + self.fallback_models
        models = [model for model in models if model]
        last_error: Exception | None = None

        for model in models or [None]:
            if model and hasattr(client, "model"):
                client.model = model
            current_tokens = max_tokens

            for attempt in range(self.max_retries + 1):
                try:
                    return client.chat(
                        messages, tools=tools, max_tokens=current_tokens, system=system
                    )
                except Exception as exc:  # noqa: BLE001 - this is a boundary wrapper.
                    last_error = exc
                    if self._is_token_limit(exc) and current_tokens < 64000:
                        current_tokens = min(current_tokens * 2, 64000)
                        continue
                    if self._status_code(exc) == 529:
                        self.sleep(self._retry_after(exc) or self._backoff(attempt))
                        continue
                    if self._status_code(exc) == 429 and attempt < self.max_retries:
                        self.sleep(self._backoff(attempt))
                        continue
                    break

        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM call failed without an exception")

    def _backoff(self, attempt: int) -> float:
        if not self.backoff_seconds:
            return 0
        return self.backoff_seconds[min(attempt, len(self.backoff_seconds) - 1)]

    def _status_code(self, exc: Exception) -> int | None:
        return getattr(exc, "status_code", None)

    def _retry_after(self, exc: Exception) -> float | None:
        headers = getattr(exc, "headers", None) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _is_token_limit(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "max_tokens" in message or (
            "token" in message and "limit" in message
        )


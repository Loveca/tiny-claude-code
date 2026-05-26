"""LLM client wrapper — communicates with the Anthropic API."""

from __future__ import annotations

import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Wrapper around the Anthropic API client."""

    def __init__(self) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL")
        self.model = os.environ.get("MODEL_ID", "claude-sonnet-4-6")
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = anthropic.Anthropic(**kwargs)

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
    ) -> anthropic.types.Message:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.create(**kwargs)

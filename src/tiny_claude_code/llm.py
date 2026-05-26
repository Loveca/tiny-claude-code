"""LLM client wrapper — communicates with the Anthropic API.

ch01: Implement LLMClient.chat() to wrap the Anthropic SDK call.
"""

from __future__ import annotations

import os
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Wrapper around the Anthropic API client.

    ch01: Implement the following:
    - __init__: initialize Anthropic client and model ID
    - chat: send messages and return the response
    """

    def __init__(self) -> None:
        """Initialize the Anthropic client.

        Read from environment variables:
        - ANTHROPIC_API_KEY: API key
        - MODEL_ID: model ID (default: claude-sonnet-4-6)
        - ANTHROPIC_BASE_URL: optional, for compatible API providers
        """
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
        """Send messages to the LLM and return the response.

        Args:
            messages: conversation history in Anthropic messages API format
            tools: list of tool schemas available to the model
            max_tokens: maximum tokens to generate

        Returns:
            Anthropic Message object

        ch07: you will come back here to add ErrorHandler retry logic.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.create(**kwargs)

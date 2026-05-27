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
        raise NotImplementedError('TODO: implement __init__')

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None=None, max_tokens: int=8000, system: str | None=None) -> anthropic.types.Message:
        """Send messages to the LLM and return the response.

        Args:
            messages: conversation history in Anthropic messages API format
            tools: list of tool schemas available to the model
            max_tokens: maximum tokens to generate

        Returns:
            Anthropic Message object

        ch07: you will come back here to add ErrorHandler retry logic.
        """
        raise NotImplementedError('TODO: implement chat')

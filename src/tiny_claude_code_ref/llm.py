"""LLM client wrapper — communicates with the Anthropic API.

ch01: Implement LLMClient.chat() to wrap the Anthropic SDK call.
ch20: add a chat-completions client plus the conversion layer that lets the
same agent run against OpenAI-compatible providers.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()


class OpenAIError(RuntimeError):
    """Raised when a chat completions request fails.

    ``status_code`` and ``headers`` mirror the attributes ErrorHandler reads,
    so provider errors get the same retry treatment as Anthropic errors.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


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
        system: str | None = None,
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
        if system:
            kwargs["system"] = system
        return self.client.messages.create(**kwargs)


@dataclass
class TextBlock:
    """Mimics an Anthropic TextBlock returned by the adapter."""

    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Mimics an Anthropic ToolUseBlock returned by the adapter."""

    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: Any = None


@dataclass
class ChatResponse:
    """Mimics an Anthropic Message: the attributes agent_loop reads."""

    content: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"


def _field(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


def anthropic_messages_to_openai(
    messages: list[dict[str, Any]], system: str | None = None
) -> list[dict[str, Any]]:
    """Convert Anthropic-shaped messages into chat completions messages."""
    converted: list[dict[str, Any]] = []
    if system:
        converted.append({"role": "system", "content": system})
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content")
        if isinstance(content, str):
            converted.append({"role": role, "content": content})
        elif role == "assistant":
            converted.append(_assistant_message(content or []))
        else:
            converted.extend(_user_messages(content or []))
    return converted


def _assistant_message(content: list[Any]) -> dict[str, Any]:
    texts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for block in content:
        block_type = _field(block, "type")
        if block_type == "text":
            text = _field(block, "text") or ""
            if text:
                texts.append(text)
        elif block_type == "tool_use":
            tool_calls.append(
                {
                    "id": _field(block, "id", ""),
                    "type": "function",
                    "function": {
                        "name": _field(block, "name", ""),
                        "arguments": json.dumps(
                            _field(block, "input") or {}, ensure_ascii=False
                        ),
                    },
                }
            )
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(texts) if texts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _user_messages(content: list[Any]) -> list[dict[str, Any]]:
    """Tool results must precede trailing text: ``tool`` roles have to follow
    the assistant tool_calls message directly."""
    results: list[dict[str, Any]] = []
    texts: list[str] = []
    for block in content:
        if isinstance(block, str):
            texts.append(block)
            continue
        block_type = _field(block, "type")
        if block_type == "tool_result":
            results.append(
                {
                    "role": "tool",
                    "tool_call_id": _field(block, "tool_use_id", ""),
                    "content": str(_field(block, "content") or ""),
                }
            )
        elif block_type == "text":
            text = _field(block, "text") or ""
            if text:
                texts.append(text)
    messages: list[dict[str, Any]] = list(results)
    if texts:
        messages.append({"role": "user", "content": "\n".join(texts)})
    return messages


def anthropic_tools_to_openai(
    tools: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Convert Anthropic tool schemas into chat completions function tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            },
        }
        for tool in tools or []
    ]


def openai_response_to_anthropic(data: dict[str, Any]) -> ChatResponse:
    """Convert a chat completions response into the shape the loop reads."""
    choices = data.get("choices") or []
    if not choices:
        raise OpenAIError("chat completions response contained no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    blocks: list[Any] = []

    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if content:
        blocks.append(TextBlock(text=str(content)))

    tool_calls = message.get("tool_calls") or []
    for call in tool_calls:
        function = call.get("function") or {}
        raw_arguments = function.get("arguments") or "{}"
        if isinstance(raw_arguments, str):
            try:
                parsed: Any = json.loads(raw_arguments)
            except json.JSONDecodeError:
                # agent_loop answers non-dict input with a malformed-tool_use
                # error result, which is better than killing the run.
                parsed = None
        else:
            parsed = raw_arguments
        blocks.append(
            ToolUseBlock(
                id=str(call.get("id") or ""),
                name=str(function.get("name") or ""),
                input=parsed,
            )
        )

    if tool_calls:
        stop_reason = "tool_use"
    elif choice.get("finish_reason") == "length":
        stop_reason = "max_tokens"
    else:
        stop_reason = "end_turn"
    return ChatResponse(content=blocks, stop_reason=stop_reason)



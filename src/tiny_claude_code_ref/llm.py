"""LLM client wrapper — communicates with the Anthropic API.

ch01: Implement LLMClient.chat() to wrap the Anthropic SDK call.
ch20: add a chat-completions client plus the conversion layer that lets the
same agent run against OpenAI-compatible providers.
ch21: stream a turn as deltas instead of waiting for the whole message.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
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

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        system: str | None = None,
    ) -> Iterator[Any]:
        """Send messages and yield the turn as stream events.

        ch21: the SDK hands back raw SSE events. Translate them here so the
        rest of the harness only ever sees TextDelta / ToolUseStart /
        ToolUseArgsDelta / MessageStop.
        """
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = system

        stop_reason = "end_turn"
        stopped = False
        for event in self.client.messages.create(**kwargs):
            kind = getattr(event, "type", None)
            if kind == "content_block_start":
                block = getattr(event, "content_block", None)
                if getattr(block, "type", None) == "tool_use":
                    yield ToolUseStart(
                        id=getattr(block, "id", "") or "",
                        name=getattr(block, "name", "") or "",
                    )
            elif kind == "content_block_delta":
                delta = getattr(event, "delta", None)
                delta_type = getattr(delta, "type", None)
                if delta_type == "text_delta":
                    yield TextDelta(text=getattr(delta, "text", "") or "")
                elif delta_type == "input_json_delta":
                    yield ToolUseArgsDelta(
                        partial_json=getattr(delta, "partial_json", "") or ""
                    )
            elif kind == "message_delta":
                delta = getattr(event, "delta", None)
                reason = getattr(delta, "stop_reason", None)
                if reason:
                    stop_reason = reason
            elif kind == "message_stop":
                stopped = True
                yield MessageStop(stop_reason=stop_reason)
        if not stopped:
            # A truncated stream still has to close the turn.
            yield MessageStop(stop_reason=stop_reason)


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


@dataclass
class TextDelta:
    """A chunk of assistant text produced while streaming."""

    type: str = "text_delta"
    text: str = ""


@dataclass
class ToolUseStart:
    """A tool call began; its arguments arrive in later deltas."""

    type: str = "tool_use_start"
    id: str = ""
    name: str = ""


@dataclass
class ToolUseArgsDelta:
    """A fragment of the JSON-encoded tool arguments.

    Neither API guarantees a fragment is valid JSON on its own, so deltas are
    only meaningful once concatenated.
    """

    type: str = "tool_use_args_delta"
    partial_json: str = ""


@dataclass
class MessageStop:
    """The turn ended and reported why."""

    type: str = "message_stop"
    stop_reason: str = "end_turn"


def _parse_tool_arguments(raw: str) -> Any:
    """Turn accumulated argument text into the dict agent_loop expects.

    Empty text means "no arguments" (``{}``); unparsable text becomes ``None``
    so the loop answers with a malformed-block error instead of crashing.
    """
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


class StreamAccumulator:
    """Glue streamed deltas back into the ChatResponse shape.

    The loop only knows ``content`` blocks and ``stop_reason``, so streaming
    needs a place where fragments become blocks again. Feed every event in
    order and read the result once the stream ends.
    """

    def __init__(self) -> None:
        self.blocks: list[Any] = []
        self.stop_reason = "end_turn"
        self._pending: dict[str, Any] | None = None

    def feed(self, event: Any) -> None:
        kind = getattr(event, "type", None)
        if kind == "text_delta":
            self._append_text(getattr(event, "text", "") or "")
        elif kind == "tool_use_start":
            self._start_tool(
                getattr(event, "id", "") or "", getattr(event, "name", "") or ""
            )
        elif kind == "tool_use_args_delta":
            if self._pending is not None:
                self._pending["parts"].append(getattr(event, "partial_json", "") or "")
        elif kind == "message_stop":
            reason = getattr(event, "stop_reason", "") or ""
            if reason:
                self.stop_reason = reason
            self._close_tool()

    def response(self) -> ChatResponse:
        self._close_tool()
        if self.stop_reason == "end_turn" and any(
            isinstance(block, ToolUseBlock) for block in self.blocks
        ):
            # A stream that ended without a stop event still asked for tools.
            self.stop_reason = "tool_use"
        return ChatResponse(content=list(self.blocks), stop_reason=self.stop_reason)

    def _append_text(self, text: str) -> None:
        if not text:
            return
        if self.blocks and isinstance(self.blocks[-1], TextBlock):
            self.blocks[-1].text += text
        else:
            self.blocks.append(TextBlock(text=text))

    def _start_tool(self, tool_id: str, name: str) -> None:
        if self._pending is not None and tool_id and self._pending["block"].id == tool_id:
            # Servers may repeat the start to deliver the rest of the name.
            if name:
                self._pending["block"].name = name
            return
        self._close_tool()
        block = ToolUseBlock(id=tool_id, name=name)
        self.blocks.append(block)
        self._pending = {"block": block, "parts": []}

    def _close_tool(self) -> None:
        if self._pending is None:
            return
        block = self._pending["block"]
        block.input = _parse_tool_arguments("".join(self._pending["parts"]))
        self._pending = None


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


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _http_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise OpenAIError(
            f"chat completions request failed ({exc.code}): {body}",
            status_code=exc.code,
            headers=dict(exc.headers or {}),
        ) from exc
    except urllib.error.URLError as exc:
        raise OpenAIError(f"chat completions connection failed: {exc.reason}") from exc


def _stream_stop_reason(finish_reason: str) -> str:
    """Map a chat completions finish_reason onto the harness vocabulary."""
    if finish_reason == "tool_calls":
        return "tool_use"
    if finish_reason == "length":
        return "max_tokens"
    return "end_turn"


def _http_stream_transport(
    url: str, headers: dict[str, str], payload: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """POST the payload and yield one decoded object per SSE ``data:`` line."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break
                if data:
                    yield json.loads(data)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise OpenAIError(
            f"chat completions request failed ({exc.code}): {body}",
            status_code=exc.code,
            headers=dict(exc.headers or {}),
        ) from exc
    except urllib.error.URLError as exc:
        raise OpenAIError(f"chat completions connection failed: {exc.reason}") from exc


class OpenAICompatibleClient:
    """Talk to any server that implements OpenAI-style chat completions.

    ch20: converts Anthropic-shaped messages/tools on the way out and turns
    the reply back into the TextBlock/ToolUseBlock shape agent_loop reads.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        transport: Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]
        | None = None,
        stream_transport: Callable[
            [str, dict[str, str], dict[str, Any]], Iterator[dict[str, Any]]
        ]
        | None = None,
    ) -> None:
        self.model = model or os.environ.get("MODEL_ID") or DEFAULT_OPENAI_MODEL
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        base = (
            base_url
            or os.environ.get("OPENAI_BASE_URL")
            or DEFAULT_OPENAI_BASE_URL
        )
        self.endpoint = base.rstrip("/") + "/chat/completions"
        self.transport = transport or _http_transport
        self.stream_transport = stream_transport or _http_stream_transport

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        system: str | None = None,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages_to_openai(messages, system),
        }
        if tools:
            payload["tools"] = anthropic_tools_to_openai(tools)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = self.transport(self.endpoint, headers, payload)
        return openai_response_to_anthropic(data)

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        system: str | None = None,
    ) -> Iterator[Any]:
        """Send messages and yield the turn as stream events.

        ch21: chat completions streams ``choices[0].delta``; tool calls arrive
        as fragments keyed by ``index``, so the first fragment opens the call
        and later ones only append argument text.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": anthropic_messages_to_openai(messages, system),
            "stream": True,
        }
        if tools:
            payload["tools"] = anthropic_tools_to_openai(tools)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        started: dict[int, bool] = {}
        stop_reason = "end_turn"
        for chunk in self.stream_transport(self.endpoint, headers, payload):
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                text = delta.get("content")
                if isinstance(text, str) and text:
                    yield TextDelta(text=text)
                for call in delta.get("tool_calls") or []:
                    index = int(call.get("index") or 0)
                    function = call.get("function") or {}
                    name = function.get("name") or ""
                    if not started.get(index) and (call.get("id") or name):
                        started[index] = True
                        yield ToolUseStart(
                            id=str(call.get("id") or f"call_{index}"), name=name
                        )
                    arguments = function.get("arguments")
                    if arguments:
                        yield ToolUseArgsDelta(partial_json=str(arguments))
                finish_reason = choice.get("finish_reason")
                if finish_reason:
                    stop_reason = _stream_stop_reason(finish_reason)
        yield MessageStop(stop_reason=stop_reason)


def create_client() -> LLMClient | OpenAICompatibleClient:
    """Pick a client from ``LLM_PROVIDER`` (default: ``anthropic``)."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "openai":
        return OpenAICompatibleClient()
    return LLMClient()



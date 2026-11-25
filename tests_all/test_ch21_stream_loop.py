"""ch21: agent_loop hands assistant text to on_text while the model writes."""

from __future__ import annotations

from typing import Any

from conftest import MockLLMClient

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.llm import (
    MessageStop,
    OpenAICompatibleClient,
    TextBlock,
    TextDelta,
    ToolUseArgsDelta,
    ToolUseBlock,
    ToolUseStart,
)
from tiny_claude_code.tools import ToolRegistry
from tiny_claude_code.tools.base import Tool


class _EchoTool(Tool):
    name = "echo"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": "echo",
            "description": "Echo text back.",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}}},
        }

    def execute(self, text: str = "") -> str:
        return f"echo:{text}"


def _text_turn(*pieces: str) -> list[Any]:
    return [TextDelta(text=piece) for piece in pieces] + [MessageStop()]


def _tool_turn(text: str, name: str, arguments: str) -> list[Any]:
    return [
        TextDelta(text=text),
        ToolUseStart(id="call_1", name=name),
        ToolUseArgsDelta(partial_json=arguments),
        MessageStop(stop_reason="tool_use"),
    ]


class StreamingClient:
    """Serves scripted turns; ``chat`` must not be touched once it can stream."""

    def __init__(self, *turns: list[Any]) -> None:
        self.turns = list(turns)
        self.requests: list[dict[str, Any]] = []

    def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        system: str | None = None,
    ) -> Any:
        self.requests.append({"messages": messages, "tools": tools, "system": system})
        yield from self.turns[len(self.requests) - 1]

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("chat() must not be called when chat_stream exists")


def _run(client: Any, **kwargs: Any) -> tuple[str, list[str], list[dict]]:
    pieces: list[str] = []
    messages: list[dict[str, Any]] = [{"role": "user", "content": "go"}]
    final = agent_loop(messages, client=client, on_text=pieces.append, **kwargs)
    return final, pieces, messages


def test_text_is_forwarded_while_the_model_writes() -> None:
    client = StreamingClient(_text_turn("Hel", "lo", "!"))

    final, pieces, _ = _run(client)

    # Deltas arrive one by one; the newline closes the turn.
    assert pieces == ["Hel", "lo", "!", "\n"]
    assert final == "Hello!"


def test_tool_turn_streams_text_then_runs_the_tool() -> None:
    client = StreamingClient(
        _tool_turn("Checking.", "echo", '{"text": "hi"}'), _text_turn("Done.")
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())

    final, pieces, messages = _run(client, tool_handlers=registry)

    assert final == "Done."
    assert pieces == ["Checking.", "\n", "Done.", "\n"]
    assistant = messages[1]["content"]
    assert isinstance(assistant[0], TextBlock) and assistant[0].text == "Checking."
    assert isinstance(assistant[1], ToolUseBlock)
    assert (assistant[1].name, assistant[1].input) == ("echo", {"text": "hi"})
    assert messages[2]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call_1",
        "content": "echo:hi",
    }
    # The second request carries the rebuilt blocks, not the raw events.
    second = client.requests[1]["messages"]
    assert second[1]["content"] is assistant
    assert second[2]["content"][0]["content"] == "echo:hi"


def test_turn_without_text_emits_nothing() -> None:
    client = StreamingClient(_tool_turn("", "echo", "{}"), _text_turn("Done."))
    registry = ToolRegistry()
    registry.register(_EchoTool())

    final, pieces, _ = _run(client, tool_handlers=registry)

    assert final == "Done."
    assert pieces == ["Done.", "\n"]


def test_streaming_passes_tools_and_system_to_the_client() -> None:
    client = StreamingClient(_text_turn("ok"))
    registry = ToolRegistry()
    registry.register(_EchoTool())

    _run(client, tool_handlers=registry, system="be brief")

    request = client.requests[0]
    assert request["system"] == "be brief"
    assert [tool["name"] for tool in request["tools"]] == ["echo"]


def test_client_without_chat_stream_delivers_text_in_one_piece() -> None:
    client = MockLLMClient()
    client.add_text_response("Hello!")

    final, pieces, _ = _run(client)

    assert final == "Hello!"
    assert pieces == ["Hello!", "\n"]


def test_streamed_turn_does_not_go_through_the_error_handler() -> None:
    class _NoRetry:
        def chat(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("streamed turns are not retried")

    final, _, _ = _run(StreamingClient(_text_turn("ok")), error_handler=_NoRetry())

    assert final == "ok"


def test_without_on_text_the_plain_path_is_untouched() -> None:
    class _StreamCapableMock(MockLLMClient):
        def chat_stream(self, *args: Any, **kwargs: Any) -> Any:
            raise AssertionError("chat_stream must not be called without on_text")

    class _CountingHandler:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, client: Any, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
            self.calls += 1
            return client.chat(messages, **kwargs)

    client = _StreamCapableMock()
    client.add_text_response("plain")
    handler = _CountingHandler()
    messages: list[dict[str, Any]] = [{"role": "user", "content": "go"}]

    final = agent_loop(messages, client=client, error_handler=handler)

    # No callback, no streaming: the error handler still owns the LLM call.
    assert final == "plain"
    assert handler.calls == 1


def test_loop_streams_over_chat_completions_chunks() -> None:
    chunks = [
        [{"choices": [{"delta": {"content": "Let me "}}]},
         {"choices": [{"delta": {"content": "echo."}}]},
         {"choices": [{"delta": {"tool_calls": [
             {"index": 0, "id": "call_7", "type": "function",
              "function": {"name": "echo", "arguments": '{"text": "yo"}'}}
         ]}}]},
         {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]}],
        [{"choices": [{"delta": {"content": "Heard: "}}]},
         {"choices": [{"delta": {"content": "yo"}, "finish_reason": "stop"}]}],
    ]
    client = OpenAICompatibleClient(
        model="m",
        api_key="k",
        base_url="http://t/v1",
        stream_transport=lambda url, headers, payload: iter(chunks.pop(0)),
    )
    registry = ToolRegistry()
    registry.register(_EchoTool())

    final, pieces, _ = _run(client, tool_handlers=registry)

    assert final == "Heard: yo"
    assert pieces == ["Let me ", "echo.", "\n", "Heard: ", "yo", "\n"]

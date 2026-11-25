"""ch21: the two clients turn their wire formats into stream events."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from tiny_claude_code.llm import (
    LLMClient,
    OpenAICompatibleClient,
    StreamAccumulator,
    TextDelta,
    ToolUseArgsDelta,
    ToolUseStart,
)


def _anthropic_client(events: list[Any], captured: dict[str, Any]) -> LLMClient:
    """An LLMClient whose SDK call returns ``events`` instead of a socket."""
    client = LLMClient.__new__(LLMClient)
    client.model = "claude-test"

    class _Messages:
        def create(self, **kwargs: Any) -> Any:
            captured.update(kwargs)
            return iter(events)

    client.client = SimpleNamespace(messages=_Messages())
    return client


def _block_start(block_type: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_start",
        content_block=SimpleNamespace(type=block_type, **fields),
    )


def _block_delta(**fields: Any) -> SimpleNamespace:
    return SimpleNamespace(
        type="content_block_delta", delta=SimpleNamespace(**fields)
    )


def _anthropic_tool_turn() -> list[Any]:
    return [
        SimpleNamespace(type="message_start"),
        _block_start("text", text=""),
        _block_delta(type="text_delta", text="Let me "),
        _block_delta(type="text_delta", text="check."),
        SimpleNamespace(type="content_block_stop"),
        _block_start("tool_use", id="toolu_01", name="bash"),
        _block_delta(type="input_json_delta", partial_json='{"command"'),
        _block_delta(type="input_json_delta", partial_json=': "ls"}'),
        SimpleNamespace(type="content_block_stop"),
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="tool_use")),
        SimpleNamespace(type="message_stop"),
    ]


def test_anthropic_text_deltas_stream_through() -> None:
    events = [
        _block_start("text", text=""),
        _block_delta(type="text_delta", text="Hel"),
        _block_delta(type="text_delta", text="lo"),
        SimpleNamespace(type="message_stop"),
    ]
    client = _anthropic_client(events, {})

    streamed = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert [event.type for event in streamed] == [
        "text_delta",
        "text_delta",
        "message_stop",
    ]
    assert [event.text for event in streamed[:-1]] == ["Hel", "lo"]


def test_anthropic_tool_call_streams_start_then_arguments() -> None:
    client = _anthropic_client(_anthropic_tool_turn(), {})

    streamed = list(client.chat_stream([{"role": "user", "content": "list files"}]))

    assert [event.type for event in streamed] == [
        "text_delta",
        "text_delta",
        "tool_use_start",
        "tool_use_args_delta",
        "tool_use_args_delta",
        "message_stop",
    ]
    start = streamed[2]
    assert isinstance(start, ToolUseStart)
    assert (start.id, start.name) == ("toolu_01", "bash")
    assert streamed[-1].stop_reason == "tool_use"


def test_anthropic_request_asks_for_a_stream() -> None:
    captured: dict[str, Any] = {}
    client = _anthropic_client([SimpleNamespace(type="message_stop")], captured)

    list(
        client.chat_stream(
            [{"role": "user", "content": "hi"}],
            tools=[{"name": "bash", "description": "", "input_schema": {"type": "object"}}],
            system="be brief",
            max_tokens=128,
        )
    )

    assert captured["stream"] is True
    assert captured["model"] == "claude-test"
    assert captured["max_tokens"] == 128
    assert captured["system"] == "be brief"
    assert captured["tools"][0]["name"] == "bash"


def test_anthropic_truncated_stream_still_stops() -> None:
    client = _anthropic_client(
        [_block_delta(type="text_delta", text="cut short")], {}
    )

    streamed = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert streamed[-1].type == "message_stop"
    assert streamed[-1].stop_reason == "end_turn"


def test_anthropic_stream_accumulates_into_a_response() -> None:
    client = _anthropic_client(_anthropic_tool_turn(), {})
    accumulator = StreamAccumulator()

    for event in client.chat_stream([{"role": "user", "content": "list files"}]):
        accumulator.feed(event)
    response = accumulator.response()

    assert response.stop_reason == "tool_use"
    assert response.content[0].text == "Let me check."
    assert response.content[1].input == {"command": "ls"}


def _completions_client(chunks: list[dict[str, Any]], captured: dict[str, Any]) -> OpenAICompatibleClient:
    def stream_transport(url: str, headers: dict[str, str], payload: dict[str, Any]):
        captured.update(url=url, headers=headers, payload=payload)
        return iter(chunks)

    return OpenAICompatibleClient(
        model="m",
        api_key="secret",
        base_url="http://example.test/v1",
        stream_transport=stream_transport,
    )


def _chunk(**delta: Any) -> dict[str, Any]:
    return {"choices": [{"delta": delta}]}


def _tool_chunk(index: int, **function: Any) -> dict[str, Any]:
    return {
        "choices": [
            {"delta": {"tool_calls": [{"index": index, "function": function}]}}
        ]
    }


def test_chat_completions_text_chunks_stream_through() -> None:
    client = _completions_client(
        [_chunk(content="Hel"), _chunk(content="lo")], {}
    )

    streamed = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert [event.text for event in streamed if isinstance(event, TextDelta)] == [
        "Hel",
        "lo",
    ]
    assert streamed[-1].type == "message_stop"


def test_chat_completions_tool_fragments_merge_into_one_call() -> None:
    client = _completions_client(
        [
            _tool_chunk(0, name="bash", arguments='{"comm'),
            _tool_chunk(0, arguments='and": "ls"}'),
        ],
        {},
    )

    streamed = list(client.chat_stream([{"role": "user", "content": "list files"}]))

    assert [event.type for event in streamed] == [
        "tool_use_start",
        "tool_use_args_delta",
        "tool_use_args_delta",
        "message_stop",
    ]
    assert streamed[0].name == "bash"
    assert "".join(
        event.partial_json for event in streamed if isinstance(event, ToolUseArgsDelta)
    ) == '{"command": "ls"}'


def test_chat_completions_missing_id_gets_a_synthetic_one() -> None:
    client = _completions_client([_tool_chunk(0, name="bash")], {})

    streamed = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert streamed[0].id == "call_0"


def test_chat_completions_length_maps_to_max_tokens() -> None:
    client = _completions_client(
        [{"choices": [{"delta": {"content": "cut"}, "finish_reason": "length"}]}], {}
    )

    streamed = list(client.chat_stream([{"role": "user", "content": "hi"}]))

    assert streamed[-1].stop_reason == "max_tokens"


def test_chat_completions_request_asks_for_a_stream() -> None:
    captured: dict[str, Any] = {}
    client = _completions_client([], captured)

    list(
        client.chat_stream(
            [{"role": "user", "content": "hi"}],
            tools=[{"name": "bash", "description": "", "input_schema": {"type": "object"}}],
            system="be brief",
            max_tokens=64,
        )
    )

    assert captured["url"] == "http://example.test/v1/chat/completions"
    assert captured["headers"]["Accept"] == "text/event-stream"
    payload = captured["payload"]
    assert payload["stream"] is True
    assert payload["max_tokens"] == 64
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["tools"][0]["type"] == "function"


def test_chat_completions_stream_accumulates_into_a_response() -> None:
    client = _completions_client(
        [
            _chunk(content="Running"),
            _tool_chunk(0, name="bash", arguments='{"command"'),
            _tool_chunk(0, arguments=': "dir"}'),
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        ],
        {},
    )
    accumulator = StreamAccumulator()

    for event in client.chat_stream([{"role": "user", "content": "list files"}]):
        accumulator.feed(event)
    response = accumulator.response()

    assert response.stop_reason == "tool_use"
    assert response.content[0].text == "Running"
    assert response.content[1].input == {"command": "dir"}

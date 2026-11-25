"""ch21: rebuilding a response from streamed deltas."""

from __future__ import annotations

import json

from tiny_claude_code.llm import (
    MessageStop,
    StreamAccumulator,
    TextBlock,
    TextDelta,
    ToolUseArgsDelta,
    ToolUseBlock,
    ToolUseStart,
)


def _collect(*events: object) -> StreamAccumulator:
    accumulator = StreamAccumulator()
    for event in events:
        accumulator.feed(event)
    return accumulator


def test_text_deltas_join_into_one_block() -> None:
    response = _collect(
        TextDelta(text="Hel"),
        TextDelta(text="lo"),
        TextDelta(text="!"),
        MessageStop(),
    ).response()

    assert len(response.content) == 1
    assert response.content[0].type == "text"
    assert response.content[0].text == "Hello!"


def test_empty_deltas_are_ignored() -> None:
    response = _collect(TextDelta(text=""), MessageStop()).response()

    assert response.content == []


def test_text_after_a_tool_call_starts_a_new_block() -> None:
    response = _collect(
        TextDelta(text="checking"),
        ToolUseStart(id="t1", name="bash"),
        ToolUseArgsDelta(partial_json='{"command": "ls"}'),
        TextDelta(text="done"),
        MessageStop(stop_reason="tool_use"),
    ).response()

    assert [block.type for block in response.content] == ["text", "tool_use", "text"]
    assert response.content[2].text == "done"


def test_tool_arguments_are_parsed_when_the_stream_stops() -> None:
    arguments = {"command": "ls -la", "timeout": 5}
    raw = json.dumps(arguments)
    response = _collect(
        ToolUseStart(id="t1", name="bash"),
        ToolUseArgsDelta(partial_json=raw[:5]),
        ToolUseArgsDelta(partial_json=raw[5:]),
        MessageStop(stop_reason="tool_use"),
    ).response()

    block = response.content[0]
    assert isinstance(block, ToolUseBlock)
    assert block.id == "t1"
    assert block.name == "bash"
    assert block.input == arguments


def test_tool_without_arguments_becomes_an_empty_dict() -> None:
    response = _collect(
        ToolUseStart(id="t1", name="todo"),
        MessageStop(stop_reason="tool_use"),
    ).response()

    assert response.content[0].input == {}


def test_unparsable_arguments_become_none() -> None:
    response = _collect(
        ToolUseStart(id="t1", name="bash"),
        ToolUseArgsDelta(partial_json="{oops"),
        MessageStop(stop_reason="tool_use"),
    ).response()

    # agent_loop answers a non-dict input with a malformed-block tool result.
    assert response.content[0].input is None


def test_repeated_start_refines_the_tool_name() -> None:
    response = _collect(
        ToolUseStart(id="t1", name="ba"),
        ToolUseStart(id="t1", name="bash"),
        ToolUseArgsDelta(partial_json="{}"),
        MessageStop(stop_reason="tool_use"),
    ).response()

    assert len(response.content) == 1
    assert response.content[0].name == "bash"


def test_two_tool_calls_stay_separate() -> None:
    response = _collect(
        ToolUseStart(id="t1", name="bash"),
        ToolUseArgsDelta(partial_json='{"command": "ls"}'),
        ToolUseStart(id="t2", name="read"),
        ToolUseArgsDelta(partial_json='{"path": "a.txt"}'),
        MessageStop(stop_reason="tool_use"),
    ).response()

    assert [block.id for block in response.content] == ["t1", "t2"]
    assert response.content[1].input == {"path": "a.txt"}


def test_stop_reason_comes_from_the_stop_event() -> None:
    response = _collect(TextDelta(text="cut"), MessageStop(stop_reason="max_tokens")).response()

    assert response.stop_reason == "max_tokens"


def test_tool_blocks_without_a_stop_event_imply_tool_use() -> None:
    response = _collect(ToolUseStart(id="t1", name="bash")).response()

    assert response.stop_reason == "tool_use"


def test_unknown_events_are_ignored() -> None:
    accumulator = _collect(TextDelta(text="hi"))

    class Ping:
        type = "ping"

    accumulator.feed(Ping())

    response = accumulator.response()
    assert [block.text for block in response.content if isinstance(block, TextBlock)] == ["hi"]
    assert response.stop_reason == "end_turn"

"""ch21: streamed turns keep working once they are saved and replayed."""

from __future__ import annotations

import json
from pathlib import Path

from tiny_claude_code.llm import (
    MessageStop,
    StreamAccumulator,
    TextDelta,
    ToolUseArgsDelta,
    ToolUseStart,
    anthropic_messages_to_openai,
)
from tiny_claude_code.session import SessionManager


def _streamed_messages() -> list[dict]:
    """A two-turn history whose assistant blocks came out of the accumulator."""
    accumulator = StreamAccumulator()
    for event in (
        TextDelta(text="Let me look."),
        ToolUseStart(id="toolu_01", name="bash"),
        ToolUseArgsDelta(partial_json='{"command": "ls"}'),
        MessageStop(stop_reason="tool_use"),
    ):
        accumulator.feed(event)
    return [
        {"role": "user", "content": "list the files"},
        {"role": "assistant", "content": accumulator.response().content},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "toolu_01", "content": "README.md"}
            ],
        },
    ]


def test_session_file_stores_streamed_blocks_as_plain_objects(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)

    path = sessions.save("s1", _streamed_messages(), {"workspace": "demo"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assistant = payload["messages"][1]["content"]
    assert assistant[0] == {"type": "text", "text": "Let me look."}
    assert assistant[1] == {
        "type": "tool_use",
        "id": "toolu_01",
        "name": "bash",
        "input": {"command": "ls"},
    }


def test_saved_streamed_history_loads_back_in_wire_shape(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    sessions.save("s1", _streamed_messages())

    loaded = sessions.load("s1")

    assert [message["role"] for message in loaded] == ["user", "assistant", "user"]
    # Loaded blocks are plain dicts, i.e. exactly what the Messages API expects.
    assert loaded[1]["content"][1]["input"] == {"command": "ls"}


def test_saved_streamed_history_converts_for_chat_completions(tmp_path: Path) -> None:
    sessions = SessionManager(tmp_path)
    sessions.save("s1", _streamed_messages())

    converted = anthropic_messages_to_openai(sessions.load("s1"))

    assert [message["role"] for message in converted] == ["user", "assistant", "tool"]
    assert converted[1]["tool_calls"][0]["function"]["name"] == "bash"
    assert converted[2] == {"role": "tool", "tool_call_id": "toolu_01", "content": "README.md"}

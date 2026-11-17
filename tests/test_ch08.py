"""Tests for ch08: Context Budget."""

from __future__ import annotations

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.context import ContextManager
from conftest import MockLLMClient


def test_estimate_tokens_tracks_character_count() -> None:
    manager = ContextManager()
    messages = [{"role": "user", "content": "a" * 40}]

    assert manager.estimate_tokens(messages) == 10


def test_trim_tool_output_keeps_head_and_tail() -> None:
    manager = ContextManager(max_tool_chars=10)
    original = "head" + "x" * 42 + "tail"
    messages = [
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "1", "content": original}],
        }
    ]

    trimmed = manager.trim_tool_output(messages)

    content = trimmed[0]["content"][0]["content"]
    assert content.startswith("head")
    assert content.endswith("tail")
    assert "truncated by context budget" in content
    assert messages[0]["content"][0]["content"] == original


def test_trim_tool_output_reuses_untouched_messages() -> None:
    manager = ContextManager(max_tool_chars=10)
    long_result = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "1", "content": "x" * 50}],
    }
    short_result = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "2", "content": "ok"}],
    }

    trimmed = manager.trim_tool_output([long_result, short_result])

    assert trimmed[0] is not long_result
    assert trimmed[1] is short_result


def test_snip_old_messages_does_not_split_tool_pairs() -> None:
    manager = ContextManager(keep_head=2, keep_tail=1)
    messages = [
        {"role": "user", "content": "goal"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t1", "name": "bash", "input": {}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "out"}],
        },
        {"role": "assistant", "content": "working"},
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "t2", "name": "bash", "input": {}}],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t2", "content": "out2"}],
        },
    ]

    snipped = manager.snip_old_messages(messages)

    blocks = [
        block
        for message in snipped
        if isinstance(message["content"], list)
        for block in message["content"]
    ]
    assert not [
        block for block in blocks if block["type"] in ("tool_use", "tool_result")
    ]
    assert snipped[0] == messages[0]


def test_snip_old_messages_preserves_head_and_tail() -> None:
    manager = ContextManager(keep_head=1, keep_tail=2)
    messages = [{"role": "user", "content": str(index)} for index in range(8)]

    snipped = manager.snip_old_messages(messages)

    assert [message["content"] for message in snipped] == [
        "0",
        "[snipped 5 old messages to fit context budget]",
        "6",
        "7",
    ]


def test_compact_pipeline_reduces_token_count() -> None:
    manager = ContextManager(max_tokens=20, max_tool_chars=20, keep_head=1, keep_tail=1)
    messages = [{"role": "user", "content": "x" * 200} for _ in range(6)]

    before = manager.estimate_tokens(messages)
    manager.compact(messages)
    after = manager.estimate_tokens(messages)

    assert after < before
    assert len(messages) == 3


def test_empty_messages_do_not_crash() -> None:
    manager = ContextManager(max_tokens=1)
    messages: list[dict] = []

    assert manager.compact(messages) == []


def test_agent_loop_compacts_before_llm_call() -> None:
    manager = ContextManager(max_tokens=5, keep_head=1, keep_tail=1)
    client = MockLLMClient()
    client.add_text_response("ok")
    messages = [{"role": "user", "content": "x" * 80} for _ in range(5)]

    result = agent_loop(messages, client=client, context_manager=manager)

    assert result == "ok"
    assert len(messages) < 6

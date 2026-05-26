"""Tests for ch08: Context Budget."""

from __future__ import annotations

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.context import ContextManager
from conftest import MockLLMClient


def test_estimate_tokens_tracks_character_count() -> None:
    manager = ContextManager()
    messages = [{"role": "user", "content": "a" * 40}]

    assert manager.estimate_tokens(messages) == 10


def test_trim_tool_output_adds_truncation_marker() -> None:
    manager = ContextManager(max_tool_chars=10)
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "1", "content": "x" * 50}
            ],
        }
    ]

    trimmed = manager.trim_tool_output(messages)

    content = trimmed[0]["content"][0]["content"]
    assert content.startswith("x" * 10)
    assert "[truncated" in content
    assert messages[0]["content"][0]["content"] == "x" * 50


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

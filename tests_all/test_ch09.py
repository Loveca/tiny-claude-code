"""Tests for ch09: /compact."""

from __future__ import annotations

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.compact import CompactManager
from tiny_claude_code.context import ContextManager
from conftest import MockLLMClient


def test_summarize_calls_llm_and_returns_text() -> None:
    client = MockLLMClient()
    client.add_text_response("summary")
    manager = CompactManager()

    result = manager.summarize([{"role": "user", "content": "hello"}], client)

    assert result == "summary"
    assert "Summarize" in client.last_system


def test_build_compact_messages_keeps_summary_and_recent() -> None:
    manager = CompactManager()
    recent = [{"role": "user", "content": "latest"}]

    messages = manager.build_compact_messages("summary", recent)

    assert messages[0]["content"] == "Conversation summary so far:\nsummary"
    assert messages[1:] == recent


def test_compact_reduces_message_count() -> None:
    client = MockLLMClient()
    client.add_text_response("short summary")
    manager = CompactManager(keep_recent=2)
    messages = [{"role": "user", "content": str(index)} for index in range(10)]

    compacted = manager.compact(messages, client)

    assert len(compacted) == 3
    assert compacted[0]["content"].endswith("short summary")
    assert [message["content"] for message in compacted[1:]] == ["8", "9"]


def test_context_manager_can_auto_compact_with_llm_summary() -> None:
    client = MockLLMClient()
    client.add_text_response("auto summary")
    compact_manager = CompactManager(keep_recent=1)
    context_manager = ContextManager(
        max_tokens=1,
        keep_head=0,
        keep_tail=10,
        max_tool_chars=1000,
    )
    messages = [{"role": "user", "content": "x" * 40} for _ in range(3)]

    context_manager.compact(
        messages, client=client, compact_manager=compact_manager
    )

    assert messages[0]["content"].endswith("auto summary")


def test_agent_loop_auto_compact_still_answers() -> None:
    client = MockLLMClient()
    client.add_text_response("summary")
    client.add_text_response("done")
    context_manager = ContextManager(max_tokens=1, keep_head=0, keep_tail=10)
    compact_manager = CompactManager(keep_recent=1)
    messages = [{"role": "user", "content": "x" * 40}]

    result = agent_loop(
        messages,
        client=client,
        context_manager=context_manager,
        compact_manager=compact_manager,
    )

    assert result == "done"

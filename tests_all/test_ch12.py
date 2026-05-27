"""Tests for ch12: Subagent."""

from __future__ import annotations

from tiny_claude_code.subagent import SubAgent, SubAgentTool
from tiny_claude_code.tools import ToolRegistry, create_default_registry
from conftest import MockLLMClient


def test_subagent_spawn_returns_summary() -> None:
    client = MockLLMClient()
    client.add_text_response("subtask complete")
    subagent = SubAgent(client=client)

    result = subagent.spawn("Inspect one file")

    assert result == "subtask complete"
    assert "focused subagent" in client.last_system


def test_subagent_max_turns_guard() -> None:
    client = MockLLMClient()
    client.add_tool_use_response("echo", {"text": "again"})
    client.add_tool_use_response("echo", {"text": "again"})
    tools = {"echo": {"schema": {"name": "echo"}, "handler": lambda text: text}}
    subagent = SubAgent(client=client, tools=tools, max_turns=1)

    result = subagent.spawn("Loop")

    assert "maximum number of turns" in result


def test_recursive_subagent_is_rejected() -> None:
    subagent = SubAgent(client=MockLLMClient(), depth=1)

    assert "recursive" in subagent.spawn("delegate again")


def test_subagent_tool_executes_task() -> None:
    client = MockLLMClient()
    client.add_text_response("done")
    tool = SubAgentTool(client=client)

    assert tool.execute("Summarize") == "done"


def test_subagent_removes_subagent_tool_from_child_registry(tmp_path) -> None:
    client = MockLLMClient()
    client.add_text_response("child ok")
    registry = create_default_registry(tmp_path, client=client)
    subagent = SubAgent(client=client, tools=registry)

    child_tools = subagent._without_subagent_tool()
    names = {schema["name"] for schema in child_tools.get_schemas()}

    assert "SubAgent" not in names


def test_default_registry_includes_subagent_when_client_is_present(tmp_path) -> None:
    registry = create_default_registry(tmp_path, client=MockLLMClient())

    names = {schema["name"] for schema in registry.get_schemas()}

    assert "SubAgent" in names

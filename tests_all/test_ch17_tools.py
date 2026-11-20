"""Tests for ch17: goal tools and registry wiring."""

from __future__ import annotations

from conftest import MockLLMClient
from tiny_claude_code.goal import GoalManager
from tiny_claude_code.tools import (
    GoalCheckpointTool,
    GoalDoneTool,
    ToolRegistry,
    create_default_registry,
)


def test_goal_done_tool_marks_goal_done():
    manager = GoalManager(MockLLMClient())
    manager.start("Ship it")
    tool = GoalDoneTool(manager)

    output = tool.execute("Shipped the feature")

    assert "Goal marked complete" in output
    assert manager.status()["status"] == "done"
    assert manager.status()["summary"] == "Shipped the feature"


def test_goal_checkpoint_tool_records_note():
    manager = GoalManager(MockLLMClient())
    manager.start("Ship it")
    tool = GoalCheckpointTool(manager)

    assert tool.execute("first") == "Checkpoint recorded (1 total)."
    assert tool.execute("second") == "Checkpoint recorded (2 total)."
    assert manager.status()["checkpoints"] == ["first", "second"]


def test_goal_done_without_active_goal_returns_tool_error():
    manager = GoalManager(MockLLMClient())
    registry = ToolRegistry()
    registry.register(GoalDoneTool(manager))

    output = registry.dispatch("GoalDone", {"summary": "nothing"})

    assert output.startswith("Error: tool 'GoalDone' failed:")
    assert "no active goal" in output


def test_goal_tool_schemas_are_exposed():
    manager = GoalManager(MockLLMClient())
    done = GoalDoneTool(manager).schema
    checkpoint = GoalCheckpointTool(manager).schema

    assert done["name"] == "GoalDone"
    assert done["input_schema"]["required"] == ["summary"]
    assert checkpoint["name"] == "GoalCheckpoint"
    assert checkpoint["input_schema"]["required"] == ["note"]


def test_default_registry_registers_goal_tools(tmp_path):
    manager = GoalManager(MockLLMClient())
    registry = create_default_registry(workspace=tmp_path, goal_manager=manager)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert {"GoalDone", "GoalCheckpoint"} <= names


def test_default_registry_skips_goal_tools_without_manager(tmp_path):
    registry = create_default_registry(workspace=tmp_path)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert "GoalDone" not in names
    assert "GoalCheckpoint" not in names

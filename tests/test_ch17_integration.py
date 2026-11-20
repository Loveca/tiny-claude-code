"""End-to-end tests for ch17: goal runs inside the default harness."""

from __future__ import annotations

from conftest import MockLLMClient
from tiny_claude_code.cli import handle_goal_command
from tiny_claude_code.goal import GoalManager
from tiny_claude_code.tools import create_default_registry


def test_goal_run_writes_file_and_completes(tmp_path):
    client = MockLLMClient()
    client.add_tool_use_response(
        "write", {"path": "result.txt", "content": "goal done"}
    )
    client.add_tool_use_response("GoalDone", {"summary": "wrote result.txt"})
    manager = GoalManager(client, max_turns=4)
    registry = create_default_registry(workspace=tmp_path, goal_manager=manager)
    messages: list[dict] = []

    result = manager.run(messages, registry, "Create result.txt")

    assert result["status"] == "done"
    assert result["turns"] == 2
    assert (tmp_path / "result.txt").read_text(encoding="utf-8") == "goal done"
    tool_results = [
        block
        for message in messages
        if isinstance(message["content"], list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]
    assert any("Wrote result.txt" in block["content"] for block in tool_results)


def test_handle_goal_command_runs_objective(tmp_path):
    client = MockLLMClient()
    client.add_tool_use_response("GoalDone", {"summary": "polished README"})
    manager = GoalManager(client)
    registry = create_default_registry(workspace=tmp_path, goal_manager=manager)
    messages: list[dict] = []

    output = handle_goal_command(
        manager, registry, messages, "sys", "/goal polish README"
    )

    assert output.startswith("Goal done after 1 turn(s).")
    assert "Summary: polished README" in output
    assert messages
    assert manager.status()["objective"] == "polish README"


def test_handle_goal_command_reports_status(tmp_path):
    manager = GoalManager(MockLLMClient())
    registry = create_default_registry(workspace=tmp_path, goal_manager=manager)

    assert "No goal has been started" in handle_goal_command(
        manager, registry, [], "sys", "/goal"
    )

    manager.start("Ship it")
    manager.checkpoint("halfway")
    manager.finish("shipped")

    status = handle_goal_command(manager, registry, [], "sys", "/goal")
    assert "Status: done (0/12 turns)" in status
    assert "Summary: shipped" in status

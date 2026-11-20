"""Tests for ch17: the goal loop."""

from __future__ import annotations

import pytest

from conftest import MockLLMClient
from tiny_claude_code.goal import GoalError, GoalManager
from tiny_claude_code.hooks import HookSystem, StopLogHook
from tiny_claude_code.tools import ToolRegistry
from tiny_claude_code.tools.goal import GoalCheckpointTool, GoalDoneTool


class RecordingClient(MockLLMClient):
    """Mock client that keeps every request for message assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[list[dict]] = []

    def chat(self, messages, tools=None, max_tokens=8000, system=None):
        self.requests.append(list(messages))
        return super().chat(
            messages, tools=tools, max_tokens=max_tokens, system=system
        )


class FailingClient:
    def chat(self, *args, **kwargs):
        raise RuntimeError("boom")


def make_registry(manager: GoalManager) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(GoalDoneTool(manager))
    registry.register(GoalCheckpointTool(manager))
    return registry


def goal_prompt_text(messages: list[dict]) -> str:
    parts = []
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            parts.append(content)
        else:
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return "\n".join(parts)


def test_start_rejects_empty_objective():
    manager = GoalManager(MockLLMClient())
    with pytest.raises(GoalError, match="cannot be empty"):
        manager.start("   ")


def test_start_rejects_overlapping_goal():
    manager = GoalManager(MockLLMClient())
    manager.start("first goal")
    with pytest.raises(GoalError, match="already active"):
        manager.start("second goal")


def test_run_starts_goal_from_objective(mock_client: MockLLMClient):
    manager = GoalManager(mock_client)
    mock_client.add_tool_use_response("GoalDone", {"summary": "done"})
    messages: list[dict] = []

    result = manager.run(messages, make_registry(manager), "Fix the tests")

    assert result["status"] == "done"
    assert result["turns"] == 1
    assert result["summary"] == "done"
    assert manager.status()["objective"] == "Fix the tests"
    assert messages[0]["role"] == "user"
    assert "Fix the tests" in messages[0]["content"]


def test_goal_done_ends_run_without_continuation(mock_client: MockLLMClient):
    manager = GoalManager(mock_client)
    mock_client.add_tool_use_response("GoalDone", {"summary": "All tests pass"})
    messages: list[dict] = []

    manager.run(messages, make_registry(manager), "Run the suite")

    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"][0]["type"] == "tool_result"
    assert "Continue working toward the goal" not in goal_prompt_text(messages)
    assert mock_client._call_count == 1


def test_tool_results_carry_continuation_and_checkpoints(mock_client: MockLLMClient):
    client = RecordingClient()
    client.add_tool_use_response("GoalCheckpoint", {"note": "read failing test"})
    client.add_tool_use_response("GoalDone", {"summary": "fixed"})
    manager = GoalManager(client, max_turns=2)
    messages: list[dict] = []

    result = manager.run(messages, make_registry(manager), "Fix the bug")

    assert result["status"] == "done"
    assert result["turns"] == 2
    assert result["checkpoints"] == ["read failing test"]
    assert "Progress so far:" in goal_prompt_text(messages)
    assert "- read failing test" in goal_prompt_text(messages)
    second_request = client.requests[1]
    continuation = second_request[-1]["content"]
    assert isinstance(continuation, list)
    assert continuation[-1]["type"] == "text"
    assert "Turns remaining: 1" in continuation[-1]["text"]


def test_budget_exhaustion_pauses_goal(mock_client: MockLLMClient):
    manager = GoalManager(mock_client, max_turns=2)
    mock_client.add_tool_use_response("GoalCheckpoint", {"note": "step one"})
    mock_client.add_tool_use_response("GoalCheckpoint", {"note": "step two"})

    result = manager.run([], make_registry(manager), "Endless task")

    assert result["status"] == "paused"
    assert result["turns"] == 2
    assert "turn budget exhausted" in result["reason"]
    assert manager.status()["status"] == "paused"


def test_text_only_turns_hit_idle_guard(mock_client: MockLLMClient):
    manager = GoalManager(mock_client, max_turns=5, max_idle_turns=2)
    mock_client.add_text_response("Still thinking about it.")
    mock_client.add_text_response("No tools needed, surely.")

    result = manager.run([], make_registry(manager), "Think forever")

    assert result["status"] == "paused"
    assert result["turns"] == 2
    assert "no tool calls" in result["reason"]


def test_client_error_marks_goal_failed():
    manager = GoalManager(FailingClient())
    result = manager.run([], make_registry(manager), "Die")
    assert result["status"] == "failed"
    assert result["reason"] == "boom"
    assert manager.status()["status"] == "failed"


def test_missing_goal_done_tool_is_rejected(mock_client: MockLLMClient):
    manager = GoalManager(mock_client)
    with pytest.raises(GoalError, match="GoalDone tool is not registered"):
        manager.run([], ToolRegistry(), "Impossible")


def test_finish_and_checkpoint_need_active_goal():
    manager = GoalManager(MockLLMClient())
    with pytest.raises(GoalError, match="no active goal"):
        manager.finish("done")
    with pytest.raises(GoalError, match="no active goal"):
        manager.checkpoint("note")


def test_finish_rejects_empty_summary():
    manager = GoalManager(MockLLMClient())
    goal = manager.start("Something")
    with pytest.raises(GoalError, match="summary cannot be empty"):
        manager.finish("  ")
    assert goal.status == "active"


def test_checkpoint_returns_running_total():
    manager = GoalManager(MockLLMClient())
    manager.start("Something")
    assert manager.checkpoint("first") == 1
    assert manager.checkpoint("second") == 2


def test_pre_tool_use_hook_can_deny_goal_done(mock_client: MockLLMClient):
    hooks = HookSystem()
    hooks.register("PreToolUse", lambda **_: "denied by policy")
    manager = GoalManager(mock_client, hooks=hooks, max_turns=1)
    mock_client.add_tool_use_response("GoalDone", {"summary": "done"})
    messages: list[dict] = []

    result = manager.run(messages, make_registry(manager), "Do the thing")

    assert result["status"] == "paused"
    tool_result = messages[-1]["content"][0]
    assert tool_result["content"] == "denied by policy"
    assert manager.status()["summary"] == ""


def test_stop_hook_fires_once(mock_client: MockLLMClient):
    stop_log = StopLogHook()
    hooks = HookSystem()
    hooks.register("Stop", stop_log.stop)
    manager = GoalManager(mock_client, hooks=hooks)
    mock_client.add_tool_use_response("GoalDone", {"summary": "finished"})

    manager.run([], make_registry(manager), "Do the thing")

    assert stop_log.responses == ["finished"]


def test_context_manager_compacts_before_each_turn(mock_client: MockLLMClient):
    class FakeContext:
        def __init__(self) -> None:
            self.calls = 0

        def compact(self, messages, *, client, compact_manager):
            self.calls += 1

    context = FakeContext()
    manager = GoalManager(mock_client, context_manager=context)
    mock_client.add_tool_use_response("GoalDone", {"summary": "done"})

    manager.run([], make_registry(manager), "Do the thing")

    assert context.calls == 1


def test_error_handler_wraps_model_calls(mock_client: MockLLMClient):
    class FakeErrorHandler:
        def __init__(self) -> None:
            self.calls = 0

        def chat(self, client, messages, tools=None, system=None):
            self.calls += 1
            return client.chat(messages, tools=tools, system=system)

    handler = FakeErrorHandler()
    manager = GoalManager(mock_client, error_handler=handler)
    mock_client.add_tool_use_response("GoalDone", {"summary": "done"})

    manager.run([], make_registry(manager), "Do the thing")

    assert handler.calls == 1


def test_system_prompt_is_forwarded(mock_client: MockLLMClient):
    manager = GoalManager(mock_client, system="base system")
    mock_client.add_tool_use_response("GoalDone", {"summary": "done"})

    manager.run([], make_registry(manager), "Do the thing", system="goal system")

    assert mock_client.last_system == "goal system"

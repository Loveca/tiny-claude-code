"""Tests for ch06: Hook System."""

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.hooks import HookSystem, StopLogHook, ToolLogHook
from conftest import MockLLMClient


def test_hooks_run_by_priority() -> None:
    hooks = HookSystem()
    calls: list[str] = []
    hooks.register("UserPromptSubmit", lambda **_: calls.append("low"), priority=0)
    hooks.register("UserPromptSubmit", lambda **_: calls.append("high"), priority=10)

    result = hooks.trigger("UserPromptSubmit", prompt="hello")

    assert result is None
    assert calls == ["high", "low"]


def test_pre_tool_use_denies_tool_execution(mock_client: MockLLMClient) -> None:
    mock_client.add_tool_use_response("echo", {"text": "hello"})
    mock_client.add_text_response("saw denial")
    hooks = HookSystem()
    hooks.register("PreToolUse", lambda **_: "denied by hook")
    called = False

    def handler(text: str) -> str:
        nonlocal called
        called = True
        return text

    messages = [{"role": "user", "content": "echo"}]
    result = agent_loop(
        messages,
        tool_handlers={"echo": {"schema": {"name": "echo"}, "handler": handler}},
        client=mock_client,
        hooks=hooks,
    )

    assert result == "saw denial"
    assert called is False
    assert "denied by hook" in str(messages)


def test_post_tool_use_receives_result(mock_client: MockLLMClient) -> None:
    mock_client.add_tool_use_response("echo", {"text": "hello"})
    mock_client.add_text_response("done")
    hooks = HookSystem()
    log = ToolLogHook()
    hooks.register("PostToolUse", log.post_tool_use)

    agent_loop(
        [{"role": "user", "content": "echo"}],
        tool_handlers={"echo": {"schema": {"name": "echo"}, "handler": lambda text: text}},
        client=mock_client,
        hooks=hooks,
    )

    assert log.entries == [{"tool": "echo", "input": {"text": "hello"}, "result": "hello"}]


def test_stop_hook_fires_on_final_response(mock_client: MockLLMClient) -> None:
    mock_client.add_text_response("done")
    hooks = HookSystem()
    stop_log = StopLogHook()
    hooks.register("Stop", stop_log.stop)

    result = agent_loop([{"role": "user", "content": "hi"}], client=mock_client, hooks=hooks)

    assert result == "done"
    assert stop_log.responses == ["done"]


def test_no_hooks_registered_returns_none() -> None:
    assert HookSystem().trigger("MissingEvent") is None

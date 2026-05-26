"""Tests for ch02: Shell Tool."""

from tiny_claude_code.tools.shell import ShellTool


def test_shell_schema_has_required_command() -> None:
    tool = ShellTool()
    schema = tool.schema

    assert schema["name"] == "bash"
    assert "command" in schema["input_schema"]["required"]


def test_shell_executes_command() -> None:
    tool = ShellTool()

    result = tool.execute("python -c \"print('hello')\"")

    assert "exit_code: 0" in result
    assert "hello" in result


def test_shell_reports_nonzero_exit() -> None:
    tool = ShellTool()

    result = tool.execute("python -c \"import sys; sys.exit(7)\"")

    assert "exit_code: 7" in result


def test_shell_rejects_empty_command() -> None:
    tool = ShellTool()

    result = tool.execute("   ")

    assert "empty" in result.lower()


def test_shell_rejects_too_long_command() -> None:
    tool = ShellTool()

    result = tool.execute("x" * (tool.max_command_length + 1))

    assert "too long" in result.lower()


def test_shell_timeout() -> None:
    tool = ShellTool()

    result = tool.execute("python -c \"import time; time.sleep(2)\"", timeout=1)

    assert "timed out" in result.lower()

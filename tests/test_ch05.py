"""Tests for ch05: Permission System."""

from tiny_claude_code.permissions import PermissionManager


def test_deny_list_blocks_dangerous_shell_command(tmp_path) -> None:
    permissions = PermissionManager(workspace=tmp_path, prompt_user=lambda *_: "y")

    result = permissions.check("bash", {"command": "rm -rf /"})

    assert result is not None
    assert "blocked" in result


def test_path_escape_is_denied(tmp_path) -> None:
    permissions = PermissionManager(workspace=tmp_path, prompt_user=lambda *_: "y")

    result = permissions.check("read", {"path": "../secret.txt"})

    assert result is not None
    assert "escapes workspace" in result


def test_normal_operation_passes_without_prompt(tmp_path) -> None:
    calls = 0

    def prompt(*_):
        nonlocal calls
        calls += 1
        return "n"

    permissions = PermissionManager(workspace=tmp_path, prompt_user=prompt)

    result = permissions.check("read", {"path": "README.md"})

    assert result is None
    assert calls == 0


def test_rule_match_can_be_approved(tmp_path) -> None:
    permissions = PermissionManager(workspace=tmp_path, prompt_user=lambda *_: "y")

    result = permissions.check("bash", {"command": "rm temp.txt"})

    assert result is None


def test_rule_match_can_be_denied(tmp_path) -> None:
    permissions = PermissionManager(workspace=tmp_path, prompt_user=lambda *_: "n")

    result = permissions.check("bash", {"command": "rm temp.txt"})

    assert result is not None
    assert "Permission denied" in result


def test_always_allows_same_arguments_without_prompt(tmp_path) -> None:
    calls = 0

    def prompt(*_):
        nonlocal calls
        calls += 1
        return "always"

    permissions = PermissionManager(workspace=tmp_path, prompt_user=prompt)

    assert permissions.check("bash", {"command": "rm temp.txt"}) is None
    assert permissions.check("bash", {"command": "rm temp.txt"}) is None
    assert calls == 1

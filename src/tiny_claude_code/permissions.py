"""Permission checks for tool execution."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Callable

class PermissionManager:
    """Three-gate permission checker for tool calls."""
    deny_patterns = ('rm -rf /', ':(){:|:&}', 'shutdown', 'reboot', 'mkfs', 'dd if=', '> /dev/sda')
    destructive_shell_tokens = ('rm ', 'del ', 'rmdir ', 'chmod 777', '> /etc/')

    def __init__(self, workspace: str | Path | None=None, prompt_user: Callable[[str, dict[str, Any], str], str] | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def check(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Return a denial message, or None when the tool may run."""
        raise NotImplementedError('TODO: implement check')

    def as_hook(self, tool_name: str, tool_input: dict[str, Any], **_: Any) -> str | None:
        raise NotImplementedError('TODO: implement as_hook')

    def _check_deny_list(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        raise NotImplementedError('TODO: implement _check_deny_list')

    def _check_rules(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        raise NotImplementedError('TODO: implement _check_rules')

    def _path_escapes_workspace(self, path: str) -> bool:
        raise NotImplementedError('TODO: implement _path_escapes_workspace')

    def _prompt_user(self, tool_name: str, tool_input: dict[str, Any], reason: str) -> str:
        raise NotImplementedError('TODO: implement _prompt_user')

    def _remember_key(self, tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
        raise NotImplementedError('TODO: implement _remember_key')

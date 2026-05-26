"""Permission checks for tool execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


class PermissionManager:
    """Three-gate permission checker for tool calls."""

    deny_patterns = (
        "rm -rf /",
        ":(){:|:&}",
        "shutdown",
        "reboot",
        "mkfs",
        "dd if=",
        "> /dev/sda",
    )

    destructive_shell_tokens = (
        "rm ",
        "del ",
        "rmdir ",
        "chmod 777",
        "> /etc/",
    )

    def __init__(
        self,
        workspace: str | Path | None = None,
        prompt_user: Callable[[str, dict[str, Any], str], str] | None = None,
    ) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.prompt_user = prompt_user or self._prompt_user
        self._always_allow: set[tuple[str, str]] = set()

    def check(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        """Return a denial message, or None when the tool may run."""
        denied = self._check_deny_list(tool_name, tool_input)
        if denied:
            return denied

        rule_reason = self._check_rules(tool_name, tool_input)
        if not rule_reason:
            return None

        key = self._remember_key(tool_name, tool_input)
        if key in self._always_allow:
            return None

        decision = self.prompt_user(tool_name, tool_input, rule_reason).strip().lower()
        if decision == "always":
            self._always_allow.add(key)
            return None
        if decision in {"y", "yes", "allow"}:
            return None
        return f"Permission denied: {rule_reason}"

    def as_hook(self, tool_name: str, tool_input: dict[str, Any], **_: Any) -> str | None:
        return self.check(tool_name, tool_input)

    def _check_deny_list(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        if tool_name in {"read", "write", "search"}:
            path = str(tool_input.get("path", "."))
            if self._path_escapes_workspace(path):
                return f"Permission denied: path escapes workspace: {path}"

        if tool_name != "bash":
            return None
        command = str(tool_input.get("command", ""))
        for pattern in self.deny_patterns:
            if pattern in command:
                return f"Permission denied: '{pattern}' is blocked"
        return None

    def _check_rules(self, tool_name: str, tool_input: dict[str, Any]) -> str | None:
        if tool_name == "bash":
            command = str(tool_input.get("command", ""))
            if any(token in command for token in self.destructive_shell_tokens):
                return "potentially destructive shell command"
        return None

    def _path_escapes_workspace(self, path: str) -> bool:
        target = (self.workspace / path).resolve()
        return target != self.workspace and self.workspace not in target.parents

    def _prompt_user(self, tool_name: str, tool_input: dict[str, Any], reason: str) -> str:
        print(f"Permission required: {reason}")
        print(f"Tool: {tool_name}({tool_input})")
        return input("Allow? [y/N/always] ")

    def _remember_key(self, tool_name: str, tool_input: dict[str, Any]) -> tuple[str, str]:
        return tool_name, repr(sorted(tool_input.items()))

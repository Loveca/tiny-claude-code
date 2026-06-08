"""Shell command tool."""
from __future__ import annotations
from pathlib import Path
import subprocess
from typing import Any
from tiny_claude_code.tools.base import Tool

class ShellTool(Tool):
    name = 'bash'
    max_command_length = 2000

    def __init__(self, workspace: str | Path | None=None, max_output_chars: int=50000) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.max_output_chars = max_output_chars

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Run a shell command in the current workspace.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run."},
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds.",
                        "default": 30,
                    },
                },
                "required": ["command"],
            },
        }

    def validate_command(self, command: str) -> str | None:
        if not command or not command.strip():
            return "Error: command cannot be empty"
        if len(command) > self.max_command_length:
            return "Error: command is too long"
        return None

    def execute(self, command: str, timeout: int=30) -> str:
        error = self.validate_command(command)
        if error:
            return error

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout}s"

        output = [f"exit_code: {result.returncode}"]
        if result.stdout:
            output.append(f"stdout:\n{result.stdout.rstrip()}")
        if result.stderr:
            output.append(f"stderr:\n{result.stderr.rstrip()}")
        if len(output) == 1:
            output.append("(no output)")
        return self._truncate("\n".join(output))

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + "\n[truncated]"

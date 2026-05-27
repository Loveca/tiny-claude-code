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
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def validate_command(self, command: str) -> str | None:
        raise NotImplementedError('TODO: implement validate_command')

    def execute(self, command: str, timeout: int=30) -> str:
        raise NotImplementedError('TODO: implement execute')

    def _truncate(self, text: str) -> str:
        raise NotImplementedError('TODO: implement _truncate')

"""File write and edit tool."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.tools.base import Tool

class WriteTool(Tool):
    name = 'write'

    def __init__(self, workspace: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def safe_path(self, path: str, workspace: str | Path | None=None) -> Path:
        raise NotImplementedError('TODO: implement safe_path')

    def execute(self, path: str, content: str | None=None, old_text: str | None=None, new_text: str | None=None, workspace: str | None=None) -> str:
        raise NotImplementedError('TODO: implement execute')

    def _edit(self, target: Path, display_path: str, old_text: str, new_text: str) -> str:
        raise NotImplementedError('TODO: implement _edit')

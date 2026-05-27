"""File and directory read tool."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.tools.base import Tool

class ReadTool(Tool):
    name = 'read'

    def __init__(self, workspace: str | Path | None=None, max_output_chars: int=50000) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def safe_path(self, path: str, workspace: str | Path | None=None) -> Path:
        raise NotImplementedError('TODO: implement safe_path')

    def execute(self, path: str, offset: int=0, limit: int | None=None, workspace: str | None=None) -> str:
        raise NotImplementedError('TODO: implement execute')

    def _truncate(self, text: str) -> str:
        raise NotImplementedError('TODO: implement _truncate')

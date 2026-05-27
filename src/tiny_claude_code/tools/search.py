"""File glob and text search tool."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.tools.base import Tool

class SearchTool(Tool):
    name = 'search'

    def __init__(self, workspace: str | Path | None=None, max_results: int=200, max_output_chars: int=50000) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def safe_path(self, path: str, workspace: str | Path | None=None) -> Path:
        raise NotImplementedError('TODO: implement safe_path')

    def execute(self, pattern: str, path: str='.', type: str='glob', workspace: str | None=None) -> str:
        raise NotImplementedError('TODO: implement execute')

    def _glob(self, root: Path, pattern: str) -> str:
        raise NotImplementedError('TODO: implement _glob')

    def _grep(self, root: Path, pattern: str) -> str:
        raise NotImplementedError('TODO: implement _grep')

    def _format_matches(self, matches: list[str], truncated: bool=False) -> str:
        raise NotImplementedError('TODO: implement _format_matches')

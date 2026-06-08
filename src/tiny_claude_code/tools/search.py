"""File glob and text search tool."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.tools.base import Tool

class SearchTool(Tool):
    name = 'search'

    def __init__(self, workspace: str | Path | None=None, max_results: int=200, max_output_chars: int=50000) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.max_results = max_results
        self.max_output_chars = max_output_chars

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Search files by glob pattern or text content.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "type": {
                        "type": "string",
                        "enum": ["glob", "grep"],
                        "default": "glob",
                    },
                },
                "required": ["pattern"],
            },
        }

    def safe_path(self, path: str, workspace: str | Path | None=None) -> Path:
        root = Path(workspace).resolve() if workspace is not None else self.workspace
        target = (root / path).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"path escapes workspace: {path}")
        return target

    def execute(self, pattern: str, path: str='.', type: str='glob', workspace: str | None=None) -> str:
        try:
            root = self.safe_path(path, workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if not root.exists():
            return f"Error: path not found: {path}"
        if type == "glob":
            return self._glob(root, pattern)
        if type == "grep":
            return self._grep(root, pattern)
        return f"Error: unknown search type: {type}"

    def _glob(self, root: Path, pattern: str) -> str:
        matches = sorted(str(path.relative_to(root)) for path in root.rglob(pattern))
        return self._format_matches(matches)

    def _grep(self, root: Path, pattern: str) -> str:
        matches = []
        files = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for file_path in files:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            relative_root = root if root.is_dir() else root.parent
            for line_no, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append(f"{file_path.relative_to(relative_root)}:{line_no}: {line}")
                    if len(matches) >= self.max_results:
                        return self._format_matches(matches, truncated=True)
        return self._format_matches(matches)

    def _format_matches(self, matches: list[str], truncated: bool=False) -> str:
        if not matches:
            return "(no matches)"
        visible = matches[: self.max_results]
        text = "\n".join(visible)
        if truncated or len(matches) > self.max_results:
            text += "\n[truncated]"
        if len(text) > self.max_output_chars:
            text = text[: self.max_output_chars] + "\n[truncated]"
        return text

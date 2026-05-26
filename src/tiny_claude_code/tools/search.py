"""File glob and text search tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_claude_code.tools.base import Tool


class SearchTool(Tool):
    name = "search"

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
                    "type": {"type": "string", "enum": ["glob", "grep"], "default": "glob"},
                },
                "required": ["pattern"],
            },
        }

    def safe_path(self, path: str, workspace: str | Path | None = None) -> Path:
        root = Path(workspace or Path.cwd()).resolve()
        target = (root / path).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"path escapes workspace: {path}")
        return target

    def execute(
        self,
        pattern: str,
        path: str = ".",
        type: str = "glob",
        workspace: str | None = None,
    ) -> str:
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
        return "\n".join(matches) if matches else "(no matches)"

    def _grep(self, root: Path, pattern: str) -> str:
        matches = []
        files = [root] if root.is_file() else [p for p in root.rglob("*") if p.is_file()]
        for file_path in files:
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_no, line in enumerate(lines, 1):
                if pattern in line:
                    matches.append(f"{file_path.relative_to(root if root.is_dir() else root.parent)}:{line_no}: {line}")
        return "\n".join(matches) if matches else "(no matches)"

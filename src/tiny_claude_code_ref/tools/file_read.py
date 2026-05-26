"""File and directory read tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_claude_code_ref.tools.base import Tool


class ReadTool(Tool):
    name = "read"

    def __init__(self, workspace: str | Path | None = None, max_output_chars: int = 50000) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.max_output_chars = max_output_chars

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Read a file or list a directory inside the workspace.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        }

    def safe_path(self, path: str, workspace: str | Path | None = None) -> Path:
        root = Path(workspace).resolve() if workspace is not None else self.workspace
        target = (root / path).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"path escapes workspace: {path}")
        return target

    def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int | None = None,
        workspace: str | None = None,
    ) -> str:
        try:
            target = self.safe_path(path, workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if not target.exists():
            return f"Error: path not found: {path}"
        if target.is_dir():
            entries = sorted(item.name + ("/" if item.is_dir() else "") for item in target.iterdir())
            return self._truncate("\n".join(entries) if entries else "(empty directory)")

        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return f"Error: file is not valid UTF-8: {path}"

        start = max(offset, 0)
        end = None if limit is None else start + max(limit, 0)
        selected = lines[start:end]
        return self._truncate("\n".join(selected))

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + "\n[truncated]"


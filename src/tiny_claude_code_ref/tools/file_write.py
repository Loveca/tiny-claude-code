"""File write and edit tool."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_claude_code_ref.tools.base import Tool


class WriteTool(Tool):
    name = "write"

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Write a file or edit a file by exact text replacement.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                },
                "required": ["path"],
                "oneOf": [
                    {"required": ["path", "content"]},
                    {"required": ["path", "old_text", "new_text"]},
                ],
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
        content: str | None = None,
        old_text: str | None = None,
        new_text: str | None = None,
        workspace: str | None = None,
    ) -> str:
        try:
            target = self.safe_path(path, workspace)
        except ValueError as exc:
            return f"Error: {exc}"

        if content is not None and old_text is not None:
            return "Error: provide either content or old_text/new_text, not both"

        if old_text is not None or new_text is not None:
            if old_text is None or new_text is None:
                return "Error: both old_text and new_text are required for edit"
            return self._edit(target, path, old_text, new_text or "")

        if content is None:
            return "Error: content is required when old_text is not provided"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {path}"

    def _edit(self, target: Path, display_path: str, old_text: str, new_text: str) -> str:
        if not target.exists():
            return f"Error: file not found: {display_path}"
        text = target.read_text(encoding="utf-8")
        if old_text not in text:
            return "Error: old_text not found"
        target.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {display_path}"


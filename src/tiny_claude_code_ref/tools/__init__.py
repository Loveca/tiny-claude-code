"""Tool registry and default tool set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_claude_code_ref.tools.base import Tool
from tiny_claude_code_ref.tools.file_read import ReadTool
from tiny_claude_code_ref.tools.file_write import WriteTool
from tiny_claude_code_ref.tools.search import SearchTool
from tiny_claude_code_ref.tools.shell import ShellTool


class ToolRegistry:
    """Name-based registry for tool schemas and execution handlers."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict[str, Any]]:
        return [tool.schema for tool in self._tools.values()]

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'"
        try:
            return str(tool.execute(**tool_input))
        except TypeError as exc:
            return f"Error: invalid input for tool '{name}': {exc}"
        except Exception as exc:
            return f"Error: tool '{name}' failed: {exc}"


def create_default_registry(workspace: str | Path | None = None) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(ShellTool(workspace=workspace))
    registry.register(ReadTool(workspace=workspace))
    registry.register(WriteTool(workspace=workspace))
    registry.register(SearchTool(workspace=workspace))
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "ShellTool",
    "ReadTool",
    "WriteTool",
    "SearchTool",
    "create_default_registry",
]


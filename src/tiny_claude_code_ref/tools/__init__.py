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


def create_default_registry(
    workspace: str | Path | None = None,
    client: Any = None,
    task_manager: Any = None,
    background_manager: Any = None,
    cron_scheduler: Any = None,
) -> ToolRegistry:
    from tiny_claude_code_ref.background import (
        BackgroundManager,
        BackgroundPollTool,
        BackgroundSubmitTool,
    )
    from tiny_claude_code_ref.subagent import SubAgentTool
    from tiny_claude_code_ref.tasks import TaskManager, TodoWriteTool
    from tiny_claude_code_ref.cron import CronScheduler, CronScheduleTool

    registry = ToolRegistry()
    registry.register(ShellTool(workspace=workspace))
    registry.register(ReadTool(workspace=workspace))
    registry.register(WriteTool(workspace=workspace))
    registry.register(SearchTool(workspace=workspace))
    task_manager = task_manager or TaskManager(workspace=workspace)
    background_manager = background_manager or BackgroundManager(workspace=workspace)
    cron_scheduler = cron_scheduler or CronScheduler(workspace=workspace)
    registry.register(TodoWriteTool(task_manager))
    registry.register(BackgroundSubmitTool(background_manager))
    registry.register(BackgroundPollTool(background_manager))
    registry.register(CronScheduleTool(cron_scheduler))
    if client is not None:
        registry.register(SubAgentTool(client=client, tools=registry))
    return registry


__all__ = [
    "Tool",
    "ToolRegistry",
    "ShellTool",
    "ReadTool",
    "WriteTool",
    "SearchTool",
    "TaskManager",
    "TodoWriteTool",
    "SubAgentTool",
    "BackgroundManager",
    "BackgroundSubmitTool",
    "BackgroundPollTool",
    "CronScheduler",
    "CronScheduleTool",
    "create_default_registry",
]


def __getattr__(name: str) -> Any:
    if name in {"TaskManager", "TodoWriteTool"}:
        from tiny_claude_code_ref.tasks import TaskManager, TodoWriteTool

        return {"TaskManager": TaskManager, "TodoWriteTool": TodoWriteTool}[name]
    if name == "SubAgentTool":
        from tiny_claude_code_ref.subagent import SubAgentTool

        return SubAgentTool
    if name in {"BackgroundManager", "BackgroundSubmitTool", "BackgroundPollTool"}:
        from tiny_claude_code_ref.background import (
            BackgroundManager,
            BackgroundPollTool,
            BackgroundSubmitTool,
        )

        return {
            "BackgroundManager": BackgroundManager,
            "BackgroundSubmitTool": BackgroundSubmitTool,
            "BackgroundPollTool": BackgroundPollTool,
        }[name]
    if name in {"CronScheduler", "CronScheduleTool"}:
        from tiny_claude_code_ref.cron import CronScheduleTool, CronScheduler

        return {"CronScheduler": CronScheduler, "CronScheduleTool": CronScheduleTool}[
            name
        ]
    raise AttributeError(name)


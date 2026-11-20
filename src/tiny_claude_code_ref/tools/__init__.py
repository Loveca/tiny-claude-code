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
    plugin_dir: str | Path | None = None,
    team_manager: Any = None,
    goal_manager: Any = None,
) -> ToolRegistry:
    from tiny_claude_code_ref.background import (
        BackgroundManager,
        BackgroundPollTool,
        BackgroundSubmitTool,
    )
    from tiny_claude_code_ref.subagent import SubAgentTool
    from tiny_claude_code_ref.tasks import TaskManager, TodoWriteTool
    from tiny_claude_code_ref.cron import CronScheduler, CronScheduleTool
    from tiny_claude_code_ref.tools.goal import GoalCheckpointTool, GoalDoneTool
    from tiny_claude_code_ref.tools.plugin import PluginLoader
    from tiny_claude_code_ref.tools.team import (
        TeamInboxTool,
        TeamSendTool,
        TeamShutdownTool,
        TeamSpawnTool,
        TeamStatusTool,
        TeamWaitTool,
        WorktreeMergeTool,
    )

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
    if goal_manager is not None:
        registry.register(GoalDoneTool(goal_manager))
        registry.register(GoalCheckpointTool(goal_manager))
    if team_manager is not None:
        lead = team_manager.LEAD
        registry.register(TeamSpawnTool(team_manager))
        registry.register(TeamSendTool(team_manager, lead))
        registry.register(TeamInboxTool(team_manager, lead))
        registry.register(TeamStatusTool(team_manager))
        registry.register(TeamWaitTool(team_manager))
        registry.register(TeamShutdownTool(team_manager))
        registry.register(WorktreeMergeTool(team_manager))
    if client is not None:
        registry.register(SubAgentTool(client=client, tools=registry))
    PluginLoader(plugin_dir).load_plugins(registry)
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
    "PluginLoader",
    "TeamSpawnTool",
    "TeamSendTool",
    "TeamInboxTool",
    "TeamStatusTool",
    "TeamWaitTool",
    "TeamShutdownTool",
    "WorktreeMergeTool",
    "GoalDoneTool",
    "GoalCheckpointTool",
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
    if name == "PluginLoader":
        from tiny_claude_code_ref.tools.plugin import PluginLoader

        return PluginLoader
    if name in {
        "TeamSpawnTool",
        "TeamSendTool",
        "TeamInboxTool",
        "TeamStatusTool",
        "TeamWaitTool",
        "TeamShutdownTool",
        "WorktreeMergeTool",
    }:
        from tiny_claude_code_ref.tools import team as team_tools

        return getattr(team_tools, name)
    if name in {"GoalDoneTool", "GoalCheckpointTool"}:
        from tiny_claude_code_ref.tools import goal as goal_tools

        return getattr(goal_tools, name)
    raise AttributeError(name)


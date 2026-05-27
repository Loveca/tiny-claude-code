"""Tool registry and default tool set."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.tools.base import Tool
from tiny_claude_code.tools.file_read import ReadTool
from tiny_claude_code.tools.file_write import WriteTool
from tiny_claude_code.tools.search import SearchTool
from tiny_claude_code.tools.shell import ShellTool

class ToolRegistry:
    """Name-based registry for tool schemas and execution handlers."""

    def __init__(self) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def register(self, tool: Tool) -> None:
        raise NotImplementedError('TODO: implement register')

    def get_schemas(self) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement get_schemas')

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> str:
        raise NotImplementedError('TODO: implement dispatch')

def create_default_registry(workspace: str | Path | None=None, client: Any=None, task_manager: Any=None, background_manager: Any=None, cron_scheduler: Any=None, plugin_dir: str | Path | None=None) -> ToolRegistry:
    raise NotImplementedError('TODO: implement create_default_registry')
__all__ = ['Tool', 'ToolRegistry', 'ShellTool', 'ReadTool', 'WriteTool', 'SearchTool', 'TaskManager', 'TodoWriteTool', 'SubAgentTool', 'BackgroundManager', 'BackgroundSubmitTool', 'BackgroundPollTool', 'CronScheduler', 'CronScheduleTool', 'PluginLoader', 'create_default_registry']

def __getattr__(name: str) -> Any:
    raise NotImplementedError('TODO: implement __getattr__')

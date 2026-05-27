"""Subagent support for isolated delegated work."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from tiny_claude_code.agent import agent_loop
from tiny_claude_code.tools.base import Tool
SUBAGENT_SYSTEM_PROMPT = 'You are a focused subagent. Complete the delegated task with the available tools, then return a concise summary for the parent agent.'

class SubAgent:
    """Run a task in an isolated message history."""

    def __init__(self, client: Any, tools: Any=None, max_turns: int=30, depth: int=0) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def spawn(self, task_description: str) -> str:
        raise NotImplementedError('TODO: implement spawn')

    def _without_subagent_tool(self) -> Any:
        raise NotImplementedError('TODO: implement _without_subagent_tool')

class SubAgentTool(Tool):
    """Expose SubAgent.spawn as a tool."""
    name = 'SubAgent'

    def __init__(self, client: Any, tools: Any=None, max_turns: int=30) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, task: str) -> str:
        raise NotImplementedError('TODO: implement execute')

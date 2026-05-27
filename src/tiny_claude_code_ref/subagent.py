"""Subagent support for isolated delegated work."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tiny_claude_code_ref.agent import agent_loop
from tiny_claude_code_ref.tools.base import Tool


SUBAGENT_SYSTEM_PROMPT = (
    "You are a focused subagent. Complete the delegated task with the available "
    "tools, then return a concise summary for the parent agent."
)


class SubAgent:
    """Run a task in an isolated message history."""

    def __init__(
        self,
        client: Any,
        tools: Any = None,
        max_turns: int = 30,
        depth: int = 0,
    ) -> None:
        self.client = client
        self.tools = tools
        self.max_turns = max_turns
        self.depth = depth

    def spawn(self, task_description: str) -> str:
        if self.depth >= 1:
            return "Error: recursive subagents are not allowed"
        messages = [{"role": "user", "content": task_description}]
        return agent_loop(
            messages,
            tool_handlers=self._without_subagent_tool(),
            client=self.client,
            system=SUBAGENT_SYSTEM_PROMPT,
            max_turns=self.max_turns,
        )

    def _without_subagent_tool(self) -> Any:
        if not hasattr(self.tools, "_tools"):
            return self.tools
        from tiny_claude_code_ref.tools import ToolRegistry

        registry = ToolRegistry()
        for name, tool in self.tools._tools.items():
            if name != "SubAgent":
                registry.register(tool)
        return registry


class SubAgentTool(Tool):
    """Expose SubAgent.spawn as a tool."""

    name = "SubAgent"

    def __init__(self, client: Any, tools: Any = None, max_turns: int = 30) -> None:
        self.client = client
        self.tools = tools
        self.max_turns = max_turns

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Delegate a focused task to an isolated subagent.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task to delegate."}
                },
                "required": ["task"],
            },
        }

    def execute(self, task: str) -> str:
        subagent = SubAgent(
            client=self.client,
            tools=self.tools,
            max_turns=self.max_turns,
            depth=0,
        )
        return subagent.spawn(task)


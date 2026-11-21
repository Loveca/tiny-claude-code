"""Expose MCP server tools as ordinary local tools."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tiny_claude_code_ref.tools.base import Tool

if TYPE_CHECKING:
    from tiny_claude_code_ref.mcp import MCPClient


class MCPTool(Tool):
    """Adapter that forwards one remote MCP tool through the local registry."""

    def __init__(self, client: "MCPClient", definition: dict[str, Any]) -> None:
        name = definition.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("MCP tool definition is missing a name")
        self.client = client
        self.name = name
        self.description = definition.get("description", "")
        self.input_schema = definition.get("inputSchema") or {
            "type": "object",
            "properties": {},
        }

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def execute(self, **kwargs: Any) -> str:
        return self.client.call_tool(self.name, kwargs)


def load_mcp_tools(client: "MCPClient") -> list[MCPTool]:
    """Discover every tool on the server and wrap it for the registry."""
    return [MCPTool(client, definition) for definition in client.list_tools()]
"""Expose MCP server tools as ordinary local tools.

ch18: implement MCPTool and load_mcp_tools.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from tiny_claude_code.tools.base import Tool
if TYPE_CHECKING:
    from tiny_claude_code.mcp import MCPClient

class MCPTool(Tool):
    """Adapter that forwards one remote MCP tool through the local registry."""

    def __init__(self, client: 'MCPClient', definition: dict[str, Any]) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, **kwargs: Any) -> str:
        raise NotImplementedError('TODO: implement execute')

def load_mcp_tools(client: 'MCPClient') -> list[MCPTool]:
    raise NotImplementedError('TODO: implement load_mcp_tools')
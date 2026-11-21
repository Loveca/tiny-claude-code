"""Tests for ch18: adapting MCP tools and registry wiring."""

from __future__ import annotations

import pytest

from tiny_claude_code.mcp import MCPClient
from tiny_claude_code.tools import MCPTool, create_default_registry, load_mcp_tools


class ToolTransport:
    """Fake MCP transport that serves a fixed tool list."""

    def __init__(self, tools: list[dict]) -> None:
        self.tools = tools
        self.calls: list[dict] = []
        self.closed = False

    def start(self) -> None:
        pass

    def request(self, method: str, params: dict | None = None) -> dict:
        if method == "initialize":
            return {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "1.0"},
            }
        if method == "tools/list":
            return {"tools": self.tools}
        if method == "tools/call":
            self.calls.append(params or {})
            name = (params or {}).get("name", "")
            return {"content": [{"type": "text", "text": f"{name}: ok"}]}
        raise AssertionError(f"unexpected method: {method}")

    def notify(self, method: str, params: dict | None = None) -> None:
        pass

    def close(self) -> None:
        self.closed = True


ECHO_TOOL = {
    "name": "echo",
    "description": "Echo text",
    "inputSchema": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}

COUNT_TOOL = {
    "name": "count",
    "description": "Count items",
    "inputSchema": {"type": "object", "properties": {}},
}


def make_client(tools: list[dict]) -> tuple[MCPClient, ToolTransport]:
    transport = ToolTransport(tools)
    client = MCPClient(transport=transport)
    client.start()
    return client, transport


def test_mcp_tool_exposes_remote_schema():
    client, _ = make_client([ECHO_TOOL])
    tool = MCPTool(client, ECHO_TOOL)

    assert tool.name == "echo"
    assert tool.schema == {
        "name": "echo",
        "description": "Echo text",
        "input_schema": ECHO_TOOL["inputSchema"],
    }


def test_mcp_tool_forwards_arguments():
    client, transport = make_client([ECHO_TOOL])
    tool = MCPTool(client, ECHO_TOOL)

    output = tool.execute(text="hello")

    assert output == "echo: ok"
    assert transport.calls == [{"name": "echo", "arguments": {"text": "hello"}}]


def test_mcp_tool_defaults_missing_schema_and_description():
    client, _ = make_client([{"name": "bare"}])
    tool = MCPTool(client, {"name": "bare"})

    assert tool.input_schema == {"type": "object", "properties": {}}
    assert tool.schema["description"] == ""


def test_mcp_tool_rejects_definition_without_name():
    client, _ = make_client([])
    with pytest.raises(ValueError, match="missing a name"):
        MCPTool(client, {"description": "nameless"})


def test_load_mcp_tools_wraps_every_definition():
    client, _ = make_client([ECHO_TOOL, COUNT_TOOL])

    tools = load_mcp_tools(client)

    assert [tool.name for tool in tools] == ["echo", "count"]


def test_default_registry_registers_mcp_tools(tmp_path):
    client, transport = make_client([ECHO_TOOL])
    registry = create_default_registry(workspace=tmp_path, mcp_client=client)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert "echo" in names
    assert registry.dispatch("echo", {"text": "hi"}) == "echo: ok"
    assert transport.calls[-1] == {"name": "echo", "arguments": {"text": "hi"}}


def test_default_registry_without_mcp_client(tmp_path):
    registry = create_default_registry(workspace=tmp_path)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert "echo" not in names
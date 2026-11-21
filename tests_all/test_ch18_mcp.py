"""Tests for ch18: the MCP protocol client."""

from __future__ import annotations

import pytest

from tiny_claude_code.mcp import (
    CLIENT_NAME,
    DEFAULT_PROTOCOL_VERSION,
    MCPClient,
    MCPError,
    StdioTransport,
)


class FakeTransport:
    """In-memory transport that records requests and replays canned results."""

    def __init__(self, results: dict[str, object] | None = None) -> None:
        self.results = results or {}
        self.started = False
        self.closed = False
        self.requests: list[tuple[str, dict]] = []
        self.notifications: list[tuple[str, dict]] = []

    def start(self) -> None:
        self.started = True

    def request(self, method: str, params: dict | None = None) -> dict:
        self.requests.append((method, params or {}))
        if method in self.results:
            result = self.results[method]
            if isinstance(result, Exception):
                raise result
            return result
        if method == "initialize":
            return {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-server", "version": "1.0"},
            }
        if method == "tools/list":
            return {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo text",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"text": {"type": "string"}},
                            "required": ["text"],
                        },
                    }
                ]
            }
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "ok"}], "isError": False}
        raise AssertionError(f"unexpected method: {method}")

    def notify(self, method: str, params: dict | None = None) -> None:
        self.notifications.append((method, params or {}))

    def close(self) -> None:
        self.closed = True


def test_start_performs_handshake():
    transport = FakeTransport()
    client = MCPClient(transport=transport)

    result = client.start()

    assert transport.started
    method, params = transport.requests[0]
    assert method == "initialize"
    assert params["protocolVersion"] == DEFAULT_PROTOCOL_VERSION
    assert params["clientInfo"]["name"] == CLIENT_NAME
    assert params["capabilities"] == {}
    assert transport.notifications == [("notifications/initialized", {})]
    assert result["serverInfo"]["name"] == "fake-server"
    assert client.server_info["name"] == "fake-server"
    assert client.capabilities == {"tools": {}}


def test_start_is_idempotent():
    transport = FakeTransport()
    client = MCPClient(transport=transport)

    client.start()
    client.start()

    assert [method for method, _ in transport.requests] == ["initialize"]


def test_client_requires_command_or_transport():
    with pytest.raises(MCPError, match="command or transport is required"):
        MCPClient()


def test_list_tools_returns_definitions():
    transport = FakeTransport()
    client = MCPClient(transport=transport)
    client.start()

    tools = client.list_tools()

    assert [tool["name"] for tool in tools] == ["echo"]
    assert transport.requests[-1] == ("tools/list", {})


def test_list_tools_rejects_invalid_payload():
    transport = FakeTransport({"tools/list": {"tools": "nope"}})
    client = MCPClient(transport=transport)
    client.start()

    with pytest.raises(MCPError, match="'tools' must be a list"):
        client.list_tools()


def test_call_tool_joins_text_blocks():
    transport = FakeTransport(
        {
            "tools/call": {
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "text", "text": "line two"},
                ]
            }
        }
    )
    client = MCPClient(transport=transport)
    client.start()

    output = client.call_tool("echo", {"text": "hello"})

    assert output == "line one\nline two"
    assert transport.requests[-1] == (
        "tools/call",
        {"name": "echo", "arguments": {"text": "hello"}},
    )


def test_call_tool_marks_error_results():
    transport = FakeTransport(
        {
            "tools/call": {
                "content": [{"type": "text", "text": "boom"}],
                "isError": True,
            }
        }
    )
    client = MCPClient(transport=transport)
    client.start()

    assert client.call_tool("echo", {"text": "x"}) == "Error: boom"


def test_call_tool_falls_back_to_json_without_text_blocks():
    transport = FakeTransport(
        {
            "tools/call": {
                "content": [{"type": "image", "data": "base64..."}],
            }
        }
    )
    client = MCPClient(transport=transport)
    client.start()

    output = client.call_tool("echo", {"text": "x"})

    assert '"type": "image"' in output


def test_call_tool_rejects_empty_name():
    client = MCPClient(transport=FakeTransport())
    with pytest.raises(MCPError, match="tool name cannot be empty"):
        client.call_tool("")


def test_transport_errors_propagate():
    transport = FakeTransport({"tools/list": MCPError("server exploded")})
    client = MCPClient(transport=transport)
    client.start()

    with pytest.raises(MCPError, match="server exploded"):
        client.list_tools()


def test_close_closes_transport():
    transport = FakeTransport()
    client = MCPClient(transport=transport)
    client.start()

    client.close()

    assert transport.closed
    assert client._started is False


class TestStdioTransportValidation:
    def test_empty_command_is_rejected(self):
        with pytest.raises(MCPError, match="command cannot be empty"):
            StdioTransport("")

    def test_request_before_start_is_rejected(self):
        transport = StdioTransport("does-not-matter")
        with pytest.raises(MCPError, match="not started"):
            transport.request("tools/list")

    def test_missing_executable_is_reported(self):
        transport = StdioTransport("definitely-not-a-real-command-xyz")
        with pytest.raises(MCPError, match="failed to start MCP server"):
            transport.start()
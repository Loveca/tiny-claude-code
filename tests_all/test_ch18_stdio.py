"""Tests for ch18: a real MCP server over stdio."""

from __future__ import annotations

import sys
import textwrap

import pytest

from tiny_claude_code.mcp import MCPClient, MCPError


SERVER_SOURCE = textwrap.dedent(
    """
    import json
    import sys

    TOOLS = [
        {
            "name": "echo",
            "description": "Echo the given text.",
            "inputSchema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }
    ]

    def reply(message, result):
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        message = json.loads(line)
        if "id" not in message:
            continue
        method = message.get("method")
        if method == "initialize":
            reply(message, {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "1.0"},
            })
        elif method == "tools/list":
            reply(message, {"tools": TOOLS})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            if name != "echo":
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": f"unknown tool '{name}'"},
                }), flush=True)
                continue
            text = str((params.get("arguments") or {}).get("text", ""))
            reply(message, {
                "content": [{"type": "text", "text": f"echo: {text}"}],
                "isError": False,
            })
        else:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": -32601, "message": "unknown method"},
            }), flush=True)
    """
)


@pytest.fixture
def server_script(tmp_path):
    path = tmp_path / "echo_server.py"
    path.write_text(SERVER_SOURCE, encoding="utf-8")
    return path


def make_client(server_script) -> MCPClient:
    return MCPClient(command=sys.executable, args=["-u", str(server_script)])


def test_stdio_roundtrip(server_script):
    client = make_client(server_script)
    try:
        client.start()
        process = client.transport.process
        tools = client.list_tools()

        assert [tool["name"] for tool in tools] == ["echo"]
        assert client.call_tool("echo", {"text": "hello"}) == "echo: hello"
        assert client.server_info["name"] == "echo-server"
    finally:
        client.close()

    assert process.poll() is not None


def test_stdio_unknown_tool_raises(server_script):
    client = make_client(server_script)
    try:
        client.start()
        with pytest.raises(MCPError, match="unknown tool 'missing'"):
            client.call_tool("missing", {})
    finally:
        client.close()


def test_stdio_server_exit_is_reported(server_script):
    client = make_client(server_script)
    try:
        client.start()
        process = client.transport.process
        process.kill()
        process.wait()
        with pytest.raises(MCPError):
            client.list_tools()
    finally:
        client.close()


def test_stdio_close_is_idempotent(server_script):
    client = make_client(server_script)
    client.start()
    client.close()
    client.close()
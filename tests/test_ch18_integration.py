"""End-to-end tests for ch18: MCP tools inside the agent."""

from __future__ import annotations

import sys
import textwrap

import pytest

from conftest import MockLLMClient
from tiny_claude_code.agent import agent_loop
from tiny_claude_code.cli import _start_mcp_client
from tiny_claude_code.goal import GoalManager
from tiny_claude_code.mcp import MCPClient
from tiny_claude_code.tools import create_default_registry


SERVER_SOURCE = textwrap.dedent(
    """
    import json
    import sys

    TOOLS = [{
        "name": "echo",
        "description": "Echo text",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    }]

    def reply(message, result):
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)

    for line in sys.stdin:
        message = json.loads(line)
        if "id" not in message:
            continue
        method = message.get("method")
        if method == "initialize":
            reply(message, {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "echo-server", "version": "1.0"},
            })
        elif method == "tools/list":
            reply(message, {"tools": TOOLS})
        elif method == "tools/call":
            params = message.get("params") or {}
            text = str((params.get("arguments") or {}).get("text", ""))
            reply(message, {"content": [{"type": "text", "text": text}], "isError": False})
    """
)


@pytest.fixture
def mcp_client(tmp_path):
    script = tmp_path / "echo_server.py"
    script.write_text(SERVER_SOURCE, encoding="utf-8")
    client = MCPClient(command=sys.executable, args=["-u", str(script)])
    client.start()
    yield client
    client.close()


def tool_result_texts(messages: list[dict]) -> list[str]:
    return [
        block.get("content", "")
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict) and block.get("type") == "tool_result"
    ]


def test_agent_loop_calls_remote_tool(tmp_path, mcp_client):
    mock = MockLLMClient()
    mock.add_tool_use_response("echo", {"text": "hello"})
    mock.add_text_response("The server echoed hello.")
    registry = create_default_registry(workspace=tmp_path, mcp_client=mcp_client)
    messages = [{"role": "user", "content": "echo hello"}]

    result = agent_loop(messages, tool_handlers=registry, client=mock)

    assert result == "The server echoed hello."
    assert "hello" in tool_result_texts(messages)


def test_goal_run_uses_remote_tool(tmp_path, mcp_client):
    mock = MockLLMClient()
    mock.add_tool_use_response("echo", {"text": "from goal"})
    mock.add_tool_use_response("GoalDone", {"summary": "echoed"})
    manager = GoalManager(mock, max_turns=3)
    registry = create_default_registry(
        workspace=tmp_path, goal_manager=manager, mcp_client=mcp_client
    )
    messages: list[dict] = []

    result = manager.run(messages, registry, "Echo from goal")

    assert result["status"] == "done"
    assert result["turns"] == 2
    assert result["summary"] == "echoed"
    assert "from goal" in tool_result_texts(messages)


def test_start_mcp_client_returns_none_without_spec():
    assert _start_mcp_client(None) is None


def test_start_mcp_client_reports_bad_command(capsys):
    assert _start_mcp_client("definitely-not-a-real-command-xyz") is None
    assert "MCP server failed to start" in capsys.readouterr().err
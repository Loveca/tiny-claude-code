"""A tiny MCP server used by the ch18 exercises.

Run it through the agent:

    python scripts/dev.py run --ref --mcp "python examples/mcp/echo_server.py"

The server speaks newline-delimited JSON-RPC 2.0 on stdin/stdout. Logs, if any,
must go to stderr: stdout carries the protocol.
"""

from __future__ import annotations

import json
import sys
from typing import Any

TOOLS: list[dict[str, Any]] = [
    {
        "name": "echo",
        "description": "Echo the given text back.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string", "description": "Text to echo."}},
            "required": ["text"],
        },
    },
    {
        "name": "word_count",
        "description": "Count the words in a piece of text.",
        "inputSchema": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
]


def _reply(message: dict[str, Any], result: dict[str, Any]) -> None:
    print(
        json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}),
        flush=True,
    )


def _error(message: dict[str, Any], code: int, detail: str) -> None:
    print(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {"code": code, "message": detail},
            }
        ),
        flush=True,
    )


def _call_tool(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name == "echo":
        text = str(arguments.get("text", ""))
        return {"content": [{"type": "text", "text": text}], "isError": False}
    if name == "word_count":
        text = str(arguments.get("text", ""))
        return {
            "content": [{"type": "text", "text": f"{len(text.split())} words"}],
            "isError": False,
        }
    return {
        "content": [{"type": "text", "text": f"unknown tool '{name}'"}],
        "isError": True,
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            print("ignoring invalid JSON line", file=sys.stderr, flush=True)
            continue
        if "id" not in message:
            continue
        method = message.get("method")
        if method == "initialize":
            _reply(
                message,
                {
                    "protocolVersion": message.get("params", {}).get(
                        "protocolVersion", "2025-06-18"
                    ),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "echo-server", "version": "1.0"},
                },
            )
        elif method == "tools/list":
            _reply(message, {"tools": TOOLS})
        elif method == "tools/call":
            _reply(message, _call_tool(message.get("params") or {}))
        else:
            _error(message, -32601, f"unknown method '{method}'")


if __name__ == "__main__":
    main()
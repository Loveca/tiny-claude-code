"""Minimal MCP (Model Context Protocol) client over JSON-RPC 2.0.

ch18: implement the handshake, tools/list, tools/call, and a stdio transport
with a reader thread and request timeouts.
"""
from __future__ import annotations
import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any
DEFAULT_PROTOCOL_VERSION = '2025-06-18'
CLIENT_NAME = 'tiny-claude-code'
CLIENT_VERSION = '0.1'

class MCPError(RuntimeError):
    """Raised when an MCP server cannot be reached or returns an error."""

class MCPClient:
    """JSON-RPC client for one MCP server."""

    def __init__(self, command: str | None=None, args: list[str] | tuple[str, ...] | None=None, *, transport: Any=None, cwd: str | Path | None=None, env: dict[str, str] | None=None, timeout: float=10.0, client_name: str=CLIENT_NAME, protocol_version: str=DEFAULT_PROTOCOL_VERSION) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def start(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement start')

    def list_tools(self) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement list_tools')

    def call_tool(self, name: str, arguments: dict[str, Any] | None=None) -> str:
        raise NotImplementedError('TODO: implement call_tool')

    def close(self) -> None:
        raise NotImplementedError('TODO: implement close')

class StdioTransport:
    """Run an MCP server as a subprocess and exchange line-delimited JSON."""

    def __init__(self, command: str, args: list[str] | tuple[str, ...]=(), *, cwd: str | Path | None=None, env: dict[str, str] | None=None, timeout: float=10.0, stderr_tail: int=20) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def start(self) -> None:
        raise NotImplementedError('TODO: implement start')

    def request(self, method: str, params: dict[str, Any] | None=None) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement request')

    def notify(self, method: str, params: dict[str, Any] | None=None) -> None:
        raise NotImplementedError('TODO: implement notify')

    def close(self) -> None:
        raise NotImplementedError('TODO: implement close')
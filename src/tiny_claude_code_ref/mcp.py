"""Minimal MCP (Model Context Protocol) client over JSON-RPC 2.0.

ch18: speak MCP over stdio, discover tools, and call them. Remote tools are
adapted into the regular `Tool` interface by `tools/mcp.py`.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any

DEFAULT_PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "tiny-claude-code"
CLIENT_VERSION = "0.1"


class MCPError(RuntimeError):
    """Raised when an MCP server cannot be reached or returns an error."""


class MCPClient:
    """JSON-RPC client for one MCP server.

    The client owns the handshake and tool calls. Starting and stopping the
    process is the transport's job, so tests can replace it with an in-memory
    fake.
    """

    def __init__(
        self,
        command: str | None = None,
        args: list[str] | tuple[str, ...] | None = None,
        *,
        transport: Any = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 10.0,
        client_name: str = CLIENT_NAME,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
    ) -> None:
        if transport is None:
            if not command:
                raise MCPError("command or transport is required")
            transport = StdioTransport(
                command, args or (), cwd=cwd, env=env, timeout=timeout
            )
        self.transport = transport
        self.client_name = client_name
        self.protocol_version = protocol_version
        self.server_info: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}
        self._started = False

    def start(self) -> dict[str, Any]:
        """Run the MCP handshake and return the server's initialize result."""
        if self._started:
            return {"serverInfo": self.server_info, "capabilities": self.capabilities}
        self.transport.start()
        result = self.transport.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": CLIENT_VERSION},
            },
        )
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        self.transport.notify("notifications/initialized")
        self._started = True
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the server's tool definitions."""
        result = self.transport.request("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise MCPError("invalid tools/list result: 'tools' must be a list")
        return [
            tool
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        ]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call a remote tool and flatten its text content into one string."""
        if not name:
            raise MCPError("tool name cannot be empty")
        result = self.transport.request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        content = result.get("content", [])
        texts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = (
            "\n".join(texts)
            if texts
            else json.dumps(result, ensure_ascii=False, sort_keys=True)
        )
        if result.get("isError"):
            return f"Error: {text}"
        return text

    def close(self) -> None:
        self._started = False
        self.transport.close()


class StdioTransport:
    """Run an MCP server as a subprocess and exchange line-delimited JSON.

    A reader thread fills a queue so requests can time out on Windows, where
    `select` does not work on pipes.
    """

    def __init__(
        self,
        command: str,
        args: list[str] | tuple[str, ...] = (),
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 10.0,
        stderr_tail: int = 20,
    ) -> None:
        if not command:
            raise MCPError("command cannot be empty")
        self.command = command
        self.args = list(args)
        self.cwd = cwd
        self.env = env
        self.timeout = timeout
        self.stderr_tail = stderr_tail
        self.process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._stderr: list[str] = []
        self._lock = threading.Lock()
        self._request_id = 0
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None

    def start(self) -> None:
        if self.process is not None:
            return
        process_env = None
        if self.env is not None:
            process_env = {**os.environ, **self.env}
        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                env=process_env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise MCPError(
                f"failed to start MCP server '{self.command}': {exc}"
            ) from exc
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader.start()
        self._stderr_reader.start()

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_id = self._next_id()
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or {},
            }
        )
        while True:
            message = self._next_message()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                detail = error.get("message") if isinstance(error, dict) else error
                raise MCPError(f"{method} failed: {detail}")
            return message.get("result") or {}

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        self.process = None
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    def _write(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise MCPError("MCP transport is not started")
        with self._lock:
            try:
                process.stdin.write(
                    json.dumps(message, ensure_ascii=False, separators=(",", ":"))
                    + "\n"
                )
                process.stdin.flush()
            except (BrokenPipeError, OSError) as exc:
                raise MCPError(
                    f"cannot write to MCP server: {exc}{self._stderr_hint()}"
                ) from exc

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _next_message(self) -> dict[str, Any]:
        try:
            line = self._responses.get(timeout=self.timeout)
        except queue.Empty:
            raise MCPError(
                f"timed out waiting for MCP server{self._stderr_hint()}"
            ) from None
        if line is None:
            raise MCPError(f"MCP server closed the connection{self._stderr_hint()}")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MCPError(f"invalid JSON from MCP server: {line[:200]}") from exc
        if not isinstance(message, dict):
            raise MCPError("invalid MCP message: expected an object")
        return message

    def _read_stdout(self) -> None:
        process = self.process
        try:
            if process is not None and process.stdout is not None:
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self._responses.put(line)
        except (ValueError, OSError):
            pass
        finally:
            self._responses.put(None)

    def _read_stderr(self) -> None:
        process = self.process
        try:
            if process is not None and process.stderr is not None:
                for line in process.stderr:
                    self._stderr.append(line.rstrip())
                    if len(self._stderr) > self.stderr_tail:
                        del self._stderr[: len(self._stderr) - self.stderr_tail]
        except (ValueError, OSError):
            pass

    def _stderr_hint(self) -> str:
        if not self._stderr:
            return ""
        tail = "\n".join(self._stderr[-5:])
        return f"\nserver stderr:\n{tail}"
# ch18 design notes: MCP client

Status: accepted for ch18 implementation.

## Context

ch15 loads tools from Python plugins inside the repository. That works for code
you own, but the growing MCP (Model Context Protocol) ecosystem already exposes
tools, resources, and prompts from separate processes. Reimplementing each one
as a plugin defeats the point.

ch18 adds a minimal MCP client:

- speak JSON-RPC 2.0 over a subprocess's stdin/stdout;
- perform the `initialize` handshake;
- discover tools with `tools/list`;
- adapt every remote tool to the existing `Tool` interface and register it.

From the agent's point of view nothing changes: the model still sees Anthropic
tool schemas and calls `registry.dispatch`. The new part is where the handler
lives.

## Decisions

### No MCP SDK dependency

The chapter implements the wire format directly: one JSON object per line, an
incrementing `id`, a matching response, and an optional `error` object. The
protocol surface used here is small, and writing it out is the lesson. It also
keeps the test environment dependency-free.

### Transport is an interface

`MCPClient` does not spawn anything itself. It talks to a transport with
`request`, `notify`, and `close`:

- `StdioTransport` starts a subprocess, writes requests to stdin, and reads
  responses from stdout on a reader thread;
- tests use a in-memory fake transport, so protocol tests do not depend on
  process timing;
- one end-to-end test still runs a real subprocess server to cover the parts a
  fake cannot: line buffering, handshake, and shutdown.

A reader thread rather than `select` keeps the implementation portable to
Windows, where `select` only works on sockets.

### Timeouts belong to the transport

Every `request` waits for the response with the matching `id`. If the server
exits, the reader thread pushes a sentinel and the request fails with a readable
error. If the server hangs, the queue wait raises a timeout. Both cases include
the tail of stderr when available, because "server closed the connection" alone
is not debuggable.

Notifications from the server (JSON-RPC messages without an `id`) are skipped
while waiting; ch18 does not act on them.

### Remote tools become ordinary tools

`MCPTool` copies the remote name, description, and `inputSchema`, and forwards
`execute(**kwargs)` to `tools/call`. Registry behavior is unchanged:

- permissions still run in `PreToolUse` before the adapter executes;
- a `tools/call` error becomes an `Error: ...` result, so the model can recover;
- text content blocks are joined with newlines; runs with no text blocks fall
  back to the JSON payload.

Tool names come from the server as-is. A colliding name overwrites the earlier
registration, matching how `ToolRegistry.register` already handles duplicates.

### Lifecycle is explicit

`create_default_registry(..., mcp_client=...)` only reads the tool list and
registers adapters; it does not start or stop processes. The caller owns the
client:

```python
client = MCPClient(command="python", args=["server.py"])
client.start()
try:
    tools = create_default_registry(mcp_client=client, ...)
finally:
    client.close()
```

The CLI registers `client.close` with `atexit`, so an interactive session leaves
no orphaned server process.

### One server per run

The CLI takes a single `--mcp "<command>"` specification. Multiple servers, tool
name prefixes, and per-server permission policies are follow-up work; they do
not change the protocol layer.

## Tool surface

| Piece | Purpose |
|---|---|
| `MCPClient.start` | handshake (`initialize` + `notifications/initialized`) |
| `MCPClient.list_tools` | call `tools/list`, return raw definitions |
| `MCPClient.call_tool` | call `tools/call`, flatten text content |
| `MCPTool` | expose one remote tool as a local `Tool` |
| `load_mcp_tools` | adapt every discovered tool for registry wiring |

## Testing contract

- handshake sends the client info and capabilities, then the initialized
  notification;
- request ids increment and responses with other ids are ignored;
- JSON-RPC errors and timeouts raise `MCPError` with the server message;
- `call_tool` joins text blocks and marks `isError` results as `Error: ...`;
- adapters keep the remote schema and forward arguments unchanged;
- `create_default_registry` registers remote tools only when a client is
  provided;
- a real stdio server: start, list, call, close, and verify the process exits.

## Non-goals

- resources, prompts, sampling, and server-initiated requests;
- HTTP/SSE transports and OAuth;
- automatic reconnection or health checks;
- multiple servers with name prefixing (CLI accepts one server in this chapter);
- acting on server notifications.
"""Agent core — the while-True loop and tool dispatch.

ch01: Implement agent_loop() — an agent is just a loop.
ch02: you will add hardcoded TOOL_HANDLERS.
ch04: you will replace TOOL_HANDLERS with ToolRegistry.
ch05: you will add permission.check() before tool execution.
ch06: you will replace permission.check() with hooks.trigger("PreToolUse", ...).
ch07: you will wrap the LLM call with ErrorHandler.
ch08: you will add context.compact() before each LLM call.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

MAX_TURNS = 50


def agent_loop(
    messages: list[dict[str, Any]],
    tool_handlers: dict[str, Any] | None = None,
    client: Any = None,
    system: str | None = None,
) -> str:
    """The core agent loop.

    Flow:
    1. Call LLM -> append assistant message
    2. If stop_reason != "tool_use" -> break, extract and return text
    3. If stop_reason == "tool_use" -> execute tool -> append tool_result -> continue

    Args:
        messages: conversation history (mutated in place)
        tool_handlers: tool name -> handler function mapping
            ch01: None (chat-only mode, no tools needed)
            ch02: {"bash": ShellTool()}
            ch04: replaced by ToolRegistry.dispatch
        client: LLMClient instance

    Returns:
        The agent's final text response

    ch01: implement basic loop (chat-only mode, tool_handlers can be None)
    ch02: add tool execution logic (when tool_handlers is not None)
    ch07: add max-turn guard (force stop after 50 turns)
    """
    if client is None:
        raise ValueError("client is required")

    tools = _get_tool_schemas(tool_handlers)

    for _ in range(MAX_TURNS):
        response = client.chat(messages, tools=tools, system=system)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return _extract_text(response.content)

        if tool_handlers is None:
            return _extract_text(response.content)

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue

            output = _dispatch_tool(tool_handlers, block.name, block.input)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                }
            )

        messages.append({"role": "user", "content": tool_results})

    return "Error: maximum number of turns reached."


def _extract_text(content: list[Any]) -> str:
    parts = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


def _get_tool_schemas(tool_handlers: Any) -> list[dict[str, Any]] | None:
    if tool_handlers is None:
        return None
    if hasattr(tool_handlers, "get_schemas"):
        return tool_handlers.get_schemas()
    if not tool_handlers:
        return None

    schemas = []
    for handler in tool_handlers.values():
        if isinstance(handler, Mapping):
            schemas.append(handler["schema"])
        else:
            schemas.append(handler.schema)
    return schemas


def _dispatch_tool(tool_handlers: Any, name: str, tool_input: dict[str, Any]) -> str:
    if hasattr(tool_handlers, "dispatch"):
        return str(tool_handlers.dispatch(name, tool_input))

    handler_entry = tool_handlers.get(name)
    if handler_entry is None:
        return f"Error: unknown tool '{name}'"
    if isinstance(handler_entry, Mapping):
        return str(handler_entry["handler"](**tool_input))
    return str(handler_entry.execute(**tool_input))

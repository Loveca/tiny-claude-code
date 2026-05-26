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
    hooks: Any = None,
    error_handler: Any = None,
    max_turns: int = MAX_TURNS,
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

    for _ in range(max_turns):
        response = _chat(client, messages, tools, system, error_handler)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = _extract_text(response.content)
            _trigger(hooks, "Stop", messages=messages, response=final_text)
            return final_text

        if tool_handlers is None:
            final_text = _extract_text(response.content)
            _trigger(hooks, "Stop", messages=messages, response=final_text)
            return final_text

        tool_results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_use_id = getattr(block, "id", None)
            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", None)
            if not tool_use_id or not tool_name or not isinstance(tool_input, dict):
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id or "unknown",
                        "content": "Error: malformed tool_use block",
                    }
                )
                continue

            denial = _trigger(
                hooks,
                "PreToolUse",
                tool_name=tool_name,
                tool_input=tool_input,
                block=block,
            )
            if denial is not None:
                output = str(denial)
            else:
                output = _dispatch_tool(tool_handlers, tool_name, tool_input)
                _trigger(
                    hooks,
                    "PostToolUse",
                    tool_name=tool_name,
                    tool_input=tool_input,
                    result=output,
                    block=block,
                )

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": str(output),
                }
            )

        messages.append({"role": "user", "content": tool_results})

    final_text = "Error: maximum number of turns reached."
    _trigger(hooks, "Stop", messages=messages, response=final_text)
    return final_text


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


def _chat(
    client: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    system: str | None,
    error_handler: Any,
) -> Any:
    if error_handler is not None:
        return error_handler.chat(client, messages, tools=tools, system=system)
    return client.chat(messages, tools=tools, system=system)


def _trigger(hooks: Any, event: str, **kwargs: Any) -> Any:
    if hooks is None:
        return None
    return hooks.trigger(event, **kwargs)


"""Agent core — the while-True loop and tool dispatch.

ch01: Implement agent_loop() — an agent is just a loop.
ch02: you will add hardcoded TOOL_HANDLERS.
ch04: you will replace TOOL_HANDLERS with ToolRegistry.
ch05: you will add permission.check() before tool execution.
ch06: you will replace permission.check() with hooks.trigger("PreToolUse", ...).
ch07: you will wrap the LLM call with ErrorHandler.
ch08: you will add context.compact() before each LLM call.
ch21: you will add on_text, which streams assistant text as it arrives.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tiny_claude_code_ref.llm import StreamAccumulator

MAX_TURNS = 50


def agent_loop(
    messages: list[dict[str, Any]],
    tool_handlers: dict[str, Any] | None = None,
    client: Any = None,
    system: str | None = None,
    hooks: Any = None,
    error_handler: Any = None,
    context_manager: Any = None,
    compact_manager: Any = None,
    max_turns: int = MAX_TURNS,
    on_text: Callable[[str], None] | None = None,
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
        on_text: ch21 — receives assistant text while the model writes it.
            Each turn that produced text ends with a "\n", so whatever prints
            next starts on a fresh line. None (default) keeps the plain path.

    Returns:
        The agent's final text response

    ch01: implement basic loop (chat-only mode, tool_handlers can be None)
    ch02: add tool execution logic (when tool_handlers is not None)
    ch07: add max-turn guard (force stop after 50 turns)
    ch21: add the streaming path behind on_text
    """
    if client is None:
        raise ValueError("client is required")

    tools = _get_tool_schemas(tool_handlers)

    for _ in range(max_turns):
        if context_manager is not None:
            context_manager.compact(
                messages, client=client, compact_manager=compact_manager
            )
        if on_text is None:
            response = _chat(client, messages, tools, system, error_handler)
        else:
            response = _chat_stream(client, messages, tools, system, on_text)
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


def _chat_stream(
    client: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    system: str | None,
    on_text: Callable[[str], None],
) -> Any:
    """Run one streamed turn and hand assistant text to ``on_text`` as it comes.

    ch21: the accumulator rebuilds the same response object the plain path
    returns, so the rest of the loop cannot tell the difference. A client
    without ``chat_stream`` falls back to ``chat`` and delivers its text in
    one piece. Streamed turns are not retried: a retry after partial output
    would print the same text twice.
    """
    stream = getattr(client, "chat_stream", None)
    if stream is None:
        response = client.chat(messages, tools=tools, system=system)
        text = _extract_text(response.content)
        if text:
            on_text(text)
            on_text("\n")
        return response

    accumulator = StreamAccumulator()
    emitted = False
    for event in stream(messages, tools=tools, system=system):
        if getattr(event, "type", None) == "text_delta":
            text = getattr(event, "text", "") or ""
            if text:
                emitted = True
                on_text(text)
        accumulator.feed(event)
    if emitted:
        on_text("\n")
    return accumulator.response()


def _trigger(hooks: Any, event: str, **kwargs: Any) -> Any:
    if hooks is None:
        return None
    return hooks.trigger(event, **kwargs)


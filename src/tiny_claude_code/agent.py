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

def agent_loop(messages: list[dict[str, Any]], tool_handlers: dict[str, Any] | None=None, client: Any=None, system: str | None=None, hooks: Any=None, error_handler: Any=None, context_manager: Any=None, compact_manager: Any=None, max_turns: int=MAX_TURNS) -> str:
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
    raise NotImplementedError('TODO: implement agent_loop')

def _extract_text(content: list[Any]) -> str:
    raise NotImplementedError('TODO: implement _extract_text')

def _get_tool_schemas(tool_handlers: Any) -> list[dict[str, Any]] | None:
    raise NotImplementedError('TODO: implement _get_tool_schemas')

def _dispatch_tool(tool_handlers: Any, name: str, tool_input: dict[str, Any]) -> str:
    raise NotImplementedError('TODO: implement _dispatch_tool')

def _chat(client: Any, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, system: str | None, error_handler: Any) -> Any:
    raise NotImplementedError('TODO: implement _chat')

def _trigger(hooks: Any, event: str, **kwargs: Any) -> Any:
    raise NotImplementedError('TODO: implement _trigger')

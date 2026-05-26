"""Agent core — the while-True loop and tool dispatch."""

from __future__ import annotations

from typing import Any

MAX_TURNS = 50


def agent_loop(
    messages: list[dict[str, Any]],
    tool_handlers: dict[str, Any] | None = None,
    client: Any = None,
) -> str:
    tools = None
    if tool_handlers:
        tools = [h["schema"] for h in tool_handlers.values()]

    for _ in range(MAX_TURNS):
        response = client.chat(messages, tools=tools)
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return _extract_text(response.content)

        if tool_handlers is None:
            return _extract_text(response.content)

        results = []
        for block in response.content:
            if block.type == "tool_use":
                handler_entry = tool_handlers.get(block.name)
                if handler_entry:
                    output = handler_entry["handler"](**block.input)
                else:
                    output = f"Error: unknown tool '{block.name}'"
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(output),
                })
        messages.append({"role": "user", "content": results})

    return "Error: maximum number of turns reached."


def _extract_text(content: list[Any]) -> str:
    parts = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)

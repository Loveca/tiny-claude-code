"""Hook event system for agent lifecycle extension points."""
from __future__ import annotations
from collections import defaultdict
from typing import Any, Callable
HookCallback = Callable[..., Any]

class HookSystem:
    """Priority-ordered hook registry.

    Returning a non-None value short-circuits the event and returns that value
    to the caller. This is used by PreToolUse to deny a tool call.
    """

    def __init__(self) -> None:
        self._callbacks: dict[str, list[tuple[int, HookCallback]]] = defaultdict(list)

    def register(self, event: str, callback: HookCallback, priority: int=0) -> None:
        callbacks = self._callbacks[event]
        callbacks.append((priority, callback))
        callbacks.sort(key=lambda item: item[0], reverse=True)

    def trigger(self, event: str, **kwargs: Any) -> Any:
        for _, callback in self._callbacks.get(event, []):
            result = callback(**kwargs)
            if result is not None:
                return result
        return None

class ToolLogHook:
    """Small in-memory log hook useful for tests and examples."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def post_tool_use(self, tool_name: str, tool_input: dict[str, Any], result: str, **_: Any) -> None:
        self.entries.append({"tool": tool_name, "input": tool_input, "result": result})

class StopLogHook:
    """Records final responses emitted by the agent loop."""

    def __init__(self) -> None:
        self.responses: list[str] = []

    def stop(self, response: str, **_: Any) -> None:
        self.responses.append(response)

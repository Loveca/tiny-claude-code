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
        raise NotImplementedError('TODO: implement __init__')

    def register(self, event: str, callback: HookCallback, priority: int=0) -> None:
        raise NotImplementedError('TODO: implement register')

    def trigger(self, event: str, **kwargs: Any) -> Any:
        raise NotImplementedError('TODO: implement trigger')

class ToolLogHook:
    """Small in-memory log hook useful for tests and examples."""

    def __init__(self) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def post_tool_use(self, tool_name: str, tool_input: dict[str, Any], result: str, **_: Any) -> None:
        raise NotImplementedError('TODO: implement post_tool_use')

class StopLogHook:
    """Records final responses emitted by the agent loop."""

    def __init__(self) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def stop(self, response: str, **_: Any) -> None:
        raise NotImplementedError('TODO: implement stop')

"""Context budget management for conversation history."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

class ContextManager:
    """Estimate and shrink messages before they overflow the model window."""

    def __init__(self, max_tokens: int=32000, target_tokens: int | None=None, max_tool_chars: int=4000, keep_head: int=2, keep_tail: int=8) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Approximate token count as one token per four characters."""
        raise NotImplementedError('TODO: implement estimate_tokens')

    def trim_tool_output(self, messages: list[dict[str, Any]], max_chars: int | None=None) -> list[dict[str, Any]]:
        """Return a copy with long tool_result content truncated."""
        raise NotImplementedError('TODO: implement trim_tool_output')

    def snip_old_messages(self, messages: list[dict[str, Any]], keep_head: int | None=None, keep_tail: int | None=None) -> list[dict[str, Any]]:
        """Return a copy that preserves the beginning and end of the history."""
        raise NotImplementedError('TODO: implement snip_old_messages')

    def compact(self, messages: list[dict[str, Any]], client: Any | None=None, compact_manager: Any | None=None) -> list[dict[str, Any]]:
        """Shrink messages in place and return them."""
        raise NotImplementedError('TODO: implement compact')

    def _content_to_text(self, content: Any) -> str:
        raise NotImplementedError('TODO: implement _content_to_text')

"""Context budget management for conversation history."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

class ContextManager:
    """Estimate and shrink messages before they overflow the model window."""

    def __init__(self, max_tokens: int=32000, target_tokens: int | None=None, max_tool_chars: int=4000, keep_head: int=2, keep_tail: int=8) -> None:
        self.max_tokens = max_tokens
        self.target_tokens = target_tokens or int(max_tokens * 0.8)
        self.max_tool_chars = max_tool_chars
        self.keep_head = keep_head
        self.keep_tail = keep_tail

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Approximate token count as one token per four characters."""
        chars = sum(
            len(self._content_to_text(message.get("content"))) for message in messages
        )
        return max(1, chars // 4) if chars else 0

    def trim_tool_output(self, messages: list[dict[str, Any]], max_chars: int | None=None) -> list[dict[str, Any]]:
        """Return a list with long tool_result content truncated.

        Copy-on-write: messages that don't need trimming are reused by
        reference, so a large history isn't deep-copied wholesale just to
        shorten a couple of oversized tool results.
        """
        limit = max_chars or self.max_tool_chars
        trimmed: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list) or not self._needs_trim(content, limit):
                trimmed.append(message)
                continue
            message = deepcopy(message)
            for block in message["content"]:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                text = str(block.get("content", ""))
                if len(text) > limit:
                    block["content"] = (
                        text[:limit]
                        + f"\n[truncated {len(text) - limit} chars by context budget]"
                    )
            trimmed.append(message)
        return trimmed

    @staticmethod
    def _needs_trim(content: list[Any], limit: int) -> bool:
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                if len(str(block.get("content", ""))) > limit:
                    return True
        return False

    def snip_old_messages(self, messages: list[dict[str, Any]], keep_head: int | None=None, keep_tail: int | None=None) -> list[dict[str, Any]]:
        """Return a copy that preserves the beginning and end of the history."""
        head_count = self.keep_head if keep_head is None else keep_head
        tail_count = self.keep_tail if keep_tail is None else keep_tail
        if len(messages) <= head_count + tail_count + 1:
            return deepcopy(messages)

        head = deepcopy(messages[:head_count])
        tail = deepcopy(messages[-tail_count:]) if tail_count else []
        # Keep tool_use / tool_result pairs intact across the snip boundary,
        # otherwise the API rejects the request with a 400:
        # - head must not end with an assistant tool_use whose result is snipped
        while head and self._ends_with_tool_use(head[-1]):
            head = head[:-1]
        # - tail must not begin with a tool_result whose tool_use is snipped
        while tail and self._has_tool_result(tail[0]):
            tail = tail[1:]
        omitted = len(messages) - len(head) - len(tail)
        marker = {
            "role": "user",
            "content": f"[snipped {omitted} old messages to fit context budget]",
        }
        return head + [marker] + tail

    def compact(self, messages: list[dict[str, Any]], client: Any | None=None, compact_manager: Any | None=None) -> list[dict[str, Any]]:
        """Shrink messages in place and return them."""
        if not messages or self.estimate_tokens(messages) <= self.max_tokens:
            return messages

        reduced = self.trim_tool_output(messages)
        if self.estimate_tokens(reduced) > self.max_tokens:
            reduced = self.snip_old_messages(reduced)

        if (
            self.estimate_tokens(reduced) > self.max_tokens
            and compact_manager is not None
            and client is not None
        ):
            reduced = compact_manager.compact(reduced, client)

        messages[:] = reduced
        return messages

    @staticmethod
    def _block_type(block: Any) -> str | None:
        if isinstance(block, dict):
            return block.get("type")
        return getattr(block, "type", None)

    def _has_tool_result(self, message: dict[str, Any]) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(self._block_type(b) == "tool_result" for b in content)

    def _ends_with_tool_use(self, message: dict[str, Any]) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(self._block_type(b) == "tool_use" for b in content)

    def _content_to_text(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(self._content_to_text(item) for item in content)
        if isinstance(content, dict):
            return "\n".join(str(value) for value in content.values())
        text = getattr(content, "text", None)
        if text is not None:
            return str(text)
        tool_input = getattr(content, "input", None)
        if tool_input is not None:
            return str(tool_input)
        return str(content)

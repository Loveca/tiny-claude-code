"""LLM-backed conversation compaction."""

from __future__ import annotations

from typing import Any


COMPACT_SYSTEM_PROMPT = (
    "Summarize the conversation for a coding agent. Keep user goals, decisions, "
    "changed files, commands run, test results, and unresolved next steps."
)


class CompactManager:
    """Replace long history with an LLM summary plus recent turns."""

    def __init__(self, keep_recent: int = 6, max_summary_tokens: int = 1000) -> None:
        self.keep_recent = keep_recent
        self.max_summary_tokens = max_summary_tokens

    def summarize(self, messages: list[dict[str, Any]], client: Any) -> str:
        transcript = self._format_transcript(messages)
        summary_request = [
            {
                "role": "user",
                "content": "Summarize this conversation:\n\n" + transcript,
            }
        ]
        response = client.chat(
            summary_request,
            max_tokens=self.max_summary_tokens,
            system=COMPACT_SYSTEM_PROMPT,
        )
        return self._extract_text(response.content)

    def build_compact_messages(
        self, summary: str, recent_messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        summary_message = {
            "role": "user",
            "content": "Conversation summary so far:\n" + summary,
        }
        return [summary_message] + list(recent_messages)

    def compact(self, messages: list[dict[str, Any]], client: Any) -> list[dict[str, Any]]:
        summary = self.summarize(messages, client)
        recent = messages[-self.keep_recent :] if self.keep_recent else []
        return self.build_compact_messages(summary, recent)

    def _format_transcript(self, messages: list[dict[str, Any]]) -> str:
        parts = []
        for message in messages:
            role = message.get("role", "unknown")
            parts.append(f"{role}: {self._content_to_text(message.get('content'))}")
        return "\n\n".join(parts)

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(self._content_to_text(item) for item in content)
        if isinstance(content, dict):
            return "\n".join(f"{key}: {value}" for key, value in content.items())
        text = getattr(content, "text", None)
        if text is not None:
            return str(text)
        return str(content)

    def _extract_text(self, content: list[Any]) -> str:
        parts = []
        for block in content:
            text = getattr(block, "text", None)
            if text is not None:
                parts.append(str(text))
        return "\n".join(parts)

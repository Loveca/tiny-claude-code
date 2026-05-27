"""LLM-backed conversation compaction."""
from __future__ import annotations
from typing import Any
COMPACT_SYSTEM_PROMPT = 'Summarize the conversation for a coding agent. Keep user goals, decisions, changed files, commands run, test results, and unresolved next steps.'

class CompactManager:
    """Replace long history with an LLM summary plus recent turns."""

    def __init__(self, keep_recent: int=6, max_summary_tokens: int=1000) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def summarize(self, messages: list[dict[str, Any]], client: Any) -> str:
        raise NotImplementedError('TODO: implement summarize')

    def build_compact_messages(self, summary: str, recent_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement build_compact_messages')

    def compact(self, messages: list[dict[str, Any]], client: Any) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement compact')

    def _format_transcript(self, messages: list[dict[str, Any]]) -> str:
        raise NotImplementedError('TODO: implement _format_transcript')

    def _content_to_text(self, content: Any) -> str:
        raise NotImplementedError('TODO: implement _content_to_text')

    def _extract_text(self, content: list[Any]) -> str:
        raise NotImplementedError('TODO: implement _extract_text')

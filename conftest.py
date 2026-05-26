"""Shared test fixtures and mock LLM client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass
class MockTextBlock:
    """Mimics Anthropic TextBlock."""
    type: str = "text"
    text: str = ""


@dataclass
class MockToolUseBlock:
    """Mimics Anthropic ToolUseBlock."""
    type: str = "tool_use"
    id: str = "toolu_01"
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class MockMessage:
    """Mimics Anthropic Message."""
    content: list[Any] = field(default_factory=list)
    stop_reason: str = "end_turn"
    model: str = "mock-model"
    role: str = "assistant"


class MockLLMClient:
    """Programmable mock LLM client for testing.

    Usage:
        client = MockLLMClient()
        client.add_text_response("Hello!")
        client.add_tool_use_response("bash", {"command": "ls"})
        client.add_text_response("Here are the files...")
    """

    def __init__(self) -> None:
        self.responses: list[MockMessage] = []
        self._call_count = 0
        self.last_system: str | None = None

    def add_text_response(self, text: str) -> None:
        self.responses.append(MockMessage(
            content=[MockTextBlock(text=text)],
            stop_reason="end_turn",
        ))

    def add_tool_use_response(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
        stop_reason: str = "tool_use",
    ) -> None:
        self.responses.append(MockMessage(
            content=[MockToolUseBlock(name=tool_name, input=tool_input or {})],
            stop_reason=stop_reason,
        ))

    def add_mixed_response(
        self,
        text: str,
        tool_name: str,
        tool_input: dict[str, Any] | None = None,
    ) -> None:
        self.responses.append(MockMessage(
            content=[
                MockTextBlock(text=text),
                MockToolUseBlock(name=tool_name, input=tool_input or {}),
            ],
            stop_reason="tool_use",
        ))

    def add_tool_use_blocks_response(
        self,
        tool_calls: list[tuple[str, dict[str, Any]]],
        stop_reason: str = "tool_use",
    ) -> None:
        self.responses.append(MockMessage(
            content=[
                MockToolUseBlock(id=f"toolu_{index:02d}", name=name, input=tool_input)
                for index, (name, tool_input) in enumerate(tool_calls, 1)
            ],
            stop_reason=stop_reason,
        ))

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 8000,
        system: str | None = None,
    ) -> MockMessage:
        self.last_system = system
        if self._call_count >= len(self.responses):
            return MockMessage(
                content=[MockTextBlock(text="No more responses configured.")],
                stop_reason="end_turn",
            )
        response = self.responses[self._call_count]
        self._call_count += 1
        return response


@pytest.fixture
def mock_client() -> MockLLMClient:
    return MockLLMClient()

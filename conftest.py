"""Shared test fixtures and mock LLM client."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest


if os.environ.get("TINY_CLAUDE_CODE_TEST_TARGET") == "ref":
    # Run the chapter tests against the reference implementation.
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    sys.modules["tiny_claude_code"] = importlib.import_module("tiny_claude_code_ref")

    class _RefAliasLoader:
        """Reuse an already-imported ref module instead of executing it again."""

        def __init__(self, module: object) -> None:
            self.module = module

        def create_module(self, spec: object) -> object:
            return self.module

        def exec_module(self, module: object) -> None:
            pass

    class _RefAliasFinder:
        """Map ``tiny_claude_code.*`` imports onto ``tiny_claude_code_ref.*``.

        Without this, ``tiny_claude_code.workflow`` executes the ref file a
        second time, producing duplicate classes from the same source — so an
        ``except SomeError`` in ref code would not catch the aliased twin.
        """

        def find_spec(self, fullname: str, path=None, target=None):
            if not fullname.startswith("tiny_claude_code."):
                return None
            ref_name = "tiny_claude_code_ref" + fullname[len("tiny_claude_code"):]
            try:
                module = importlib.import_module(ref_name)
            except ModuleNotFoundError:
                return None
            return importlib.util.spec_from_loader(
                fullname,
                _RefAliasLoader(module),
                is_package=hasattr(module, "__path__"),
            )

    sys.meta_path.insert(0, _RefAliasFinder())


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

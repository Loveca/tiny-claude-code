"""Tests for ch04: Tool Registry."""

from typing import Any

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.tools import ToolRegistry, create_default_registry
from tiny_claude_code.tools.base import Tool
from conftest import MockLLMClient


class EchoTool(Tool):
    name = "echo"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Echo text.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        }

    def execute(self, text: str) -> str:
        return text


class ReplacementEchoTool(EchoTool):
    def execute(self, text: str) -> str:
        return f"replacement:{text}"


def test_register_one_tool_schema() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    schemas = registry.get_schemas()

    assert len(schemas) == 1
    assert schemas[0]["name"] == "echo"


def test_register_three_default_tools() -> None:
    registry = create_default_registry()

    names = {schema["name"] for schema in registry.get_schemas()}

    assert {"bash", "read", "write", "search"}.issubset(names)


def test_dispatch_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = registry.dispatch("echo", {"text": "hello"})

    assert result == "hello"


def test_dispatch_unknown_tool_returns_error() -> None:
    registry = ToolRegistry()

    result = registry.dispatch("missing", {})

    assert "unknown tool" in result.lower()


def test_duplicate_registration_overwrites_old_tool() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())
    registry.register(ReplacementEchoTool())

    result = registry.dispatch("echo", {"text": "hello"})

    assert result == "replacement:hello"


def test_agent_loop_uses_registry() -> None:
    mock_client = MockLLMClient()
    mock_client.add_tool_use_response("echo", {"text": "hello"})
    mock_client.add_text_response("done")
    registry = ToolRegistry()
    registry.register(EchoTool())
    messages = [{"role": "user", "content": "echo hello"}]

    result = agent_loop(messages, tool_handlers=registry, client=mock_client)

    assert result == "done"
    assert any(
        block.get("content") == "hello"
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if isinstance(block, dict)
    )

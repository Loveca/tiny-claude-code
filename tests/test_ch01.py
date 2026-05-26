"""Tests for ch01: Agent Loop + CLI."""

import pytest

from tiny_claude_code.agent import agent_loop
from conftest import MockLLMClient, MockTextBlock, MockToolUseBlock


class TestAgentLoop:
    """Test agent_loop with mock LLM client."""

    def test_text_response_ends_loop(self, mock_client: MockLLMClient):
        """When LLM returns pure text, the loop should end immediately."""
        mock_client.add_text_response("I am an agent.")

        messages = [{"role": "user", "content": "Hello"}]
        result = agent_loop(messages, tool_handlers=None, client=mock_client)

        assert result == "I am an agent."
        assert len(messages) == 2  # user + assistant
        assert mock_client._call_count == 1

    def test_tool_use_then_text(self, mock_client: MockLLMClient):
        """When LLM calls a tool then returns text, loop should execute tool and end."""
        mock_client.add_tool_use_response("bash", {"command": "echo hello"})
        mock_client.add_text_response("The output is: hello")

        def bash_handler(command: str) -> str:
            return "hello"

        tool_handlers = {
            "bash": {
                "schema": {"name": "bash", "description": "Run a command"},
                "handler": bash_handler,
            }
        }

        messages = [{"role": "user", "content": "Run echo hello"}]
        result = agent_loop(messages, tool_handlers=tool_handlers, client=mock_client)

        assert "hello" in result
        assert mock_client._call_count == 2

    def test_multiple_tool_uses(self, mock_client: MockLLMClient):
        """When LLM calls tools multiple times, loop should continue until text response."""
        mock_client.add_tool_use_response("bash", {"command": "echo step1"})
        mock_client.add_tool_use_response("bash", {"command": "echo step2"})
        mock_client.add_text_response("Done with both steps.")

        call_count = 0

        def bash_handler(command: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"step{call_count}"

        tool_handlers = {
            "bash": {
                "schema": {"name": "bash", "description": "Run a command"},
                "handler": bash_handler,
            }
        }

        messages = [{"role": "user", "content": "Run two commands"}]
        result = agent_loop(messages, tool_handlers=tool_handlers, client=mock_client)

        assert "Done" in result
        assert call_count == 2
        assert mock_client._call_count == 3

    def test_unknown_tool_returns_error(self, mock_client: MockLLMClient):
        """When LLM calls an unknown tool, it should get an error message back."""
        mock_client.add_tool_use_response("nonexistent_tool", {})
        mock_client.add_text_response("I see the tool doesn't exist.")

        tool_handlers = {}

        messages = [{"role": "user", "content": "Try unknown tool"}]
        result = agent_loop(messages, tool_handlers=tool_handlers, client=mock_client)

        assert "I see" in result
        # The tool_result message should contain the error
        # Find the tool_result in messages
        for msg in messages:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result":
                        assert "unknown tool" in block["content"].lower() or "error" in block["content"].lower()

    def test_empty_messages(self, mock_client: MockLLMClient):
        """Agent loop should handle an empty messages list."""
        mock_client.add_text_response("I'm ready to help.")

        messages: list[dict] = []
        result = agent_loop(messages, tool_handlers=None, client=mock_client)

        assert "ready" in result.lower() or len(result) > 0

    def test_messages_grow_with_conversation(self, mock_client: MockLLMClient):
        """Messages list should grow as the conversation progresses."""
        mock_client.add_tool_use_response("bash", {"command": "ls"})
        mock_client.add_text_response("Files listed.")

        tool_handlers = {
            "bash": {
                "schema": {"name": "bash", "description": "Run a command"},
                "handler": lambda command: "file1.py\nfile2.py",
            }
        }

        messages = [{"role": "user", "content": "List files"}]
        agent_loop(messages, tool_handlers=tool_handlers, client=mock_client)

        # user(1) + assistant(1) + tool_result(1) + assistant(1) = 4
        assert len(messages) >= 3

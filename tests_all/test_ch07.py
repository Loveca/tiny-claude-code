"""Tests for ch07: Error Recovery."""

from __future__ import annotations

import pytest

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.error_recovery import ErrorHandler
from conftest import MockLLMClient, MockMessage, MockTextBlock


class APIError(Exception):
    def __init__(self, message: str, status_code: int | None = None, headers: dict | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.headers = headers or {}


class FlakyClient:
    def __init__(self, outcomes, model: str = "primary") -> None:
        self.outcomes = list(outcomes)
        self.model = model
        self.calls: list[dict] = []

    def chat(self, messages, tools=None, max_tokens=8000, system=None):
        self.calls.append({"model": self.model, "max_tokens": max_tokens, "system": system})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def message(text: str = "ok") -> MockMessage:
    return MockMessage(content=[MockTextBlock(text=text)], stop_reason="end_turn")


def test_429_retries_then_success() -> None:
    client = FlakyClient([APIError("rate limit", 429), APIError("rate limit", 429), message("ok")])
    sleeps: list[float] = []
    handler = ErrorHandler(sleep=sleeps.append)

    result = handler.chat(client, [])

    assert result.content[0].text == "ok"
    assert sleeps == [2.0, 4.0]
    assert len(client.calls) == 3


def test_429_exhausts_retries() -> None:
    client = FlakyClient([APIError("rate limit", 429)] * 4)
    handler = ErrorHandler(sleep=lambda _: None)

    with pytest.raises(APIError):
        handler.chat(client, [])

    assert len(client.calls) == 4


def test_529_uses_retry_after() -> None:
    client = FlakyClient([APIError("overloaded", 529, {"Retry-After": "5"}), message("ok")])
    sleeps: list[float] = []
    handler = ErrorHandler(sleep=sleeps.append)

    result = handler.chat(client, [])

    assert result.content[0].text == "ok"
    assert sleeps == [5.0]


def test_token_limit_increases_max_tokens() -> None:
    client = FlakyClient([APIError("token limit exceeded"), message("ok")])
    handler = ErrorHandler(sleep=lambda _: None)

    result = handler.chat(client, [], max_tokens=8000)

    assert result.content[0].text == "ok"
    assert [call["max_tokens"] for call in client.calls] == [8000, 16000]


def test_fallback_model_is_used_after_primary_failure() -> None:
    client = FlakyClient([APIError("server error", 500), message("ok")])
    handler = ErrorHandler(fallback_models=["backup"], sleep=lambda _: None)

    result = handler.chat(client, [])

    assert result.content[0].text == "ok"
    assert [call["model"] for call in client.calls] == ["primary", "backup"]


def test_agent_loop_max_turn_guard() -> None:
    client = MockLLMClient()
    for _ in range(3):
        client.add_tool_use_response("echo", {"text": "loop"})

    result = agent_loop(
        [{"role": "user", "content": "loop"}],
        tool_handlers={"echo": {"schema": {"name": "echo"}, "handler": lambda text: text}},
        client=client,
        max_turns=2,
    )

    assert "maximum number of turns" in result


def test_malformed_tool_use_does_not_crash() -> None:
    class BadToolUse:
        type = "tool_use"
        name = "echo"
        input = {"text": "hello"}

    client = MockLLMClient()
    client.responses.append(MockMessage(content=[BadToolUse()], stop_reason="tool_use"))
    client.add_text_response("recovered")

    result = agent_loop(
        [{"role": "user", "content": "bad tool"}],
        tool_handlers={"echo": {"schema": {"name": "echo"}, "handler": lambda text: text}},
        client=client,
    )

    assert result == "recovered"

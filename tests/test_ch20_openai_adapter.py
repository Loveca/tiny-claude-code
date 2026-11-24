"""ch20: OpenAI-compatible provider adapter."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.error_recovery import ErrorHandler
from tiny_claude_code.llm import (
    OpenAICompatibleClient,
    OpenAIError,
    TextBlock,
    ToolUseBlock,
    anthropic_messages_to_openai,
    anthropic_tools_to_openai,
    create_client,
    openai_response_to_anthropic,
)
from tiny_claude_code.tools import ToolRegistry
from tiny_claude_code.tools.base import Tool


def _tool_use_response(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def _text_response(text: str) -> dict[str, Any]:
    return {
        "choices": [
            {"message": {"content": text}, "finish_reason": "stop"}
        ]
    }


class EchoTool(Tool):
    name = "echo"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": "echo",
            "description": "Echo text back.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        }

    def execute(self, text: str = "") -> str:
        return f"echo:{text}"


def test_user_text_message_passes_through() -> None:
    assert anthropic_messages_to_openai(
        [{"role": "user", "content": "hi"}]
    ) == [{"role": "user", "content": "hi"}]


def test_system_prompt_becomes_leading_message() -> None:
    converted = anthropic_messages_to_openai(
        [{"role": "user", "content": "hi"}], system="be brief"
    )
    assert converted[0] == {"role": "system", "content": "be brief"}
    assert len(converted) == 2


def test_assistant_tool_use_becomes_tool_calls() -> None:
    messages = [
        {
            "role": "assistant",
            "content": [
                TextBlock(text="running"),
                ToolUseBlock(id="t1", name="bash", input={"command": "ls"}),
            ],
        }
    ]
    converted = anthropic_messages_to_openai(messages)
    item = converted[0]
    assert item["role"] == "assistant"
    assert item["content"] == "running"
    call = item["tool_calls"][0]
    assert call["id"] == "t1"
    assert call["type"] == "function"
    assert call["function"]["name"] == "bash"
    assert json.loads(call["function"]["arguments"]) == {"command": "ls"}


def test_tool_results_come_before_trailing_text() -> None:
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "continue after"},
                {"type": "tool_result", "tool_use_id": "t1", "content": "file1"},
                {"type": "tool_result", "tool_use_id": "t2", "content": "file2"},
            ],
        }
    ]
    converted = anthropic_messages_to_openai(messages)
    assert [item["role"] for item in converted] == ["tool", "tool", "user"]
    assert [item["tool_call_id"] for item in converted[:2]] == ["t1", "t2"]
    assert converted[2]["content"] == "continue after"


def test_tool_results_without_text_emit_no_empty_user_message() -> None:
    messages = [
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
        }
    ]
    converted = anthropic_messages_to_openai(messages)
    assert converted == [{"role": "tool", "tool_call_id": "t1", "content": "ok"}]


def test_tool_schemas_become_function_tools() -> None:
    schema = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
    }
    converted = anthropic_tools_to_openai(
        [{"name": "bash", "description": "Run a command", "input_schema": schema}]
    )
    assert converted[0]["type"] == "function"
    function = converted[0]["function"]
    assert function["name"] == "bash"
    assert function["description"] == "Run a command"
    assert function["parameters"] == schema


def test_text_response_adapts() -> None:
    response = openai_response_to_anthropic(_text_response("hello"))
    assert response.stop_reason == "end_turn"
    assert len(response.content) == 1
    assert response.content[0].type == "text"
    assert response.content[0].text == "hello"


def test_tool_call_response_adapts() -> None:
    response = openai_response_to_anthropic(
        _tool_use_response("bash", {"command": "dir"})
    )
    assert response.stop_reason == "tool_use"
    block = response.content[0]
    assert block.type == "tool_use"
    assert block.id == "call_1"
    assert block.name == "bash"
    assert block.input == {"command": "dir"}


def test_invalid_tool_arguments_mark_input_none() -> None:
    data = _tool_use_response("bash", {})
    data["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "{oops"
    response = openai_response_to_anthropic(data)
    assert response.content[0].input is None


def test_finish_reason_length_maps_to_max_tokens() -> None:
    data = {
        "choices": [
            {"message": {"content": "partial"}, "finish_reason": "length"}
        ]
    }
    assert openai_response_to_anthropic(data).stop_reason == "max_tokens"


def test_missing_choices_raises() -> None:
    with pytest.raises(OpenAIError):
        openai_response_to_anthropic({"choices": []})


def test_client_converts_and_posts() -> None:
    captured: dict[str, Any] = {}

    def fake_transport(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return _text_response("ok")

    client = OpenAICompatibleClient(
        model="m",
        api_key="secret",
        base_url="http://example.test/v1/",
        transport=fake_transport,
    )
    response = client.chat(
        [{"role": "user", "content": "hi"}],
        tools=[{"name": "bash", "description": "", "input_schema": {"type": "object"}}],
        system="be brief",
        max_tokens=100,
    )
    assert captured["url"] == "http://example.test/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    payload = captured["payload"]
    assert payload["model"] == "m"
    assert payload["max_tokens"] == 100
    assert payload["messages"][0] == {"role": "system", "content": "be brief"}
    assert payload["tools"][0]["type"] == "function"
    assert response.content[0].text == "ok"


def test_agent_loop_round_trip_over_fake_transport() -> None:
    sent: list[list[dict[str, Any]]] = []
    replies = [_tool_use_response("echo", {"text": "hi"}), _text_response("done")]

    def fake_transport(url, headers, payload):
        sent.append(payload["messages"])
        return replies[len(sent) - 1]

    client = OpenAICompatibleClient(
        model="m", api_key="k", base_url="http://t/v1", transport=fake_transport
    )
    registry = ToolRegistry()
    registry.register(EchoTool())
    messages: list[dict[str, Any]] = [{"role": "user", "content": "say hi"}]

    final = agent_loop(messages, tool_handlers=registry, client=client)

    assert final == "done"
    assert len(sent) == 2
    second = sent[1]
    assert second[1]["role"] == "assistant"
    assert second[1]["tool_calls"][0]["function"]["name"] == "echo"
    assert second[2] == {"role": "tool", "tool_call_id": "call_1", "content": "echo:hi"}


def test_error_handler_retries_openai_429() -> None:
    calls = {"count": 0}

    def fake_transport(url, headers, payload):
        calls["count"] += 1
        if calls["count"] < 3:
            raise OpenAIError("rate limited", status_code=429)
        return _text_response("ok")

    client = OpenAICompatibleClient(
        model="m", api_key="k", base_url="http://t/v1", transport=fake_transport
    )
    handler = ErrorHandler(max_retries=3, backoff_seconds=(0, 0, 0), sleep=lambda _: None)

    response = handler.chat(client, [{"role": "user", "content": "hi"}])

    assert response.content[0].text == "ok"
    assert calls["count"] == 3


def test_error_handler_gives_up_after_retries() -> None:
    calls = {"count": 0}

    def fake_transport(url, headers, payload):
        calls["count"] += 1
        raise OpenAIError("rate limited", status_code=429)

    client = OpenAICompatibleClient(
        model="m", api_key="k", base_url="http://t/v1", transport=fake_transport
    )
    handler = ErrorHandler(max_retries=3, backoff_seconds=(0, 0, 0), sleep=lambda _: None)

    with pytest.raises(OpenAIError):
        handler.chat(client, [{"role": "user", "content": "hi"}])
    assert calls["count"] == 4


def test_create_client_honours_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from tiny_claude_code import llm as llm_module

    class StubAnthropicClient:
        """Stands in for LLMClient so no real SDK client is constructed."""

    monkeypatch.setattr(llm_module, "LLMClient", StubAnthropicClient)

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert isinstance(create_client(), OpenAICompatibleClient)

    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    assert isinstance(create_client(), StubAnthropicClient)

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(create_client(), StubAnthropicClient)
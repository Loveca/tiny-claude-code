"""ch21: ``--stream`` end to end — the task mode CLI prints text as it arrives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tiny_claude_code import cli
from tiny_claude_code.llm import MessageStop, TextDelta


class _ScriptedClient:
    """A provider client with only the surface the streamed loop touches."""

    def __init__(self, *pieces: str) -> None:
        self.pieces = pieces

    def chat_stream(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        for piece in self.pieces:
            yield TextDelta(text=piece)
        yield MessageStop()

    def chat(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("--stream must not fall back to chat()")


def _run_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, client: Any, *argv: str
) -> None:
    monkeypatch.setattr(cli, "create_client", lambda: client)
    cli.main(["--workspace", str(tmp_path), *argv, "say hi"])


def test_stream_flag_prints_each_delta_on_arrival(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    on_screen: list[str] = []

    class _Client(_ScriptedClient):
        def chat_stream(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
            for piece in ("Hel", "lo!"):
                # Snapshot what the user can already see before this delta.
                on_screen.append(capsys.readouterr().out)
                yield TextDelta(text=piece)
            yield MessageStop()

    _run_task(monkeypatch, tmp_path, _Client(), "--stream")

    # "Hel" was written before the second delta existed.
    assert on_screen == ["", "Hel"]
    assert capsys.readouterr().out == "lo!\n"


def test_stream_output_is_not_printed_twice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _run_task(monkeypatch, tmp_path, _ScriptedClient("Hel", "lo!"), "--stream")

    assert capsys.readouterr().out == "Hello!\n"


def test_without_stream_flag_the_answer_is_printed_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class _PlainClient(_ScriptedClient):
        def chat(self, *args: Any, **kwargs: Any) -> Any:
            from conftest import MockMessage, MockTextBlock

            return MockMessage(content=[MockTextBlock(text="Hello!")])

    _run_task(monkeypatch, tmp_path, _PlainClient())

    assert capsys.readouterr().out == "Hello!\n"


def test_streamed_task_is_saved_as_a_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tiny_claude_code.session import SessionManager

    _run_task(monkeypatch, tmp_path, _ScriptedClient("Hello!"), "--stream")

    sessions = SessionManager(tmp_path).list_sessions()
    assert len(sessions) == 1
    saved = SessionManager(tmp_path).load(str(sessions[0]["id"]))
    assert saved[-1] == {
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello!"}],
    }

"""Tests for ch10: Session and Memory."""

from __future__ import annotations

from tiny_claude_code.cli import build_system_prompt, handle_memory_command
from tiny_claude_code.memory import MemoryManager
from tiny_claude_code.session import SessionManager


def test_session_save_and_load_round_trip(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    messages = [{"role": "user", "content": "hello"}]

    manager.save("s1", messages, {"name": "test"})

    assert manager.load("s1") == messages


def test_list_sessions_returns_newest_first(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    manager.save("old", [], {})
    manager.save("new", [{"role": "user", "content": "x"}], {})

    sessions = manager.list_sessions()

    assert sessions[0]["id"] == "new"
    assert manager.latest_session_id() == "new"


def test_memory_save_writes_frontmatter(tmp_path) -> None:
    manager = MemoryManager(tmp_path)

    path = manager.save("project", "Uses pytest", "Run tests with pytest -q")

    text = path.read_text(encoding="utf-8")
    assert "category: project" in text
    assert "title: Uses pytest" in text
    assert "Run tests with pytest -q" in text


def test_memory_load_relevant_matches_keywords(tmp_path) -> None:
    manager = MemoryManager(tmp_path)
    manager.save("project", "Testing", "Use pytest for this project")
    manager.save("style", "Formatting", "Use compact Markdown")

    memories = manager.load_relevant("pytest command")

    assert len(memories) == 1
    assert "Use pytest" in memories[0]


def test_memory_build_index_lists_entries(tmp_path) -> None:
    manager = MemoryManager(tmp_path)
    manager.save("project", "Testing", "Use pytest")

    index = manager.build_index()

    assert "Testing" in index.read_text(encoding="utf-8")


def test_system_prompt_includes_memory_context(tmp_path) -> None:
    memory = MemoryManager(tmp_path)
    memory.save("project", "Testing", "Use pytest")

    system = build_system_prompt(tmp_path, memory.build_system_context())

    assert "Relevant project memories" in system
    assert "Use pytest" in system


def test_memory_command_adds_memory(tmp_path) -> None:
    memory = MemoryManager(tmp_path)

    output = handle_memory_command(memory, '/memory add "Testing" "Use pytest"')

    assert "Saved memory" in output
    assert memory.load_relevant("pytest")

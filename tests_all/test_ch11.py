"""Tests for ch11: Todo and Task System."""

from __future__ import annotations

import json

from tiny_claude_code.tasks import TaskManager, TodoWriteTool
from tiny_claude_code.tools import create_default_registry


def test_create_todo_defaults_to_pending(tmp_path) -> None:
    manager = TaskManager(tmp_path)

    todo = manager.create("Read the code")

    assert todo.status == "pending"
    assert (tmp_path / ".tiny-claude-code" / "tasks" / f"{todo.id}.json").exists()


def test_only_one_todo_can_be_in_progress(tmp_path) -> None:
    manager = TaskManager(tmp_path)

    first = manager.create("First", status="in_progress")
    second = manager.create("Second", status="in_progress")

    assert manager.todos[first.id].status == "in_progress"
    assert manager.todos[second.id].status == "pending"


def test_blocked_dependency_becomes_pending_when_dependency_completes(tmp_path) -> None:
    manager = TaskManager(tmp_path)
    dependency = manager.create("Dependency")
    blocked = manager.create("Blocked", blocked_by=[dependency.id])

    assert manager.todos[blocked.id].status == "blocked"

    manager.update(dependency.id, status="completed")

    assert manager.todos[blocked.id].status == "pending"


def test_reminder_after_three_turns_without_update(tmp_path) -> None:
    manager = TaskManager(tmp_path)
    manager.create("Do work")

    assert manager.tick_without_update() is None
    assert manager.tick_without_update() is None
    assert "Reminder" in manager.tick_without_update()


def test_todo_write_tool_updates_manager(tmp_path) -> None:
    manager = TaskManager(tmp_path)
    tool = TodoWriteTool(manager)

    result = tool.execute([{"title": "Implement feature", "status": "in_progress"}])

    data = json.loads(result)
    assert data[0]["title"] == "Implement feature"
    assert manager.list()[0]["status"] == "in_progress"


def test_default_registry_includes_todo_write(tmp_path) -> None:
    registry = create_default_registry(tmp_path)

    names = {schema["name"] for schema in registry.get_schemas()}

    assert "TodoWrite" in names

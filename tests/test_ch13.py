"""Tests for ch13: Background and Cron."""

from __future__ import annotations

from datetime import datetime

from tiny_claude_code.background import (
    BackgroundManager,
    BackgroundPollTool,
    BackgroundSubmitTool,
)
from tiny_claude_code.cron import CronScheduleTool, CronScheduler
from tiny_claude_code.tools import create_default_registry


def test_background_submit_returns_before_result(tmp_path) -> None:
    manager = BackgroundManager(tmp_path)

    task_id = manager.submit("python -c \"print('hello')\"")
    result = manager.get_result(task_id)

    assert result == "Task is still running" or "hello" in result
    manager.shutdown()


def test_background_poll_returns_completed_result(tmp_path) -> None:
    manager = BackgroundManager(tmp_path)
    task_id = manager.submit("python -c \"print('hello')\"")

    result = manager.tasks[task_id].future.result(timeout=5)
    status = manager.poll(task_id)

    assert "hello" in result
    assert status["status"] == "completed"
    assert "hello" in status["result"]
    manager.shutdown()


def test_background_tools_submit_and_poll(tmp_path) -> None:
    manager = BackgroundManager(tmp_path)
    submit = BackgroundSubmitTool(manager)
    poll = BackgroundPollTool(manager)

    response = submit.execute("python -c \"print('ok')\"")
    task_id = response.split(":", 1)[1].strip()
    manager.tasks[task_id].future.result(timeout=5)

    assert "completed" in poll.execute(task_id)
    manager.shutdown()


def test_background_notifications_are_returned_once(tmp_path) -> None:
    manager = BackgroundManager(tmp_path)
    task_id = manager.submit("python -c \"print('done')\"")
    manager.tasks[task_id].future.result(timeout=5)

    first = manager.completed_notifications()
    second = manager.completed_notifications()

    assert len(first) == 1
    assert second == []
    manager.shutdown()


def test_cron_every_five_minutes_matches(tmp_path) -> None:
    scheduler = CronScheduler(tmp_path)
    now = datetime(2026, 5, 26, 10, 15)

    assert scheduler.matches("*/5 * * * *", now)
    assert not scheduler.matches("*/7 * * * *", now)


def test_cron_schedule_is_persisted(tmp_path) -> None:
    scheduler = CronScheduler(tmp_path)
    task = scheduler.schedule("*/5 * * * *", "Run tests")

    restored = CronScheduler(tmp_path)

    assert task.id in restored.tasks
    assert restored.tasks[task.id].prompt == "Run tests"


def test_cron_schedule_tool_persists_task(tmp_path) -> None:
    scheduler = CronScheduler(tmp_path)
    tool = CronScheduleTool(scheduler)

    result = tool.execute("*/5 * * * *", "Run tests")

    assert "scheduled_task_id" in result
    assert len(scheduler.tasks) == 1


def test_cron_due_returns_matching_tasks(tmp_path) -> None:
    scheduler = CronScheduler(tmp_path)
    scheduler.schedule("*/5 * * * *", "Run tests")

    due = scheduler.due(datetime(2026, 5, 26, 10, 15))

    assert due[0].prompt == "Run tests"


def test_default_registry_includes_background_tools(tmp_path) -> None:
    registry = create_default_registry(tmp_path)

    names = {schema["name"] for schema in registry.get_schemas()}

    assert {"BackgroundSubmit", "BackgroundPoll", "CronSchedule"}.issubset(names)

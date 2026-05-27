"""Tiny cron-style scheduler."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from tiny_claude_code.tools.base import Tool


@dataclass
class CronTask:
    id: str
    expression: str
    prompt: str


class CronScheduler:
    """Persisted five-field cron matcher."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.path = self.workspace / ".tiny-claude-code" / "scheduled_tasks.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, CronTask] = {}
        self.load()

    def schedule(self, expression: str, prompt: str) -> CronTask:
        self._validate(expression)
        task = CronTask(uuid4().hex[:8], expression, prompt)
        self.tasks[task.id] = task
        self.save()
        return task

    def due(self, now: datetime) -> list[CronTask]:
        return [task for task in self.tasks.values() if self.matches(task.expression, now)]

    def matches(self, expression: str, now: datetime) -> bool:
        minute, hour, day, month, weekday = expression.split()
        return (
            self._field_matches(minute, now.minute)
            and self._field_matches(hour, now.hour)
            and self._field_matches(day, now.day)
            and self._field_matches(month, now.month)
            and self._field_matches(weekday, now.weekday())
        )

    def save(self) -> None:
        data = [asdict(task) for task in self.tasks.values()]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.tasks = {item["id"]: CronTask(**item) for item in data}

    def _validate(self, expression: str) -> None:
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError("cron expression must have five fields")
        for part in parts:
            if part != "*" and not part.startswith("*/") and not part.isdigit():
                raise ValueError(f"unsupported cron field: {part}")

    def _field_matches(self, field: str, value: int) -> bool:
        if field == "*":
            return True
        if field.startswith("*/"):
            step = int(field[2:])
            return step > 0 and value % step == 0
        return int(field) == value


class CronScheduleTool(Tool):
    name = "CronSchedule"

    def __init__(self, scheduler: CronScheduler) -> None:
        self.scheduler = scheduler

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Schedule a prompt with a simple five-field cron expression.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                    "prompt": {"type": "string"},
                },
                "required": ["expression", "prompt"],
            },
        }

    def execute(self, expression: str, prompt: str) -> str:
        task = self.scheduler.schedule(expression, prompt)
        return f"scheduled_task_id: {task.id}"

"""Todo and task tracking for agent work."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from tiny_claude_code.tools.base import Tool


VALID_STATUSES = {"pending", "in_progress", "completed", "blocked"}


@dataclass
class TodoItem:
    title: str
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    status: str = "pending"
    blocked_by: list[str] = field(default_factory=list)


class TaskManager:
    """Persistent todo list with simple dependency rules."""

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.task_dir = self.workspace / ".tiny-claude-code" / "tasks"
        self.task_dir.mkdir(parents=True, exist_ok=True)
        self.todos: dict[str, TodoItem] = {}
        self.turns_without_update = 0

    def create(
        self,
        title: str,
        status: str = "pending",
        blocked_by: list[str] | None = None,
        todo_id: str | None = None,
    ) -> TodoItem:
        todo = TodoItem(
            id=todo_id or uuid4().hex[:8],
            title=title,
            status=status,
            blocked_by=blocked_by or [],
        )
        self.todos[todo.id] = todo
        self._normalize()
        self._persist(todo)
        self.turns_without_update = 0
        return todo

    def update(self, todo_id: str, **changes: Any) -> TodoItem:
        if todo_id not in self.todos:
            raise KeyError(f"unknown todo: {todo_id}")
        todo = self.todos[todo_id]
        if "title" in changes and changes["title"] is not None:
            todo.title = str(changes["title"])
        if "blocked_by" in changes and changes["blocked_by"] is not None:
            todo.blocked_by = list(changes["blocked_by"])
        if "status" in changes and changes["status"] is not None:
            status = str(changes["status"])
            if status not in VALID_STATUSES:
                raise ValueError(f"invalid status: {status}")
            todo.status = status
        self._normalize()
        self._persist(todo)
        self.turns_without_update = 0
        return todo

    def write(self, todos: list[dict[str, Any]]) -> list[TodoItem]:
        changed = []
        for item in todos:
            todo_id = item.get("id")
            if todo_id and todo_id in self.todos:
                changed.append(self.update(str(todo_id), **item))
            else:
                changed.append(
                    self.create(
                        title=str(item["title"]),
                        status=str(item.get("status", "pending")),
                        blocked_by=list(item.get("blocked_by", item.get("blockedBy", []))),
                        todo_id=str(todo_id) if todo_id else None,
                    )
                )
        return changed

    def list(self) -> list[dict[str, Any]]:
        return [asdict(todo) for todo in self.todos.values()]

    def tick_without_update(self) -> str | None:
        self.turns_without_update += 1
        if self.todos and self.turns_without_update >= 3:
            return "Reminder: update the todo list before continuing complex work."
        return None

    def load(self) -> None:
        self.todos.clear()
        for path in self.task_dir.glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.todos[data["id"]] = TodoItem(**data)
        self._normalize()

    def _normalize(self) -> None:
        completed = {
            todo.id for todo in self.todos.values() if todo.status == "completed"
        }
        for todo in self.todos.values():
            if todo.blocked_by and not set(todo.blocked_by).issubset(completed):
                todo.status = "blocked"
            elif todo.status == "blocked":
                todo.status = "pending"

        active_seen = False
        for todo in self.todos.values():
            if todo.status != "in_progress":
                continue
            if active_seen:
                todo.status = "pending"
            else:
                active_seen = True

    def _persist(self, todo: TodoItem) -> None:
        path = self.task_dir / f"{todo.id}.json"
        path.write_text(json.dumps(asdict(todo), ensure_ascii=False, indent=2), encoding="utf-8")


class TodoWriteTool(Tool):
    """Tool wrapper for TaskManager.write."""

    name = "TodoWrite"

    def __init__(self, manager: TaskManager) -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Create or update the agent todo list.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": sorted(VALID_STATUSES),
                                },
                                "blocked_by": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["title"],
                        },
                    }
                },
                "required": ["todos"],
            },
        }

    def execute(self, todos: list[dict[str, Any]]) -> str:
        changed = self.manager.write(todos)
        return json.dumps([asdict(todo) for todo in changed], ensure_ascii=False)

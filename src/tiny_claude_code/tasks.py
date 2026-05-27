"""Todo and task tracking for agent work."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4
from tiny_claude_code.tools.base import Tool
VALID_STATUSES = {'pending', 'in_progress', 'completed', 'blocked'}

@dataclass
class TodoItem:
    title: str
    id: str = field(default_factory=lambda: uuid4().hex[:8])
    status: str = 'pending'
    blocked_by: list[str] = field(default_factory=list)

class TaskManager:
    """Persistent todo list with simple dependency rules."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def create(self, title: str, status: str='pending', blocked_by: list[str] | None=None, todo_id: str | None=None) -> TodoItem:
        raise NotImplementedError('TODO: implement create')

    def update(self, todo_id: str, **changes: Any) -> TodoItem:
        raise NotImplementedError('TODO: implement update')

    def write(self, todos: list[dict[str, Any]]) -> list[TodoItem]:
        raise NotImplementedError('TODO: implement write')

    def list(self) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement list')

    def tick_without_update(self) -> str | None:
        raise NotImplementedError('TODO: implement tick_without_update')

    def load(self) -> None:
        raise NotImplementedError('TODO: implement load')

    def _normalize(self) -> None:
        raise NotImplementedError('TODO: implement _normalize')

    def _persist(self, todo: TodoItem) -> None:
        raise NotImplementedError('TODO: implement _persist')

class TodoWriteTool(Tool):
    """Tool wrapper for TaskManager.write."""
    name = 'TodoWrite'

    def __init__(self, manager: TaskManager) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, todos: list[dict[str, Any]]) -> str:
        raise NotImplementedError('TODO: implement execute')

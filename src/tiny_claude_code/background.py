"""Background command execution."""
from __future__ import annotations
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4
from tiny_claude_code.tools.base import Tool

@dataclass
class BackgroundTask:
    id: str
    command: str
    future: Future[str]

class BackgroundManager:
    """Run shell commands without blocking the main conversation."""

    def __init__(self, workspace: str | Path | None=None, max_workers: int=4, timeout: int=300) -> None:
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.timeout = timeout
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.tasks: dict[str, BackgroundTask] = {}
        self._notified: set[str] = set()

    def submit(self, command: str) -> str:
        task_id = uuid4().hex[:8]
        future = self.executor.submit(self._run, command)
        self.tasks[task_id] = BackgroundTask(task_id, command, future)
        return task_id

    def poll(self, task_id: str) -> dict[str, Any]:
        task = self._get(task_id)
        if not task.future.done():
            return {"id": task_id, "status": "running", "command": task.command}
        return {
            "id": task_id,
            "status": "completed",
            "command": task.command,
            "result": task.future.result(),
        }

    def get_result(self, task_id: str) -> str:
        task = self._get(task_id)
        if not task.future.done():
            return "Task is still running"
        return task.future.result()

    def completed_notifications(self) -> list[str]:
        notes = []
        for task_id, task in self.tasks.items():
            if task.future.done() and task_id not in self._notified:
                notes.append(f"Background task {task_id} completed:\n{task.future.result()}")
                self._notified.add(task_id)
        return notes

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _run(self, command: str) -> str:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                cwd=self.workspace,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {self.timeout}s"
        parts = [f"exit_code: {result.returncode}"]
        if result.stdout:
            parts.append(f"stdout:\n{result.stdout.rstrip()}")
        if result.stderr:
            parts.append(f"stderr:\n{result.stderr.rstrip()}")
        return "\n".join(parts)

    def _get(self, task_id: str) -> BackgroundTask:
        if task_id not in self.tasks:
            raise KeyError(f"unknown background task: {task_id}")
        return self.tasks[task_id]


class BackgroundSubmitTool(Tool):
    name = 'BackgroundSubmit'

    def __init__(self, manager: BackgroundManager) -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Run a shell command in the background without blocking.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run."}
                },
                "required": ["command"],
            },
        }

    def execute(self, command: str) -> str:
        task_id = self.manager.submit(command)
        return f"background_task_id: {task_id}"


class BackgroundPollTool(Tool):
    name = 'BackgroundPoll'

    def __init__(self, manager: BackgroundManager) -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Poll the status of a background task.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID from BackgroundSubmit."}
                },
                "required": ["task_id"],
            },
        }

    def execute(self, task_id: str) -> str:
        return str(self.manager.poll(task_id))

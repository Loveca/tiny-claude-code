"""Workflow tools — run, inspect, and approve workflows from the model."""

from __future__ import annotations

from typing import Any

from tiny_claude_code_ref.tools.base import Tool
from tiny_claude_code_ref.workflow import WorkflowManager, format_run_result


class WorkflowRunTool(Tool):
    name = "WorkflowRun"

    def __init__(self, manager: WorkflowManager, registry: Any) -> None:
        self.manager = manager
        self.registry = registry

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Run a declared workflow by name and report the run status.",
            "input_schema": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        }

    def execute(self, name: str) -> str:
        return format_run_result(self.manager.run(name, self.registry))


class WorkflowStatusTool(Tool):
    name = "WorkflowStatus"

    def __init__(self, manager: WorkflowManager) -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Show the step statuses of a workflow run (latest by default).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                },
            },
        }

    def execute(self, run_id: str | None = None) -> str:
        result = self.manager.status(run_id)
        if result is None:
            return "No workflow runs yet."
        return format_run_result(result)


class WorkflowApproveTool(Tool):
    name = "WorkflowApprove"

    def __init__(self, manager: WorkflowManager, registry: Any) -> None:
        self.manager = manager
        self.registry = registry

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Approve or deny a workflow run waiting for approval.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["approve", "deny"]},
                    "comment": {"type": "string"},
                },
                "required": ["decision"],
            },
        }

    def execute(
        self, decision: str, run_id: str | None = None, comment: str = ""
    ) -> str:
        decision = decision.strip().lower()
        if decision not in ("approve", "deny"):
            raise ValueError("decision must be 'approve' or 'deny'")
        target = run_id
        if target is None:
            target = self.manager.latest_run_id()
            if target is None:
                return "No workflow runs yet."
        result = self.manager.approve(
            target, self.registry, approved=decision == "approve", comment=comment
        )
        return format_run_result(result)

"""Workflow tools — run, inspect, and approve workflows from the model.

ch19: implement WorkflowRun, WorkflowStatus and WorkflowApprove.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from tiny_claude_code.tools.base import Tool
if TYPE_CHECKING:
    from tiny_claude_code.workflow import WorkflowManager

class WorkflowRunTool(Tool):
    name = 'WorkflowRun'

    def __init__(self, manager: 'WorkflowManager', registry: Any) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, name: str) -> str:
        raise NotImplementedError('TODO: implement execute')

class WorkflowStatusTool(Tool):
    name = 'WorkflowStatus'

    def __init__(self, manager: 'WorkflowManager') -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, run_id: str | None=None) -> str:
        raise NotImplementedError('TODO: implement execute')

class WorkflowApproveTool(Tool):
    name = 'WorkflowApprove'

    def __init__(self, manager: 'WorkflowManager', registry: Any) -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, decision: str, run_id: str | None=None, comment: str='') -> str:
        raise NotImplementedError('TODO: implement execute')

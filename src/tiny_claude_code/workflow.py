"""Workflow runtime — declared step graphs with retries and run records.

ch19: implement the engine that owns control flow. ``tool`` steps reuse the
registry, ``agent`` steps run one bounded agent_loop, ``approval`` steps pause
the run until a human decides, and every state change is persisted to disk.
"""
from __future__ import annotations
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
AGENT_STEP_TURNS = 4
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STEP_TYPES = ('tool', 'agent', 'approval')

class WorkflowError(RuntimeError):
    """Raised when a workflow definition or run cannot be used."""

@dataclass
class WorkflowStep:
    id: str
    type: str
    tool: str=''
    input: dict[str, Any]=field(default_factory=dict)
    prompt: str=''
    message: str=''
    depends_on: list[str]=field(default_factory=list)
    max_retries: int=0

@dataclass
class WorkflowDef:
    name: str
    description: str=''
    steps: list[WorkflowStep]=field(default_factory=list)

@dataclass
class StepRecord:
    """One step's progress inside a run."""
    status: str='pending'
    attempts: int=0
    output: str=''
    error: str=''

@dataclass
class WorkflowRun:
    """The full state of one workflow execution, persisted as JSON."""
    run_id: str
    name: str
    status: str='running'
    steps: dict[str, StepRecord]=field(default_factory=dict)
    reason: str=''
    created_at: str=''

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement to_dict')

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRun:
        raise NotImplementedError('TODO: implement from_dict')

def parse_definition(data: Any) -> WorkflowDef:
    """Build a WorkflowDef from parsed JSON, raising WorkflowError on shape errors."""
    raise NotImplementedError('TODO: implement parse_definition')

def format_run_result(result: dict[str, Any]) -> str:
    """Render a run result dict for the CLI and workflow tools."""
    raise NotImplementedError('TODO: implement format_run_result')

class WorkflowManager:
    """Execute declared workflows with deterministic scheduling."""

    def __init__(self, client: Any, *, workspace: str | Path | None=None, system: str | None=None, agent_max_turns: int=AGENT_STEP_TURNS, hooks: Any=None, error_handler: Any=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def load_definitions(self, directory: str | Path) -> list[str]:
        """Load every *.json workflow in a directory; return loaded names."""
        raise NotImplementedError('TODO: implement load_definitions')

    def register_definition(self, definition: WorkflowDef) -> None:
        raise NotImplementedError('TODO: implement register_definition')

    def validate(self, definition: WorkflowDef) -> None:
        """Reject graphs that could never be scheduled."""
        raise NotImplementedError('TODO: implement validate')

    def run(self, name: str, registry: Any) -> dict[str, Any]:
        """Run a declared workflow to completion (or its first failure)."""
        raise NotImplementedError('TODO: implement run')

    def resume(self, run_id: str, registry: Any) -> dict[str, Any]:
        """Continue a run left in running state by an interrupted process."""
        raise NotImplementedError('TODO: implement resume')

    def approve(self, run_id: str, registry: Any, *, approved: bool, comment: str='') -> dict[str, Any]:
        """Resolve the waiting approval step and continue (or stop) the run."""
        raise NotImplementedError('TODO: implement approve')

    def status(self, run_id: str | None=None) -> dict[str, Any] | None:
        """Return the result dict of a run, or of the latest run."""
        raise NotImplementedError('TODO: implement status')

    def latest_run_id(self) -> str | None:
        """The most recently created run, preferring the on-disk record."""
        raise NotImplementedError('TODO: implement latest_run_id')

"""Workflow runtime — declared step graphs with retries and run records.

ch19: the engine owns control flow; the model only fills ``agent`` steps.
``tool`` steps reuse the registry and its ``Error: ...`` failure convention,
``agent`` steps run one bounded agent_loop, ``approval`` steps pause the run
until a human approves or denies, and every state change is persisted so a
run can be inspected and continued later.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from tiny_claude_code_ref.agent import agent_loop

AGENT_STEP_TURNS = 4
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STEP_TYPES = ("tool", "agent", "approval")


class WorkflowError(RuntimeError):
    """Raised when a workflow definition or run cannot be used."""


@dataclass
class WorkflowStep:
    id: str
    type: str
    tool: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    prompt: str = ""
    message: str = ""
    depends_on: list[str] = field(default_factory=list)
    max_retries: int = 0


@dataclass
class WorkflowDef:
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)


@dataclass
class StepRecord:
    status: str = "pending"  # pending|running|done|failed|skipped|waiting
    attempts: int = 0
    output: str = ""
    error: str = ""


@dataclass
class WorkflowRun:
    run_id: str
    name: str
    status: str = "running"  # running|waiting_approval|done|failed|denied
    steps: dict[str, StepRecord] = field(default_factory=dict)
    reason: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at,
            "steps": {sid: asdict(rec) for sid, rec in self.steps.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowRun:
        steps = {sid: StepRecord(**rec) for sid, rec in data.get("steps", {}).items()}
        return cls(
            run_id=data["run_id"],
            name=data["name"],
            status=data.get("status", "running"),
            steps=steps,
            reason=data.get("reason", ""),
            created_at=data.get("created_at", ""),
        )


def parse_definition(data: Any) -> WorkflowDef:
    """Build a WorkflowDef from parsed JSON, raising WorkflowError on shape errors."""
    if not isinstance(data, dict):
        raise WorkflowError("workflow definition must be a JSON object")
    name = data.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        raise WorkflowError(f"invalid workflow name: {name!r}")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise WorkflowError(f"workflow '{name}' must have a non-empty steps list")
    steps = [_parse_step(item) for item in raw_steps]
    return WorkflowDef(
        name=name, description=str(data.get("description", "")), steps=steps
    )


def _parse_step(data: Any) -> WorkflowStep:
    if not isinstance(data, dict):
        raise WorkflowError("each workflow step must be a JSON object")
    step_id = data.get("id")
    if not isinstance(step_id, str) or not NAME_PATTERN.match(step_id):
        raise WorkflowError(f"invalid step id: {step_id!r}")
    step_type = data.get("type")
    if step_type not in STEP_TYPES:
        supported = ", ".join(STEP_TYPES)
        raise WorkflowError(
            f"step '{step_id}' has unsupported type {step_type!r} (supported: {supported})"
        )
    deps = data.get("depends_on", [])
    if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
        raise WorkflowError(f"step '{step_id}' depends_on must be a list of step ids")
    retries = data.get("max_retries", 0)
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise WorkflowError(
            f"step '{step_id}' max_retries must be a non-negative integer"
        )
    step_input = data.get("input", {})
    if not isinstance(step_input, dict):
        raise WorkflowError(f"step '{step_id}' input must be a JSON object")
    return WorkflowStep(
        id=step_id,
        type=step_type,
        tool=str(data.get("tool", "")),
        input=dict(step_input),
        prompt=str(data.get("prompt", "")),
        message=str(data.get("message", "")),
        depends_on=list(deps),
        max_retries=retries,
    )


def format_run_result(result: dict[str, Any]) -> str:
    """Render a run result dict for the CLI and workflow tools."""
    lines = [f"run {result['run_id']} [{result['name']}] -> {result['status']}"]
    if result.get("reason"):
        lines.append(f"reason: {result['reason']}")
    for sid, info in result["steps"].items():
        line = f"  {sid}: {info['status']} (attempts {info['attempts']})"
        if info.get("error"):
            line += f" - {info['error']}"
        lines.append(line)
    return "\n".join(lines)


class WorkflowManager:
    """Execute declared workflows with deterministic scheduling."""

    def __init__(
        self,
        client: Any,
        *,
        workspace: str | Path | None = None,
        system: str | None = None,
        agent_max_turns: int = AGENT_STEP_TURNS,
        hooks: Any = None,
        error_handler: Any = None,
    ) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.runs_dir = self.workspace / ".tiny-claude-code" / "workflows" / "runs"
        self.client = client
        self.system = system
        self.agent_max_turns = agent_max_turns
        self.hooks = hooks
        self.error_handler = error_handler
        self.definitions: dict[str, WorkflowDef] = {}
        self.runs: dict[str, WorkflowRun] = {}

    def load_definitions(self, directory: str | Path) -> list[str]:
        """Load every ``*.json`` workflow in a directory; return loaded names."""
        directory = Path(directory)
        if not directory.exists():
            return []
        loaded = []
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise WorkflowError(
                    f"cannot load workflow from {path.name}: {exc}"
                ) from exc
            definition = parse_definition(data)
            if definition.name in self.definitions:
                raise WorkflowError(
                    f"duplicate workflow name '{definition.name}' in {path.name}"
                )
            self.definitions[definition.name] = definition
            loaded.append(definition.name)
        return loaded

    def register_definition(self, definition: WorkflowDef) -> None:
        self.validate(definition)
        self.definitions[definition.name] = definition

    def validate(self, definition: WorkflowDef) -> None:
        """Reject graphs that could never be scheduled."""
        if not definition.steps:
            raise WorkflowError(f"workflow '{definition.name}' must have at least one step")
        seen = set()
        for step in definition.steps:
            if step.id in seen:
                raise WorkflowError(
                    f"duplicate step id '{step.id}' in workflow '{definition.name}'"
                )
            seen.add(step.id)
        for step in definition.steps:
            for dep in step.depends_on:
                if dep not in seen:
                    raise WorkflowError(
                        f"step '{step.id}' depends on unknown step '{dep}'"
                    )
            if step.type == "tool" and not step.tool:
                raise WorkflowError(f"step '{step.id}' is a tool step but has no tool")
            if step.type == "agent" and not step.prompt:
                raise WorkflowError(
                    f"step '{step.id}' is an agent step but has no prompt"
                )
        self._check_acyclic(definition)

    def run(self, name: str, registry: Any) -> dict[str, Any]:
        """Run a declared workflow to completion (or its first failure)."""
        definition = self.definitions.get(name)
        if definition is None:
            raise WorkflowError(f"unknown workflow '{name}'")
        self.validate(definition)
        run_id = f"{name}-{uuid4().hex[:8]}"
        record = WorkflowRun(
            run_id=run_id,
            name=name,
            steps={step.id: StepRecord() for step in definition.steps},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.runs[run_id] = record
        self._save(record)
        return self._drive(definition, record, registry)

    def resume(self, run_id: str, registry: Any) -> dict[str, Any]:
        """Continue a run left in ``running`` state by an interrupted process."""
        record = self._load(run_id)
        if record.status != "running":
            raise WorkflowError(f"run '{run_id}' is {record.status}, not resumable")
        definition = self._definition_for(record)
        return self._drive(definition, record, registry)

    def approve(
        self,
        run_id: str,
        registry: Any,
        *,
        approved: bool,
        comment: str = "",
    ) -> dict[str, Any]:
        """Resolve the waiting approval step and continue (or stop) the run."""
        record = self._load(run_id)
        if record.status != "waiting_approval":
            raise WorkflowError(
                f"run '{run_id}' is {record.status}, not waiting for approval"
            )
        definition = self._definition_for(record)
        waiting = self._waiting_step(record)
        if approved:
            record.steps[waiting].status = "done"
            record.steps[waiting].output = comment or "approved"
            self._save(record)
            record.status = "running"
            return self._drive(definition, record, registry)
        record.steps[waiting].status = "skipped"
        record.steps[waiting].error = comment or "denied"
        for rec in record.steps.values():
            if rec.status == "pending":
                rec.status = "skipped"
        record.status = "denied"
        record.reason = comment or "denied by approver"
        self._save(record)
        return self._result(record)

    def status(self, run_id: str | None = None) -> dict[str, Any] | None:
        """Return the result dict of a run, or of the latest run."""
        if run_id is None:
            run_id = self.latest_run_id()
            if run_id is None:
                return None
        record = self._load(run_id)
        return self._result(record)

    def latest_run_id(self) -> str | None:
        """The most recently created run, preferring the on-disk record."""
        best: tuple[str, str] | None = None
        for path in self.runs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                created = str(data.get("created_at", ""))
            except (OSError, json.JSONDecodeError):
                continue
            key = (created, path.stem)
            if best is None or key > best:
                best = key
        if best is not None:
            return best[1]
        if self.runs:
            return next(reversed(self.runs))
        return None

    def _drive(
        self, definition: WorkflowDef, record: WorkflowRun, registry: Any
    ) -> dict[str, Any]:
        while record.status == "running":
            progressed = False
            for step in definition.steps:
                rec = record.steps[step.id]
                if rec.status != "pending":
                    continue
                deps = [record.steps[dep] for dep in step.depends_on]
                if any(dep.status == "skipped" for dep in deps):
                    rec.status = "skipped"
                    progressed = True
                    self._save(record)
                    continue
                if any(dep.status != "done" for dep in deps):
                    continue
                if step.type == "approval":
                    rec.status = "waiting"
                    record.status = "waiting_approval"
                    self._save(record)
                    break
                self._execute(step, rec, record, registry)
                progressed = True
                self._save(record)
                if record.status == "failed":
                    break
            if record.status == "running" and not progressed:
                record.status = "done"
                self._save(record)
        return self._result(record)

    def _execute(
        self, step: WorkflowStep, rec: StepRecord, record: WorkflowRun, registry: Any
    ) -> None:
        max_attempts = 1 + max(0, step.max_retries)
        while rec.attempts < max_attempts:
            rec.attempts += 1
            try:
                output = self._run_step(step, record, registry)
            except Exception as exc:  # noqa: BLE001 - failures become retryable results
                output = f"Error: {exc}"
            if not output.startswith("Error:"):
                rec.status = "done"
                rec.output = output
                return
            rec.error = output
        rec.status = "failed"
        record.status = "failed"
        record.reason = (
            f"step '{step.id}' failed after {rec.attempts} attempt(s): {rec.error}"
        )

    def _run_step(
        self, step: WorkflowStep, record: WorkflowRun, registry: Any
    ) -> str:
        if step.type == "tool":
            tool_input = {
                key: self._substitute(value, record)
                for key, value in step.input.items()
            }
            return str(registry.dispatch(step.tool, tool_input))
        prompt = self._substitute(step.prompt, record)
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        return agent_loop(
            messages,
            tool_handlers=registry,
            client=self.client,
            system=self.system,
            hooks=self.hooks,
            error_handler=self.error_handler,
            max_turns=self.agent_max_turns,
        )

    def _substitute(self, value: Any, record: WorkflowRun) -> Any:
        if not isinstance(value, str):
            return value
        for sid, rec in record.steps.items():
            if rec.status == "done":
                value = value.replace("{outputs." + sid + "}", rec.output)
        return value

    def _save(self, record: WorkflowRun) -> None:
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        path = self.runs_dir / f"{record.run_id}.json"
        path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self, run_id: str) -> WorkflowRun:
        if not isinstance(run_id, str) or not NAME_PATTERN.match(run_id):
            raise WorkflowError(f"invalid run id: {run_id!r}")
        record = self.runs.get(run_id)
        if record is not None:
            return record
        path = self.runs_dir / f"{run_id}.json"
        if not path.exists():
            raise WorkflowError(f"unknown run '{run_id}'")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WorkflowError(f"cannot load run '{run_id}': {exc}") from exc
        record = WorkflowRun.from_dict(data)
        self.runs[run_id] = record
        return record

    def _definition_for(self, record: WorkflowRun) -> WorkflowDef:
        definition = self.definitions.get(record.name)
        if definition is None:
            raise WorkflowError(
                f"unknown workflow '{record.name}': cannot continue run '{record.run_id}'"
            )
        self.validate(definition)
        return definition

    def _waiting_step(self, record: WorkflowRun) -> str:
        waiting = [sid for sid, rec in record.steps.items() if rec.status == "waiting"]
        if len(waiting) != 1:
            raise WorkflowError(
                f"run '{record.run_id}' has no single waiting approval step"
            )
        return waiting[0]

    def _result(self, record: WorkflowRun) -> dict[str, Any]:
        return {
            "run_id": record.run_id,
            "name": record.name,
            "status": record.status,
            "reason": record.reason,
            "steps": {
                sid: {
                    "status": rec.status,
                    "attempts": rec.attempts,
                    "output": rec.output,
                    "error": rec.error,
                }
                for sid, rec in record.steps.items()
            },
        }

    def _check_acyclic(self, definition: WorkflowDef) -> None:
        remaining = {step.id: set(step.depends_on) for step in definition.steps}
        while remaining:
            ready = [sid for sid, deps in remaining.items() if not deps]
            if not ready:
                cycle = ", ".join(sorted(remaining))
                raise WorkflowError(
                    f"dependency cycle detected in workflow '{definition.name}': {cycle}"
                )
            for sid in ready:
                del remaining[sid]
            for deps in remaining.values():
                deps.difference_update(ready)

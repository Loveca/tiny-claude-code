"""Tests for ch19: the workflow engine core."""

from __future__ import annotations

import json

import pytest

from conftest import MockLLMClient
from tiny_claude_code.tools import ToolRegistry
from tiny_claude_code.tools.base import Tool
from tiny_claude_code.workflow import (
    WorkflowDef,
    WorkflowError,
    WorkflowManager,
    WorkflowStep,
    format_run_result,
    parse_definition,
)


class EchoTool(Tool):
    """Records inputs and returns them, so tests can assert order."""

    name = "echo"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": "Echo the input text",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
            },
        }

    def execute(self, **kwargs) -> str:
        self.calls.append(dict(kwargs))
        return f"echo:{kwargs.get('text', '')}"


class FlakyTool(Tool):
    """Fails the first N calls, then succeeds."""

    name = "flaky"

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.calls = 0

    @property
    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": "Fails then succeeds",
            "input_schema": {"type": "object", "properties": {}},
        }

    def execute(self, **kwargs) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(f"flaky failure {self.calls}")
        return "ok"


class RecordingClient(MockLLMClient):
    """MockLLMClient that also records the messages it is called with."""

    def __init__(self) -> None:
        super().__init__()
        self.last_messages = None

    def chat(self, messages, **kwargs):
        self.last_messages = messages
        return super().chat(messages, **kwargs)


def make_manager(tmp_path, client=None, **kwargs) -> WorkflowManager:
    return WorkflowManager(client, workspace=tmp_path, **kwargs)


def make_registry(*tools) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_linear_tool_workflow_runs_to_done(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(
            name="linear",
            steps=[
                WorkflowStep(id="first", type="tool", tool="echo", input={"text": "hello"}),
                WorkflowStep(
                    id="second",
                    type="tool",
                    tool="echo",
                    input={"text": "after {outputs.first}"},
                    depends_on=["first"],
                ),
            ],
        )
    )

    result = manager.run("linear", make_registry(echo))

    assert result["status"] == "done"
    assert result["steps"]["first"]["output"] == "echo:hello"
    assert result["steps"]["second"]["output"] == "echo:after echo:hello"
    assert [call["text"] for call in echo.calls] == ["hello", "after echo:hello"]


def test_dag_scheduling_survives_out_of_order_declaration(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(
            name="dag",
            steps=[
                WorkflowStep(
                    id="c", type="tool", tool="echo", input={"text": "c"},
                    depends_on=["a", "b"],
                ),
                WorkflowStep(id="b", type="tool", tool="echo", input={"text": "b"},
                             depends_on=["a"]),
                WorkflowStep(id="a", type="tool", tool="echo", input={"text": "a"}),
            ],
        )
    )

    result = manager.run("dag", make_registry(echo))

    assert result["status"] == "done"
    assert [call["text"] for call in echo.calls] == ["a", "b", "c"]


def test_unknown_workflow_name_is_rejected(tmp_path):
    manager = make_manager(tmp_path)
    with pytest.raises(WorkflowError, match="unknown workflow 'nope'"):
        manager.run("nope", make_registry())


def test_validation_rejects_duplicate_step_ids():
    manager = WorkflowManager(None)
    definition = WorkflowDef(
        name="dupe",
        steps=[
            WorkflowStep(id="a", type="tool", tool="echo"),
            WorkflowStep(id="a", type="tool", tool="echo"),
        ],
    )
    with pytest.raises(WorkflowError, match="duplicate step id 'a'"):
        manager.validate(definition)


def test_validation_rejects_unknown_dependency():
    manager = WorkflowManager(None)
    definition = WorkflowDef(
        name="orphan",
        steps=[
            WorkflowStep(id="a", type="tool", tool="echo", depends_on=["ghost"]),
        ],
    )
    with pytest.raises(WorkflowError, match="unknown step 'ghost'"):
        manager.validate(definition)


def test_validation_rejects_dependency_cycles():
    manager = WorkflowManager(None)
    definition = WorkflowDef(
        name="cyclic",
        steps=[
            WorkflowStep(id="a", type="tool", tool="echo", depends_on=["b"]),
            WorkflowStep(id="b", type="tool", tool="echo", depends_on=["a"]),
        ],
    )
    with pytest.raises(WorkflowError, match="dependency cycle"):
        manager.validate(definition)


def test_validation_rejects_tool_step_without_tool():
    manager = WorkflowManager(None)
    definition = WorkflowDef(name="notool", steps=[WorkflowStep(id="a", type="tool")])
    with pytest.raises(WorkflowError, match="has no tool"):
        manager.validate(definition)


def test_validation_rejects_agent_step_without_prompt():
    manager = WorkflowManager(None)
    definition = WorkflowDef(name="noprompt", steps=[WorkflowStep(id="a", type="agent")])
    with pytest.raises(WorkflowError, match="has no prompt"):
        manager.validate(definition)


def test_parse_definition_rejects_bad_shapes():
    with pytest.raises(WorkflowError, match="invalid workflow name"):
        parse_definition({"name": "bad name!", "steps": [{"id": "a", "type": "tool"}]})
    with pytest.raises(WorkflowError, match="non-empty steps"):
        parse_definition({"name": "ok-name", "steps": []})
    with pytest.raises(WorkflowError, match="unsupported type"):
        parse_definition({"name": "ok-name", "steps": [{"id": "a", "type": "shell"}]})
    with pytest.raises(WorkflowError, match="invalid step id"):
        parse_definition(
            {"name": "ok-name", "steps": [{"id": "bad id", "type": "tool"}]}
        )
    with pytest.raises(WorkflowError, match="input must be a JSON object"):
        parse_definition(
            {"name": "ok-name", "steps": [{"id": "a", "type": "tool", "input": [1]}]}
        )


def test_retry_records_attempts_and_recovers(tmp_path):
    flaky = FlakyTool(failures=1)
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(
            name="retry",
            steps=[
                WorkflowStep(id="a", type="tool", tool="flaky", max_retries=2),
            ],
        )
    )

    result = manager.run("retry", make_registry(flaky))

    assert result["status"] == "done"
    assert result["steps"]["a"]["attempts"] == 2
    assert flaky.calls == 2


def test_retry_exhaustion_fails_the_run(tmp_path):
    flaky = FlakyTool(failures=99)
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(
            name="doomed",
            steps=[
                WorkflowStep(id="a", type="tool", tool="flaky", max_retries=1),
                WorkflowStep(id="b", type="tool", tool="flaky", depends_on=["a"]),
            ],
        )
    )

    result = manager.run("doomed", make_registry(flaky))

    assert result["status"] == "failed"
    assert result["steps"]["a"]["status"] == "failed"
    assert result["steps"]["a"]["attempts"] == 2
    assert result["steps"]["b"]["status"] == "pending"
    assert "failed after 2 attempt(s)" in result["reason"]
    assert flaky.calls == 2


def test_agent_step_runs_a_bounded_loop(tmp_path):
    client = MockLLMClient()
    client.add_tool_use_response("echo", {"text": "hi"})
    client.add_text_response("final answer")
    echo = EchoTool()
    manager = make_manager(tmp_path, client=client, system="workflow system")
    manager.register_definition(
        WorkflowDef(
            name="draft",
            steps=[WorkflowStep(id="a", type="agent", prompt="say hi")],
        )
    )

    result = manager.run("draft", make_registry(echo))

    assert result["status"] == "done"
    assert result["steps"]["a"]["output"] == "final answer"
    assert echo.calls == [{"text": "hi"}]
    assert client.last_system == "workflow system"


def test_agent_step_turn_budget_fails_the_step(tmp_path):
    client = MockLLMClient()
    for _ in range(5):
        client.add_tool_use_response("echo", {"text": "again"})
    echo = EchoTool()
    manager = make_manager(tmp_path, client=client, agent_max_turns=2)
    manager.register_definition(
        WorkflowDef(
            name="spinner",
            steps=[WorkflowStep(id="a", type="agent", prompt="loop")],
        )
    )

    result = manager.run("spinner", make_registry(echo))

    assert result["status"] == "failed"
    assert result["steps"]["a"]["status"] == "failed"
    assert result["steps"]["a"]["attempts"] == 1
    assert echo.calls == [{"text": "again"}, {"text": "again"}]


def test_substitution_reaches_agent_prompts(tmp_path):
    client = RecordingClient()
    client.add_text_response("done")
    echo = EchoTool()
    manager = make_manager(tmp_path, client=client)
    manager.register_definition(
        WorkflowDef(
            name="pipeline",
            steps=[
                WorkflowStep(id="first", type="tool", tool="echo", input={"text": "hello"}),
                WorkflowStep(
                    id="second",
                    type="agent",
                    prompt="Context: {outputs.first}",
                    depends_on=["first"],
                ),
            ],
        )
    )

    result = manager.run("pipeline", make_registry(echo))

    assert result["status"] == "done"
    assert client.last_messages[0]["content"] == "Context: echo:hello"


def test_run_records_are_persisted_and_reloadable(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(name="recorded", steps=[WorkflowStep(id="a", type="tool", tool="echo")])
    )
    result = manager.run("recorded", make_registry(echo))

    files = list((tmp_path / ".tiny-claude-code" / "workflows" / "runs").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["status"] == "done"

    fresh = make_manager(tmp_path)
    assert fresh.status(result["run_id"]) == result
    assert fresh.status() == result
    assert fresh.latest_run_id() == result["run_id"]


def test_status_rejects_unknown_and_invalid_run_ids(tmp_path):
    manager = make_manager(tmp_path)
    with pytest.raises(WorkflowError, match="unknown run 'ghost-00000000'"):
        manager.status("ghost-00000000")
    with pytest.raises(WorkflowError, match="invalid run id"):
        manager.status("../escape")


def test_load_definitions_from_directory(tmp_path):
    defs_dir = tmp_path / "workflows"
    defs_dir.mkdir()
    (defs_dir / "alpha.json").write_text(
        json.dumps(
            {
                "name": "alpha",
                "steps": [{"id": "a", "type": "tool", "tool": "echo"}],
            }
        ),
        encoding="utf-8",
    )
    (defs_dir / "beta.json").write_text(
        json.dumps(
            {
                "name": "beta",
                "steps": [{"id": "b", "type": "tool", "tool": "echo"}],
            }
        ),
        encoding="utf-8",
    )
    (defs_dir / "notes.txt").write_text("ignored", encoding="utf-8")

    manager = make_manager(tmp_path)
    loaded = manager.load_definitions(defs_dir)

    assert loaded == ["alpha", "beta"]


def test_load_definitions_rejects_duplicate_names(tmp_path):
    defs_dir = tmp_path / "workflows"
    defs_dir.mkdir()
    for filename in ("one.json", "two.json"):
        (defs_dir / filename).write_text(
            json.dumps(
                {"name": "same", "steps": [{"id": "a", "type": "tool", "tool": "echo"}]}
            ),
            encoding="utf-8",
        )

    manager = make_manager(tmp_path)
    with pytest.raises(WorkflowError, match="duplicate workflow name 'same'"):
        manager.load_definitions(defs_dir)


def test_format_run_result_renders_steps_and_reason():
    result = {
        "run_id": "demo-abc",
        "name": "demo",
        "status": "failed",
        "reason": "step 'a' failed after 2 attempt(s): boom",
        "steps": {
            "a": {"status": "failed", "attempts": 2, "output": "", "error": "Error: boom"},
            "b": {"status": "pending", "attempts": 0, "output": "", "error": ""},
        },
    }

    text = format_run_result(result)

    assert "run demo-abc [demo] -> failed" in text
    assert "reason: step 'a' failed" in text
    assert "a: failed (attempts 2)" in text
    assert "b: pending (attempts 0)" in text


GATED_DEF = WorkflowDef(
    name="gated",
    steps=[
        WorkflowStep(id="collect", type="tool", tool="echo", input={"text": "a"}),
        WorkflowStep(
            id="signoff",
            type="approval",
            message="Publish these notes?",
            depends_on=["collect"],
        ),
        WorkflowStep(
            id="publish",
            type="tool",
            tool="echo",
            input={"text": "published {outputs.collect}"},
            depends_on=["signoff"],
        ),
    ],
)


def test_approval_pauses_then_approve_completes(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(GATED_DEF)

    paused = manager.run("gated", make_registry(echo))

    assert paused["status"] == "waiting_approval"
    assert paused["steps"]["collect"]["status"] == "done"
    assert paused["steps"]["signoff"]["status"] == "waiting"
    assert paused["steps"]["publish"]["status"] == "pending"
    assert [call["text"] for call in echo.calls] == ["a"]

    result = manager.approve(
        paused["run_id"], make_registry(echo), approved=True, comment="lgtm"
    )

    assert result["status"] == "done"
    assert result["steps"]["signoff"]["status"] == "done"
    assert result["steps"]["signoff"]["output"] == "lgtm"
    assert result["steps"]["publish"]["output"] == "echo:published echo:a"


def test_deny_skips_the_rest_of_the_run(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(GATED_DEF)

    paused = manager.run("gated", make_registry(echo))
    result = manager.approve(
        paused["run_id"], make_registry(echo), approved=False, comment="not yet"
    )

    assert result["status"] == "denied"
    assert result["reason"] == "not yet"
    assert result["steps"]["signoff"]["status"] == "skipped"
    assert result["steps"]["publish"]["status"] == "skipped"
    assert [call["text"] for call in echo.calls] == ["a"]


def test_approve_requires_a_waiting_run(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(GATED_DEF)

    with pytest.raises(WorkflowError, match="unknown run 'ghost-00000000'"):
        manager.approve("ghost-00000000", make_registry(echo), approved=True)

    paused = manager.run("gated", make_registry(echo))
    done = manager.approve(paused["run_id"], make_registry(echo), approved=True)
    with pytest.raises(WorkflowError, match="not waiting for approval"):
        manager.approve(done["run_id"], make_registry(echo), approved=True)


def test_approval_survives_a_manager_restart(tmp_path):
    echo = EchoTool()
    first = make_manager(tmp_path)
    first.register_definition(GATED_DEF)
    paused = first.run("gated", make_registry(echo))

    second = make_manager(tmp_path)
    second.register_definition(GATED_DEF)
    result = second.approve(
        paused["run_id"], make_registry(echo), approved=True, comment="ship it"
    )

    assert result["status"] == "done"
    assert result["steps"]["signoff"]["output"] == "ship it"
    assert result["steps"]["publish"]["output"] == "echo:published echo:a"


def test_resume_continues_an_interrupted_run(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(
        WorkflowDef(
            name="half",
            steps=[
                WorkflowStep(id="a", type="tool", tool="echo", input={"text": "hello"}),
                WorkflowStep(
                    id="b",
                    type="tool",
                    tool="echo",
                    input={"text": "after {outputs.a}"},
                    depends_on=["a"],
                ),
            ],
        )
    )
    runs_dir = tmp_path / ".tiny-claude-code" / "workflows" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "half-abcd1234.json").write_text(
        json.dumps(
            {
                "run_id": "half-abcd1234",
                "name": "half",
                "status": "running",
                "reason": "",
                "created_at": "2026-11-22T08:00:00+00:00",
                "steps": {
                    "a": {
                        "status": "done",
                        "attempts": 1,
                        "output": "echo:hello",
                        "error": "",
                    },
                    "b": {"status": "pending", "attempts": 0, "output": "", "error": ""},
                },
            }
        ),
        encoding="utf-8",
    )

    result = manager.resume("half-abcd1234", make_registry(echo))

    assert result["status"] == "done"
    assert result["steps"]["b"]["output"] == "echo:after echo:hello"


def test_resume_rejects_terminal_runs(tmp_path):
    echo = EchoTool()
    manager = make_manager(tmp_path)
    manager.register_definition(GATED_DEF)
    result = manager.run("gated", make_registry(echo))

    assert result["status"] == "waiting_approval"
    with pytest.raises(WorkflowError, match="not resumable"):
        manager.resume(result["run_id"], make_registry(echo))

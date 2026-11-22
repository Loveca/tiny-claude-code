"""Tests for ch19: workflow tools and registry wiring."""

from __future__ import annotations

import pytest

from tiny_claude_code.tools import ToolRegistry, create_default_registry
from tiny_claude_code.tools.base import Tool
from tiny_claude_code.tools.workflow import (
    WorkflowApproveTool,
    WorkflowRunTool,
    WorkflowStatusTool,
)
from tiny_claude_code.workflow import WorkflowDef, WorkflowManager, WorkflowStep


class EchoTool(Tool):
    name = "echo"

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
        return f"echo:{kwargs.get('text', '')}"


GATED_DEF = WorkflowDef(
    name="gated",
    steps=[
        WorkflowStep(id="collect", type="tool", tool="echo", input={"text": "a"}),
        WorkflowStep(id="signoff", type="approval", depends_on=["collect"]),
        WorkflowStep(
            id="publish",
            type="tool",
            tool="echo",
            input={"text": "done"},
            depends_on=["signoff"],
        ),
    ],
)


def make_setup(tmp_path):
    registry = ToolRegistry()
    registry.register(EchoTool())
    manager = WorkflowManager(None, workspace=tmp_path)
    manager.register_definition(GATED_DEF)
    return manager, registry


def test_workflow_run_tool_starts_a_run(tmp_path):
    manager, registry = make_setup(tmp_path)
    tool = WorkflowRunTool(manager, registry)

    output = tool.execute(name="gated")

    assert "-> waiting_approval" in output
    assert "signoff: waiting" in output


def test_workflow_run_tool_reports_unknown_names(tmp_path):
    manager, registry = make_setup(tmp_path)
    tool = WorkflowRunTool(manager, registry)

    with pytest.raises(Exception, match="unknown workflow 'nope'"):
        tool.execute(name="nope")


def test_workflow_status_tool_reports_latest_run(tmp_path):
    manager, registry = make_setup(tmp_path)
    run_tool = WorkflowRunTool(manager, registry)
    status_tool = WorkflowStatusTool(manager)

    assert status_tool.execute() == "No workflow runs yet."

    run_tool.execute(name="gated")
    output = status_tool.execute()

    assert "-> waiting_approval" in output
    assert "collect: done" in output


def test_workflow_approve_tool_resolves_waiting_runs(tmp_path):
    manager, registry = make_setup(tmp_path)
    run_tool = WorkflowRunTool(manager, registry)
    approve_tool = WorkflowApproveTool(manager, registry)

    run_tool.execute(name="gated")
    output = approve_tool.execute(decision="APPROVE", comment="ship it")

    assert "-> done" in output
    assert "signoff: done" in output
    assert "publish: done" in output


def test_workflow_approve_tool_denies_waiting_runs(tmp_path):
    manager, registry = make_setup(tmp_path)
    run_tool = WorkflowRunTool(manager, registry)
    approve_tool = WorkflowApproveTool(manager, registry)

    run_tool.execute(name="gated")
    output = approve_tool.execute(decision="deny", comment="not yet")

    assert "-> denied" in output
    assert "publish: skipped" in output


def test_workflow_approve_tool_rejects_bad_decisions(tmp_path):
    manager, registry = make_setup(tmp_path)
    tool = WorkflowApproveTool(manager, registry)

    with pytest.raises(ValueError, match="decision must be"):
        tool.execute(decision="maybe")


def test_default_registry_registers_workflow_tools(tmp_path):
    manager = WorkflowManager(None, workspace=tmp_path)
    registry = create_default_registry(workspace=tmp_path, workflow_manager=manager)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert {"WorkflowRun", "WorkflowStatus", "WorkflowApprove"} <= names


def test_default_registry_without_workflow_manager(tmp_path):
    registry = create_default_registry(workspace=tmp_path)
    names = {schema["name"] for schema in registry.get_schemas()}

    assert "WorkflowRun" not in names
    assert "WorkflowStatus" not in names
    assert "WorkflowApprove" not in names

"""Tests for ch19: workflows wired into the default registry and CLI."""

from __future__ import annotations

import json

from conftest import MockLLMClient
from tiny_claude_code.cli import handle_workflow_command
from tiny_claude_code.tools import create_default_registry
from tiny_claude_code.workflow import WorkflowManager


PIPELINE = {
    "name": "pipeline",
    "steps": [
        {"id": "draft", "type": "agent", "prompt": "Draft the changelog"},
        {
            "id": "signoff",
            "type": "approval",
            "message": "Write draft.md?",
            "depends_on": ["draft"],
        },
        {
            "id": "publish",
            "type": "tool",
            "tool": "write",
            "input": {"path": "draft.md", "content": "{outputs.draft}"},
            "depends_on": ["signoff"],
        },
    ],
}


def make_setup(tmp_path):
    client = MockLLMClient()
    client.add_text_response("Draft changelog line")
    defs_dir = tmp_path / ".tiny-claude-code" / "workflows"
    defs_dir.mkdir(parents=True)
    (defs_dir / "pipeline.json").write_text(json.dumps(PIPELINE), encoding="utf-8")
    manager = WorkflowManager(client, workspace=tmp_path)
    manager.load_definitions(defs_dir)
    registry = create_default_registry(workspace=tmp_path, workflow_manager=manager)
    return manager, registry


def run_id_of(formatted: str) -> str:
    return formatted.splitlines()[0].split()[1]


def test_workflow_publishes_a_file_after_approval(tmp_path):
    manager, registry = make_setup(tmp_path)

    paused = manager.run("pipeline", registry)

    assert paused["status"] == "waiting_approval"
    assert paused["steps"]["draft"]["output"] == "Draft changelog line"
    assert not (tmp_path / "draft.md").exists()

    result = manager.approve(paused["run_id"], registry, approved=True)

    assert result["status"] == "done"
    assert (tmp_path / "draft.md").read_text(encoding="utf-8") == "Draft changelog line"


def test_workflow_cli_run_status_and_approve(tmp_path):
    manager, registry = make_setup(tmp_path)

    paused = handle_workflow_command(manager, registry, "/workflow pipeline")
    assert "-> waiting_approval" in paused

    status = handle_workflow_command(manager, registry, "/workflow status")
    assert "signoff: waiting" in status
    run_id = run_id_of(status)

    done = handle_workflow_command(
        manager, registry, f"/workflow approve {run_id} approve ship-it"
    )
    assert "-> done" in done
    assert (tmp_path / "draft.md").read_text(encoding="utf-8") == "Draft changelog line"


def test_workflow_cli_deny_and_errors(tmp_path):
    manager, registry = make_setup(tmp_path)

    paused = handle_workflow_command(manager, registry, "/workflow pipeline")
    run_id = run_id_of(paused)

    denied = handle_workflow_command(
        manager, registry, f"/workflow approve {run_id} deny not-ready"
    )
    assert "-> denied" in denied
    assert not (tmp_path / "draft.md").exists()

    usage = handle_workflow_command(manager, registry, "/workflow")
    assert usage.startswith("Usage:")
    assert (
        handle_workflow_command(manager, registry, "/workflow nope")
        == "Error: unknown workflow 'nope'"
    )
    assert "Decision must be" in handle_workflow_command(
        manager, registry, f"/workflow approve {run_id} maybe"
    )
    assert "unknown run 'ghost-00000000'" in handle_workflow_command(
        manager, registry, "/workflow status ghost-00000000"
    )

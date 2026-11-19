"""Tests for ch16: team mailbox and scheduling."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import MockLLMClient
from tiny_claude_code.team import TeamError, TeamManager
from tiny_claude_code.worktree import WorktreeManager


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _init_repo(path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    return path


def _tool_names(manager: TeamManager, name: str) -> set[str]:
    registry = manager.members[name].registry
    return {schema["name"] for schema in registry.get_schemas()}


def test_spawn_queues_task_and_default_tools(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)

    member = team.spawn("alice", "bug fixer", task="fix the cart")

    assert member.status == "idle"
    messages = team.inbox("alice", drain=False)
    assert [(message.sender, message.kind) for message in messages] == [
        ("lead", "task")
    ]
    assert {"bash", "read", "write", "search"} <= _tool_names(team, "alice")


def test_spawn_isolates_workspace_in_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    team = TeamManager(MockLLMClient(), repo)

    member = team.spawn("alice", "bug fixer", task="fix", isolate=True)

    assert member.worktree is not None
    assert member.workspace == member.worktree
    assert member.workspace != repo
    assert member.workspace.is_dir()


def test_spawn_rejects_reserved_duplicate_and_overflow(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path, max_members=2)
    team.spawn("alice", "role")

    with pytest.raises(TeamError, match="reserved"):
        team.spawn("lead", "role")
    with pytest.raises(TeamError, match="already exists"):
        team.spawn("alice", "role")

    team.spawn("bob", "role")
    with pytest.raises(TeamError, match="team is full"):
        team.spawn("carol", "role")


def test_send_and_drain_inbox(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")

    team.send("lead", "alice", "try again")

    assert [message.content for message in team.inbox("alice")] == ["try again"]
    assert team.inbox("alice") == []


def test_broadcast_reaches_other_members_only(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")
    team.spawn("bob", "role")

    team.send("alice", "all", "status update")

    assert [message.content for message in team.inbox("bob")] == ["status update"]
    assert team.inbox("alice") == []


def test_send_rejects_unknown_recipient_and_empty_content(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)

    with pytest.raises(TeamError, match="unknown team member"):
        team.send("lead", "ghost", "hello")
    with pytest.raises(TeamError, match="cannot be empty"):
        team.send("lead", "lead", "   ")


def test_status_reports_members_and_unread_count(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role", task="fix")

    status = team.status()

    assert status[0]["name"] == "alice"
    assert status[0]["status"] == "idle"
    assert status[0]["unread"] == 1


def test_step_marks_done_and_reports_to_lead(tmp_path: Path) -> None:
    client = MockLLMClient()
    client.add_text_response("done fixing")
    team = TeamManager(client, tmp_path)
    team.spawn("alice", "role", task="fix it")

    result = team.step("alice")

    assert result == "done fixing"
    assert team.members["alice"].status == "done"
    lead_mail = team.inbox("lead")
    assert [(m.sender, m.kind, m.content) for m in lead_mail] == [
        ("alice", "result", "done fixing")
    ]


def test_step_executes_tool_batch_then_finishes(tmp_path: Path) -> None:
    client = MockLLMClient()
    client.add_tool_use_response("write", {"path": "note.txt", "content": "hi"})
    client.add_text_response("written")
    team = TeamManager(client, tmp_path)
    team.spawn("alice", "role", task="write a note")

    first = team.step("alice")

    assert "1 tool call" in first
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hi"
    assert team.members["alice"].status == "idle"

    assert team.step("alice") == "written"
    assert team.members["alice"].status == "done"


def test_wait_collects_results_from_all_members(tmp_path: Path) -> None:
    client = MockLLMClient()
    client.add_text_response("alice done")
    client.add_text_response("bob done")
    team = TeamManager(client, tmp_path)
    team.spawn("alice", "role", task="fix a")
    team.spawn("bob", "role", task="fix b")

    summary = team.wait()

    assert summary["rounds"] == 1
    assert sorted(summary["done"]) == ["alice", "bob"]
    assert summary["results"]["alice"] == "alice done"


def test_wait_respects_round_cap(tmp_path: Path) -> None:
    client = MockLLMClient()
    for _ in range(6):
        client.add_tool_use_response("bash", {"command": "echo tick"})
    team = TeamManager(client, tmp_path, max_rounds=2)
    team.spawn("alice", "role", task="loop forever")

    summary = team.wait()

    assert summary["rounds"] == 2
    assert summary["done"] == []


def test_wait_with_no_task_does_not_call_model(tmp_path: Path) -> None:
    client = MockLLMClient()
    team = TeamManager(client, tmp_path)
    team.spawn("alice", "role")

    summary = team.wait()

    assert summary["rounds"] == 0
    assert client._call_count == 0


def test_step_records_client_error(tmp_path: Path) -> None:
    class BrokenClient:
        def chat(self, *args, **kwargs):
            raise RuntimeError("boom")

    team = TeamManager(BrokenClient(), tmp_path)
    team.spawn("alice", "role", task="fail")

    result = team.step("alice")

    assert "boom" in result
    assert team.members["alice"].status == "error"
    assert team.inbox("lead")[0].kind == "result"


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_shutdown_removes_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    team = TeamManager(MockLLMClient(), repo)
    member = team.spawn("alice", "role", isolate=True)
    assert member.worktree is not None
    worktree_path = member.worktree

    team.shutdown("alice")

    assert member.status == "done"
    assert member.worktree is None
    assert not worktree_path.exists()
    assert WorktreeManager(repo).list() == []

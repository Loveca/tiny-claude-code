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

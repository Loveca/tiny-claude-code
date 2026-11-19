"""Tests for ch16: team tool surface."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import MockLLMClient
from tiny_claude_code.team import TeamManager
from tiny_claude_code.tools.team import (
    TeamInboxTool,
    TeamSendTool,
    TeamShutdownTool,
    TeamSpawnTool,
    TeamStatusTool,
    TeamWaitTool,
    WorktreeMergeTool,
)


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


def test_member_registry_has_mailbox_tools_but_no_team_spawn(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")

    schemas = team.members["alice"].registry.get_schemas()
    names = {schema["name"] for schema in schemas}

    assert {"TeamSend", "TeamInbox"} <= names
    assert "TeamSpawn" not in names
    assert "SubAgent" not in names


def test_send_tool_queues_message(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")
    tool = TeamSendTool(team, "alice")

    result = tool.execute("lead", "finished the fix")

    assert "queued" in result
    assert team.inbox("lead")[0].content == "finished the fix"


def test_inbox_tool_formats_and_drains(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role", task="fix the cart")
    tool = TeamInboxTool(team, "alice")

    output = tool.execute()

    assert "lead (task): fix the cart" in output
    assert tool.execute() == "No new messages."


def test_spawn_tool_creates_member_and_queues_task(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    tool = TeamSpawnTool(team)

    result = tool.execute("alice", "bug fixer", task="fix the cart")

    assert "Spawned 'alice'" in result
    assert team.inbox("alice", drain=False)[0].kind == "task"


def test_status_tool_lists_members(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role", task="fix")
    tool = TeamStatusTool(team)

    output = tool.execute()

    assert "alice [idle]" in output
    assert "unread=1" in output


def test_wait_tool_returns_summary(tmp_path: Path) -> None:
    client = MockLLMClient()
    client.add_text_response("alice done")
    team = TeamManager(client, tmp_path)
    team.spawn("alice", "role", task="fix")
    tool = TeamWaitTool(team)

    output = tool.execute()

    assert "rounds=1" in output
    assert "alice" in output
    assert "alice done" in output


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_shutdown_tool_removes_worktree(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    team = TeamManager(MockLLMClient(), repo)
    member = team.spawn("alice", "role", isolate=True)
    worktree_path = member.worktree
    tool = TeamShutdownTool(team)

    tool.execute("alice")

    assert worktree_path is not None
    assert not worktree_path.exists()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_merge_tool_merges_worktree_branch(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    team = TeamManager(MockLLMClient(), repo)
    member = team.spawn("alice", "role", isolate=True)
    assert member.worktree is not None
    (member.worktree / "fix.py").write_text("print('fixed')\n", encoding="utf-8")
    _git(member.worktree, "add", ".")
    _git(member.worktree, "commit", "-q", "-m", "fix from alice")
    tool = WorktreeMergeTool(team)

    result = tool.execute("alice")

    assert "Merged" in result
    assert (repo / "fix.py").is_file()

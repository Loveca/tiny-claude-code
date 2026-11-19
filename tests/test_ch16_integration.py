"""End-to-end tests for ch16: lead + team over the mock LLM."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import MockLLMClient
from tiny_claude_code.agent import agent_loop
from tiny_claude_code.team import TeamManager
from tiny_claude_code.tools import create_default_registry


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


def test_lead_spawns_team_and_waits_for_results(tmp_path: Path) -> None:
    client = MockLLMClient()
    client.add_tool_use_response(
        "TeamSpawn", {"name": "alice", "role": "fixer", "task": "fix a"}
    )
    client.add_tool_use_response(
        "TeamSpawn", {"name": "bob", "role": "fixer", "task": "fix b"}
    )
    client.add_tool_use_response("TeamWait", {})
    client.add_text_response("alice done")
    client.add_text_response("bob done")
    client.add_text_response("all done")
    team = TeamManager(client, tmp_path)
    registry = create_default_registry(tmp_path, client=client, team_manager=team)
    messages = [{"role": "user", "content": "Fix two bugs with the team."}]

    result = agent_loop(messages, tool_handlers=registry, client=client)

    assert result == "all done"
    assert team.members["alice"].result == "alice done"
    assert {m["name"] for m in team.status()} == {"alice", "bob"}
    assert all(member.status == "done" for member in team.members.values())
    lead_results = [m for m in team.inbox("lead") if m.kind == "result"]
    assert sorted(m.content for m in lead_results) == ["alice done", "bob done"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_isolated_members_edit_separate_worktrees(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    client = MockLLMClient()
    client.add_tool_use_response(
        "write", {"path": "fix.txt", "content": "alice edit"}
    )
    client.add_tool_use_response("write", {"path": "fix.txt", "content": "bob edit"})
    client.add_text_response("alice finished")
    client.add_text_response("bob finished")
    team = TeamManager(client, repo)
    alice = team.spawn("alice", "fixer", task="fix", isolate=True)
    bob = team.spawn("bob", "fixer", task="fix", isolate=True)

    summary = team.wait()

    assert summary["rounds"] == 2
    assert sorted(summary["done"]) == ["alice", "bob"]
    assert alice.worktree is not None and bob.worktree is not None
    assert (alice.worktree / "fix.txt").read_text(encoding="utf-8") == "alice edit"
    assert (bob.worktree / "fix.txt").read_text(encoding="utf-8") == "bob edit"
    assert not (repo / "fix.txt").exists()
    team.shutdown()
    assert not alice.worktree.exists()
    assert not bob.worktree.exists()

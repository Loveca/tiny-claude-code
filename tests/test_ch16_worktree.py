"""Tests for ch16: git worktree isolation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from tiny_claude_code.worktree import WorktreeError, WorktreeManager


pytestmark = pytest.mark.skipif(
    shutil.which("git") is None, reason="git is not installed"
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


def test_create_returns_worktree_path(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    manager = WorktreeManager(repo)

    path = manager.create("alice")

    assert path.is_dir()
    assert (path / "README.md").is_file()
    assert manager._git("branch", "--list", "tiny/team/alice").stdout.strip()


def test_create_requires_git_repository(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path)

    with pytest.raises(WorktreeError, match="git repository"):
        manager.create("alice")


def test_create_rejects_duplicate_name(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    manager = WorktreeManager(repo)
    manager.create("alice")

    with pytest.raises(WorktreeError, match="already exists"):
        manager.create("alice")


def test_create_rejects_unsafe_name(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    manager = WorktreeManager(repo)

    with pytest.raises(WorktreeError, match="invalid worktree name"):
        manager.create("../escape")


def test_list_reports_only_managed_worktrees(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    manager = WorktreeManager(repo)
    manager.create("alice")

    entries = manager.list()

    assert [entry["name"] for entry in entries] == ["alice"]
    assert entries[0]["branch"] == "tiny/team/alice"

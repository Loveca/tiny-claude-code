"""Git worktree helpers for isolated parallel work."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorktreeError(RuntimeError):
    """Raised when a worktree operation cannot be completed."""


class WorktreeManager:
    """Create git worktrees so agents can edit the same repo in parallel."""

    def __init__(
        self,
        workspace: str | Path,
        root: str | Path | None = None,
        branch_prefix: str = "tiny/team/",
    ) -> None:
        self.workspace = Path(workspace).resolve()
        if root is None:
            root = self.workspace / ".tiny-claude-code" / "worktrees"
        self.root = Path(root).resolve()
        self.branch_prefix = branch_prefix

    def is_repo(self) -> bool:
        if not self.workspace.is_dir():
            return False
        proc = self._git("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def branch_name(self, name: str) -> str:
        return f"{self.branch_prefix}{name}"

    def create(self, name: str) -> Path:
        self._validate_name(name)
        if not self.is_repo():
            raise WorktreeError("isolate requires a git repository")
        path = self.root / name
        if path.exists():
            raise WorktreeError(f"worktree '{name}' already exists at {path}")
        self.root.mkdir(parents=True, exist_ok=True)
        self._git(
            "worktree",
            "add",
            "-b",
            self.branch_name(name),
            str(path),
            "HEAD",
        )
        return path

    def list(self) -> list[dict[str, str]]:
        if not self.is_repo():
            return []
        proc = self._git("worktree", "list", "--porcelain")
        entries: list[dict[str, str]] = []
        current: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if not line.strip():
                if current:
                    entries.append(current)
                    current = {}
                continue
            key, _, value = line.partition(" ")
            if key == "worktree":
                current["path"] = value
            elif key == "branch":
                current["branch"] = value.removeprefix("refs/heads/")
        if current:
            entries.append(current)

        worktrees: list[dict[str, str]] = []
        for entry in entries:
            raw_path = entry.get("path")
            if not raw_path:
                continue
            path = Path(raw_path)
            if not self._is_direct_child(path):
                continue
            worktrees.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "branch": entry.get("branch", ""),
                }
            )
        return worktrees

    def remove(self, name: str, force: bool = False) -> None:
        self._validate_name(name)
        path = self.root / name
        branch = self.branch_name(name)
        found = False
        if path.exists():
            args = ["worktree", "remove"]
            if force:
                args.append("--force")
            args.append(str(path))
            self._git(*args)
            found = True
        else:
            self._git("worktree", "prune", check=False)
        if self._git("branch", "--list", branch).stdout.strip():
            self._git("branch", "-D", branch)
            found = True
        if not found:
            raise WorktreeError(f"worktree '{name}' does not exist")

    def merge(self, name: str, message: str | None = None) -> str:
        self._validate_name(name)
        branch = self.branch_name(name)
        if not self._git("branch", "--list", branch).stdout.strip():
            return f"Error: worktree branch '{branch}' does not exist"
        proc = self._git(
            "merge",
            "--no-ff",
            "-m",
            message or f"Merge {branch}",
            branch,
            check=False,
        )
        if proc.returncode != 0:
            self._git("merge", "--abort", check=False)
            detail = proc.stderr.strip() or proc.stdout.strip()
            return f"Error: merge failed: {detail}"
        return f"Merged {branch} into the main workspace."

    def cleanup(self) -> None:
        for entry in self.list():
            try:
                self.remove(entry["name"], force=True)
            except WorktreeError:
                continue
        self._git("worktree", "prune", check=False)

    def _is_direct_child(self, path: Path) -> bool:
        try:
            return path.resolve().parent == self.root
        except OSError:
            return False

    def _validate_name(self, name: str) -> None:
        if not _NAME_PATTERN.match(name):
            raise WorktreeError(
                f"invalid worktree name '{name}': use letters, digits, '.', '_' or '-'"
            )

    def _git(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        proc = subprocess.run(
            ["git", "-C", str(self.workspace), *args],
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            message = proc.stderr.strip() or proc.stdout.strip()
            raise WorktreeError(message or f"git {' '.join(args)} failed")
        return proc

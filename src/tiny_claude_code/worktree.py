"""Git worktree helpers for isolated parallel work.

ch16: implement create/list/remove/merge/cleanup on top of `git worktree`.
"""
from __future__ import annotations
from pathlib import Path

class WorktreeError(RuntimeError):
    """Raised when a worktree operation cannot be completed."""

class WorktreeManager:
    """Create git worktrees so agents can edit the same repo in parallel."""

    def __init__(self, workspace: str | Path, root: str | Path | None=None, branch_prefix: str='tiny/team/') -> None:
        raise NotImplementedError('TODO: implement __init__')

    def is_repo(self) -> bool:
        raise NotImplementedError('TODO: implement is_repo')

    def branch_name(self, name: str) -> str:
        raise NotImplementedError('TODO: implement branch_name')

    def create(self, name: str) -> Path:
        raise NotImplementedError('TODO: implement create')

    def list(self) -> list[dict[str, str]]:
        raise NotImplementedError('TODO: implement list')

    def remove(self, name: str, force: bool=False) -> None:
        raise NotImplementedError('TODO: implement remove')

    def merge(self, name: str, message: str | None=None) -> str:
        raise NotImplementedError('TODO: implement merge')

    def cleanup(self) -> None:
        raise NotImplementedError('TODO: implement cleanup')

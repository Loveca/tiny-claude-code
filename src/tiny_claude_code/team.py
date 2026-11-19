"""Multi-agent team coordination with mailboxes and isolated worktrees.

ch16: implement TeamManager — spawn members, queue messages, and run
deterministic rounds with `step` / `run_round` / `wait`.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
LEAD = 'lead'
MEMBER_SYSTEM_PROMPT = 'You are {name}, a teammate in a small agent team. Use the available tools to complete your task. Send progress or questions to the lead with TeamSend. When the task is finished, reply with a concise summary.'

class TeamError(RuntimeError):
    """Raised when a team operation cannot be completed."""

@dataclass
class TeamMessage:
    """One queued message between the lead and a member."""
    seq: int
    sender: str
    recipient: str
    content: str
    kind: str='message'

@dataclass
class TeamMember:
    """A named teammate with its own transcript, tools, and workspace."""
    name: str
    role: str
    workspace: Path
    messages: list[dict[str, Any]]=field(default_factory=list)
    status: str='idle'
    result: str=''
    worktree: Path | None=None
    registry: Any=None

    @property
    def system_prompt(self) -> str:
        raise NotImplementedError('TODO: implement system_prompt')

class TeamManager:
    """Coordinate named agents through mailboxes."""
    LEAD = LEAD

    def __init__(self, client: Any, workspace: str | Path, *, max_members: int=4, max_rounds: int=20, tool_factory: Callable[['TeamManager', TeamMember], Any] | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def spawn(self, name: str, role: str, *, task: str='', isolate: bool=False) -> TeamMember:
        raise NotImplementedError('TODO: implement spawn')

    def send(self, sender: str, recipient: str, content: str, kind: str='message') -> None:
        raise NotImplementedError('TODO: implement send')

    def inbox(self, name: str, *, drain: bool=True) -> list[TeamMessage]:
        raise NotImplementedError('TODO: implement inbox')

    def step(self, name: str) -> str:
        raise NotImplementedError('TODO: implement step')

    def run_round(self) -> list[str]:
        raise NotImplementedError('TODO: implement run_round')

    def wait(self, max_rounds: int | None=None) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement wait')

    def status(self) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement status')

    def shutdown(self, name: str | None=None, *, cleanup_worktrees: bool=True) -> None:
        raise NotImplementedError('TODO: implement shutdown')

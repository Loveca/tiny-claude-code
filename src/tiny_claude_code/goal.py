"""Goal loop — budgeted autonomous runs with explicit completion.

ch17: implement GoalManager.run — one model call per turn, a turn budget,
an explicit GoalDone signal, and checkpoint notes that survive compaction.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
GOAL_PROMPT = 'You are starting an autonomous goal run.\nGoal: {objective}\nWork toward it with the available tools, one step at a time. Call GoalCheckpoint to record progress that must survive context compaction. Call GoalDone with a short summary when the goal is complete.'
CONTINUATION_PROMPT = 'Continue working toward the goal. Turns remaining: {remaining}.\n{progress}Call GoalCheckpoint to record progress that must survive compaction, or GoalDone with a summary when the goal is complete.'
CHECKPOINT_WINDOW = 3

class GoalError(RuntimeError):
    """Raised when a goal operation cannot be completed."""

@dataclass
class Goal:
    """One autonomous objective and its progress."""
    objective: str
    max_turns: int=12
    status: str='active'
    turns_used: int=0
    summary: str=''
    reason: str=''
    checkpoints: list[str]=field(default_factory=list)

class GoalManager:
    """Drive a single goal to completion within a turn budget."""

    def __init__(self, client: Any, *, max_turns: int=12, max_idle_turns: int=2, system: str | None=None, hooks: Any=None, error_handler: Any=None, context_manager: Any=None, compact_manager: Any=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def start(self, objective: str, *, max_turns: int | None=None) -> Goal:
        raise NotImplementedError('TODO: implement start')

    def finish(self, summary: str) -> None:
        raise NotImplementedError('TODO: implement finish')

    def checkpoint(self, note: str) -> int:
        raise NotImplementedError('TODO: implement checkpoint')

    def status(self) -> dict[str, Any] | None:
        raise NotImplementedError('TODO: implement status')

    def run(self, messages: list[dict[str, Any]], registry: Any, objective: str | None=None, *, system: str | None=None) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement run')

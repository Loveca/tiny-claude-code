"""Tools that let an agent steer its own goal run.

ch17: implement GoalDone and GoalCheckpoint.
"""
from __future__ import annotations
from typing import Any, TYPE_CHECKING
from tiny_claude_code.tools.base import Tool
if TYPE_CHECKING:
    from tiny_claude_code.goal import GoalManager

class GoalDoneTool(Tool):
    name = 'GoalDone'

    def __init__(self, manager: 'GoalManager') -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, summary: str) -> str:
        raise NotImplementedError('TODO: implement execute')

class GoalCheckpointTool(Tool):
    name = 'GoalCheckpoint'

    def __init__(self, manager: 'GoalManager') -> None:
        raise NotImplementedError('TODO: implement __init__')

    @property
    def schema(self) -> dict[str, Any]:
        raise NotImplementedError('TODO: implement schema')

    def execute(self, note: str) -> str:
        raise NotImplementedError('TODO: implement execute')

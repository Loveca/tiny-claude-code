"""Tools that let an agent steer its own goal run."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tiny_claude_code_ref.tools.base import Tool

if TYPE_CHECKING:
    from tiny_claude_code_ref.goal import GoalManager


class GoalDoneTool(Tool):
    """Mark the active goal complete with a summary."""

    name = "GoalDone"

    def __init__(self, manager: "GoalManager") -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Mark the active goal complete. Call this only when the "
                "objective is achieved; include a short summary of the result."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "What was accomplished.",
                    }
                },
                "required": ["summary"],
            },
        }

    def execute(self, summary: str) -> str:
        self.manager.finish(summary)
        return f"Goal marked complete: {summary.strip()}"


class GoalCheckpointTool(Tool):
    """Append a progress note to the active goal."""

    name = "GoalCheckpoint"

    def __init__(self, manager: "GoalManager") -> None:
        self.manager = manager

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Record a short progress note. The latest notes are repeated "
                "in every continuation prompt, so they survive compaction."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "note": {
                        "type": "string",
                        "description": "Fact, decision, or remaining work.",
                    }
                },
                "required": ["note"],
            },
        }

    def execute(self, note: str) -> str:
        total = self.manager.checkpoint(note)
        return f"Checkpoint recorded ({total} total)."

"""Goal loop — budgeted autonomous runs with explicit completion.

ch17: a goal adds three things to a normal agent turn: a turn budget, an
explicit ``GoalDone`` signal, and a progress log that survives compaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

GOAL_PROMPT = (
    "You are starting an autonomous goal run.\n"
    "Goal: {objective}\n"
    "Work toward it with the available tools, one step at a time. "
    "Call GoalCheckpoint to record progress that must survive context "
    "compaction. Call GoalDone with a short summary when the goal is complete."
)

CONTINUATION_PROMPT = (
    "Continue working toward the goal. Turns remaining: {remaining}.\n"
    "{progress}"
    "Call GoalCheckpoint to record progress that must survive compaction, "
    "or GoalDone with a summary when the goal is complete."
)

CHECKPOINT_WINDOW = 3


class GoalError(RuntimeError):
    """Raised when a goal operation cannot be completed."""


@dataclass
class Goal:
    """One autonomous objective and its progress."""

    objective: str
    max_turns: int = 12
    status: str = "active"
    turns_used: int = 0
    summary: str = ""
    reason: str = ""
    checkpoints: list[str] = field(default_factory=list)


class GoalManager:
    """Drive a single goal to completion within a turn budget.

    Each turn is one model call followed by tool dispatch. A goal ends when the
    model calls ``GoalDone``, the budget runs out, or the model spends
    ``max_idle_turns`` consecutive turns without calling a tool.
    """

    def __init__(
        self,
        client: Any,
        *,
        max_turns: int = 12,
        max_idle_turns: int = 2,
        system: str | None = None,
        hooks: Any = None,
        error_handler: Any = None,
        context_manager: Any = None,
        compact_manager: Any = None,
    ) -> None:
        if max_turns < 1:
            raise GoalError("max_turns must be at least 1")
        if max_idle_turns < 1:
            raise GoalError("max_idle_turns must be at least 1")
        self.client = client
        self.max_turns = max_turns
        self.max_idle_turns = max_idle_turns
        self.system = system
        self.hooks = hooks
        self.error_handler = error_handler
        self.context_manager = context_manager
        self.compact_manager = compact_manager
        self.goal: Goal | None = None

    def start(self, objective: str, *, max_turns: int | None = None) -> Goal:
        """Create a goal, rejecting empty objectives and overlapping runs."""
        objective = objective.strip()
        if not objective:
            raise GoalError("goal objective cannot be empty")
        if self.goal is not None and self.goal.status == "active":
            raise GoalError("a goal is already active")
        limit = self.max_turns if max_turns is None else max_turns
        if limit < 1:
            raise GoalError("max_turns must be at least 1")
        self.goal = Goal(objective=objective, max_turns=limit)
        return self.goal

    def finish(self, summary: str) -> None:
        """Mark the active goal complete with a summary."""
        goal = self._require_active()
        summary = summary.strip()
        if not summary:
            raise GoalError("goal summary cannot be empty")
        goal.status = "done"
        goal.summary = summary

    def checkpoint(self, note: str) -> int:
        """Append a progress note and return how many the goal now has."""
        goal = self._require_active()
        note = note.strip()
        if not note:
            raise GoalError("checkpoint note cannot be empty")
        goal.checkpoints.append(note)
        return len(goal.checkpoints)

    def status(self) -> dict[str, Any] | None:
        if self.goal is None:
            return None
        goal = self.goal
        return {
            "objective": goal.objective,
            "status": goal.status,
            "turns": goal.turns_used,
            "max_turns": goal.max_turns,
            "summary": goal.summary,
            "reason": goal.reason,
            "checkpoints": list(goal.checkpoints),
        }

    def run(
        self,
        messages: list[dict[str, Any]],
        registry: Any,
        objective: str | None = None,
        *,
        system: str | None = None,
    ) -> dict[str, Any]:
        """Run a goal loop, mutating ``messages`` with every turn.

        Pass ``objective`` to start a new goal, or omit it to run the goal
        created by ``start()``. The registry must include the ``GoalDone`` tool,
        otherwise the run could never finish.
        """
        if objective is not None:
            goal = self.start(objective)
        else:
            if self.goal is None:
                raise GoalError("no goal to run: pass an objective or call start()")
            if self.goal.status != "active":
                raise GoalError(f"goal is {self.goal.status}, not active")
            goal = self.goal

        if not _has_goal_done(registry):
            raise GoalError(
                "GoalDone tool is not registered: create the registry with "
                "goal_manager=..."
            )

        schemas = registry.get_schemas()
        prompt_system = self.system if system is None else system
        self._append_user(messages, GOAL_PROMPT.format(objective=goal.objective))
        idle_turns = 0

        while goal.turns_used < goal.max_turns:
            self._compact(messages)
            try:
                response = self._chat(messages, schemas, prompt_system)
            except Exception as exc:
                goal.status = "failed"
                goal.reason = str(exc)
                break

            goal.turns_used += 1
            messages.append({"role": "assistant", "content": response.content})
            tool_results, tool_calls = self._dispatch(registry, response)

            if goal.status == "done":
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})
                break

            idle_turns = 0 if tool_calls else idle_turns + 1
            if idle_turns >= self.max_idle_turns:
                goal.status = "paused"
                goal.reason = f"no tool calls in the last {idle_turns} turns"
                break

            has_more_turns = goal.turns_used < goal.max_turns
            continuation = self._continuation(goal)
            if tool_results:
                if has_more_turns:
                    tool_results.append({"type": "text", "text": continuation})
                messages.append({"role": "user", "content": tool_results})
            elif has_more_turns:
                self._append_user(messages, continuation)
        else:
            goal.status = "paused"
            goal.reason = f"turn budget exhausted after {goal.turns_used} turns"

        self._trigger(
            "Stop", messages=messages, response=goal.summary or goal.reason
        )
        return {
            "status": goal.status,
            "turns": goal.turns_used,
            "summary": goal.summary,
            "reason": goal.reason,
            "checkpoints": list(goal.checkpoints),
        }

    def _dispatch(
        self, registry: Any, response: Any
    ) -> tuple[list[dict[str, Any]], int]:
        results: list[dict[str, Any]] = []
        calls = 0
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            calls += 1
            tool_name = getattr(block, "name", "") or ""
            tool_input = getattr(block, "input", None) or {}
            denial = self._trigger(
                "PreToolUse",
                tool_name=tool_name,
                tool_input=tool_input,
                block=block,
            )
            if denial is not None:
                output = str(denial)
            else:
                output = registry.dispatch(tool_name, tool_input)
                self._trigger(
                    "PostToolUse",
                    tool_name=tool_name,
                    tool_input=tool_input,
                    result=output,
                    block=block,
                )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": getattr(block, "id", None) or "toolu_unknown",
                    "content": str(output),
                }
            )
        return results, calls

    def _chat(
        self,
        messages: list[dict[str, Any]],
        schemas: list[dict[str, Any]],
        system: str | None,
    ) -> Any:
        if self.error_handler is not None:
            return self.error_handler.chat(
                self.client, messages, tools=schemas, system=system
            )
        return self.client.chat(messages, tools=schemas, system=system)

    def _compact(self, messages: list[dict[str, Any]]) -> None:
        if self.context_manager is None:
            return
        self.context_manager.compact(
            messages, client=self.client, compact_manager=self.compact_manager
        )

    def _continuation(self, goal: Goal) -> str:
        remaining = goal.max_turns - goal.turns_used
        recent = goal.checkpoints[-CHECKPOINT_WINDOW:]
        progress = ""
        if recent:
            notes = "\n".join(f"- {note}" for note in recent)
            progress = f"Progress so far:\n{notes}\n"
        return CONTINUATION_PROMPT.format(remaining=remaining, progress=progress)

    def _append_user(self, messages: list[dict[str, Any]], text: str) -> None:
        if messages and messages[-1].get("role") == "user":
            last = messages[-1]["content"]
            if isinstance(last, str):
                messages[-1] = {"role": "user", "content": f"{last}\n\n{text}"}
            else:
                last.append({"type": "text", "text": text})
            return
        messages.append({"role": "user", "content": text})

    def _require_active(self) -> Goal:
        if self.goal is None:
            raise GoalError("no active goal")
        if self.goal.status != "active":
            raise GoalError(f"goal is {self.goal.status}, not active")
        return self.goal

    def _trigger(self, event: str, **kwargs: Any) -> Any:
        if self.hooks is None:
            return None
        return self.hooks.trigger(event, **kwargs)


def _has_goal_done(registry: Any) -> bool:
    try:
        schemas = registry.get_schemas()
    except Exception:
        return False
    return any(schema.get("name") == "GoalDone" for schema in schemas)

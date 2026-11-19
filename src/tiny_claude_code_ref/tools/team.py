"""Tools that expose team mailboxes to agents."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from tiny_claude_code_ref.tools.base import Tool

if TYPE_CHECKING:
    from tiny_claude_code_ref.team import TeamManager, TeamMessage


class TeamSendTool(Tool):
    """Queue a message for another teammate or the lead."""

    name = "TeamSend"

    def __init__(self, team: "TeamManager", sender: str) -> None:
        self.team = team
        self.sender = sender

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Send a message to a teammate or the lead. "
                "Use to=\"lead\" to report progress or ask a question."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient name, 'lead', or 'all'.",
                    },
                    "message": {"type": "string", "description": "Message body."},
                },
                "required": ["to", "message"],
            },
        }

    def execute(self, to: str, message: str) -> str:
        self.team.send(self.sender, to, message)
        return f"Message queued for {to}."


class TeamInboxTool(Tool):
    """Read and drain the current agent's mailbox."""

    name = "TeamInbox"

    def __init__(self, team: "TeamManager", member: str) -> None:
        self.team = team
        self.member = member

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Read new messages from teammates and the lead.",
            "input_schema": {"type": "object", "properties": {}},
        }

    def execute(self) -> str:
        messages = self.team.inbox(self.member)
        if not messages:
            return "No new messages."
        return "\n".join(_format_message(message) for message in messages)


class TeamSpawnTool(Tool):
    """Create a named member and queue its first task."""

    name = "TeamSpawn"

    def __init__(self, team: "TeamManager") -> None:
        self.team = team

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Spawn a named teammate with its own transcript and tools. "
                "Set isolate=true to give it a separate git worktree."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Member name."},
                    "role": {"type": "string", "description": "What the member is for."},
                    "task": {"type": "string", "description": "First task to queue."},
                    "isolate": {
                        "type": "boolean",
                        "description": "Run in a dedicated git worktree.",
                        "default": False,
                    },
                },
                "required": ["name", "role"],
            },
        }

    def execute(
        self, name: str, role: str, task: str = "", isolate: bool = False
    ) -> str:
        member = self.team.spawn(name, role, task=task, isolate=isolate)
        where = f" in worktree {member.worktree}" if member.worktree else ""
        return f"Spawned '{member.name}' ({role}){where}."


class TeamStatusTool(Tool):
    """Report member status and unread mail counts."""

    name = "TeamStatus"

    def __init__(self, team: "TeamManager") -> None:
        self.team = team

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "List team members with status and unread message counts.",
            "input_schema": {"type": "object", "properties": {}},
        }

    def execute(self) -> str:
        rows = self.team.status()
        if not rows:
            return "No team members."
        lines = []
        for row in rows:
            line = f"{row['name']} [{row['status']}] unread={row['unread']}"
            if row["worktree"]:
                line += f" worktree={row['worktree']}"
            if row["result"]:
                line += f" result={row['result']}"
            lines.append(line)
        return "\n".join(lines)


class TeamWaitTool(Tool):
    """Advance members until the team is idle or the round cap is reached."""

    name = "TeamWait"

    def __init__(self, team: "TeamManager") -> None:
        self.team = team

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Run member turns in rounds until everyone is done or the cap "
                "is reached, then report results."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_rounds": {
                        "type": "integer",
                        "description": "Round cap; defaults to the team setting.",
                    }
                },
            },
        }

    def execute(self, max_rounds: int | None = None) -> str:
        summary = self.team.wait(max_rounds=max_rounds)
        lines = [f"rounds={summary['rounds']} done={summary['done']} pending={summary['pending']}"]
        for name, result in summary["results"].items():
            if result:
                lines.append(f"- {name}: {result}")
        return "\n".join(lines)


class TeamShutdownTool(Tool):
    """Mark members done and clean up their worktrees."""

    name = "TeamShutdown"

    def __init__(self, team: "TeamManager") -> None:
        self.team = team

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Shut down one member or the whole team and clean worktrees.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Member to stop; omit to stop everyone.",
                    }
                },
            },
        }

    def execute(self, name: str | None = None) -> str:
        self.team.shutdown(name)
        if name is None:
            return "Shut down all team members."
        return f"Shut down '{name}'."


class WorktreeMergeTool(Tool):
    """Merge a member's worktree branch into the main workspace."""

    name = "WorktreeMerge"

    def __init__(self, team: "TeamManager") -> None:
        self.team = team

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": (
                "Merge a member's worktree branch into the current workspace. "
                "Conflicts are aborted, not resolved."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Member name."},
                    "message": {
                        "type": "string",
                        "description": "Optional merge commit message.",
                    },
                },
                "required": ["name"],
            },
        }

    def execute(self, name: str, message: str | None = None) -> str:
        return self.team.worktrees.merge(name, message)


def _format_message(message: "TeamMessage") -> str:
    return f"[{message.seq}] {message.sender} ({message.kind}): {message.content}"

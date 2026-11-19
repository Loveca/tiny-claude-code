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


def _format_message(message: "TeamMessage") -> str:
    return f"[{message.seq}] {message.sender} ({message.kind}): {message.content}"

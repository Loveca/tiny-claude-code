"""Multi-agent team coordination with mailboxes and isolated worktrees."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tiny_claude_code_ref.worktree import WorktreeError, WorktreeManager

LEAD = "lead"

MEMBER_SYSTEM_PROMPT = (
    "You are {name}, a teammate in a small agent team. "
    "Use the available tools to complete your task. "
    "Send progress or questions to the lead with TeamSend. "
    "When the task is finished, reply with a concise summary."
)

_MEMBER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class TeamError(RuntimeError):
    """Raised when a team operation cannot be completed."""


@dataclass
class TeamMessage:
    """One queued message between the lead and a member."""

    seq: int
    sender: str
    recipient: str
    content: str
    kind: str = "message"


@dataclass
class TeamMember:
    """A named teammate with its own transcript, tools, and workspace."""

    name: str
    role: str
    workspace: Path
    messages: list[dict[str, Any]] = field(default_factory=list)
    status: str = "idle"
    result: str = ""
    worktree: Path | None = None
    registry: Any = None

    @property
    def system_prompt(self) -> str:
        return f"{MEMBER_SYSTEM_PROMPT.format(name=self.name)}\nRole: {self.role}"


class TeamManager:
    """Coordinate named agents through mailboxes.

    Scheduling is deterministic: ``step`` runs one member turn, ``run_round``
    advances every unfinished member once, and ``wait`` repeats rounds up to a
    hard cap. This keeps behavior reproducible with a scripted mock client.
    """

    LEAD = LEAD

    def __init__(
        self,
        client: Any,
        workspace: str | Path,
        *,
        max_members: int = 4,
        max_rounds: int = 20,
        tool_factory: Callable[["TeamManager", TeamMember], Any] | None = None,
    ) -> None:
        self.client = client
        self.workspace = Path(workspace).resolve()
        self.max_members = max_members
        self.max_rounds = max_rounds
        self.members: dict[str, TeamMember] = {}
        self.worktrees = WorktreeManager(self.workspace)
        self._tool_factory = tool_factory
        self._mailboxes: dict[str, list[TeamMessage]] = {LEAD: []}
        self._seq = 0

    def spawn(
        self,
        name: str,
        role: str,
        *,
        task: str = "",
        isolate: bool = False,
    ) -> TeamMember:
        self._validate_member_name(name)
        if len(self.members) >= self.max_members:
            raise TeamError(
                f"team is full: at most {self.max_members} members are allowed"
            )
        workspace = self.workspace
        worktree = None
        if isolate:
            try:
                workspace = self.worktrees.create(name)
            except WorktreeError as exc:
                raise TeamError(str(exc)) from exc
            worktree = workspace
        member = TeamMember(name=name, role=role, workspace=workspace)
        member.worktree = worktree
        member.registry = self._build_registry(member)
        self.members[name] = member
        self._mailboxes[name] = []
        if task:
            self.send(LEAD, name, task, kind="task")
        return member

    def send(
        self,
        sender: str,
        recipient: str,
        content: str,
        kind: str = "message",
    ) -> None:
        if not content.strip():
            raise TeamError("message content cannot be empty")
        self._validate_endpoint(sender)
        if recipient == "all":
            recipients = [name for name in self.members if name != sender]
            if not recipients:
                raise TeamError("no other members to broadcast to")
        else:
            self._validate_endpoint(recipient)
            recipients = [recipient]
        for target in recipients:
            self._seq += 1
            self._mailboxes.setdefault(target, []).append(
                TeamMessage(
                    seq=self._seq,
                    sender=sender,
                    recipient=target,
                    content=content,
                    kind=kind,
                )
            )

    def inbox(self, name: str, *, drain: bool = True) -> list[TeamMessage]:
        self._validate_endpoint(name)
        messages = self._mailboxes.setdefault(name, [])
        if not drain:
            return list(messages)
        self._mailboxes[name] = []
        return messages

    def step(self, name: str) -> str:
        """Run one model turn for one member.

        A turn drains unread mail into the transcript, calls the model once,
        dispatches any requested tools, and updates the member status. A final
        text answer marks the member done and sends it to the lead as a result.
        """
        member = self._get_member(name)
        if member.status in ("done", "error"):
            return ""
        unread = self.inbox(name)
        if unread:
            self._append_user(
                member, "\n".join(_format_incoming(message) for message in unread)
            )
        if not member.messages:
            return ""
        schemas = member.registry.get_schemas() if member.registry is not None else None
        try:
            response = self.client.chat(
                member.messages,
                tools=schemas,
                system=member.system_prompt,
            )
        except Exception as exc:
            member.status = "error"
            member.result = str(exc)
            self.send(name, LEAD, f"error: {exc}", kind="result")
            return member.result

        member.messages.append({"role": "assistant", "content": response.content})
        if getattr(response, "stop_reason", None) != "tool_use":
            text = _extract_text(response.content).strip()
            member.status = "done"
            member.result = text
            self.send(name, LEAD, text or "(no output)", kind="result")
            return text

        results = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_name = getattr(block, "name", "") or ""
            tool_input = getattr(block, "input", None) or {}
            if member.registry is None:
                output = "Error: no tools available"
            else:
                output = member.registry.dispatch(tool_name, tool_input)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": getattr(block, "id", None) or "toolu_unknown",
                    "content": str(output),
                }
            )
        member.messages.append({"role": "user", "content": results})
        member.status = "idle"
        return f"[{name}] ran {len(results)} tool call(s)"

    def run_round(self) -> list[str]:
        """Step every unfinished member once, in spawn order."""
        outcomes = []
        for member in list(self.members.values()):
            if member.status in ("done", "error"):
                continue
            outcomes.append(self.step(member.name))
        return outcomes

    def wait(self, max_rounds: int | None = None) -> dict[str, Any]:
        """Run rounds until every member is done or the round cap is hit."""
        limit = self.max_rounds if max_rounds is None else max_rounds
        rounds = 0
        while rounds < limit:
            pending = [
                member
                for member in self.members.values()
                if member.status not in ("done", "error")
            ]
            if not pending:
                break
            progressed = False
            for member in pending:
                if not member.messages and not self._mailboxes.get(member.name):
                    continue
                self.step(member.name)
                progressed = True
            if not progressed:
                break
            rounds += 1
        return {
            "rounds": rounds,
            "done": [
                member.name
                for member in self.members.values()
                if member.status == "done"
            ],
            "pending": [
                member.name
                for member in self.members.values()
                if member.status not in ("done", "error")
            ],
            "results": {
                member.name: member.result for member in self.members.values()
            },
        }

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": member.name,
                "role": member.role,
                "status": member.status,
                "worktree": str(member.worktree) if member.worktree else "",
                "unread": len(self._mailboxes.get(member.name, [])),
                "result": member.result,
            }
            for member in self.members.values()
        ]

    def shutdown(self, name: str | None = None, *, cleanup_worktrees: bool = True) -> None:
        if name is None:
            for member in self.members.values():
                member.status = "done"
            if cleanup_worktrees:
                self.worktrees.cleanup()
            return
        member = self._get_member(name)
        member.status = "done"
        if cleanup_worktrees and member.worktree is not None:
            try:
                self.worktrees.remove(name, force=True)
            except WorktreeError as exc:
                raise TeamError(str(exc)) from exc
            member.worktree = None

    def _append_user(self, member: TeamMember, text: str) -> None:
        if member.messages and member.messages[-1]["role"] == "user":
            last = member.messages[-1]["content"]
            if isinstance(last, str):
                member.messages[-1] = {
                    "role": "user",
                    "content": f"{last}\n\n{text}",
                }
            else:
                last.append({"type": "text", "text": text})
            return
        member.messages.append({"role": "user", "content": text})

    def _build_registry(self, member: TeamMember) -> Any:
        if self._tool_factory is not None:
            return self._tool_factory(self, member)
        from tiny_claude_code_ref.tools import ToolRegistry
        from tiny_claude_code_ref.tools.file_read import ReadTool
        from tiny_claude_code_ref.tools.file_write import WriteTool
        from tiny_claude_code_ref.tools.search import SearchTool
        from tiny_claude_code_ref.tools.shell import ShellTool

        from tiny_claude_code_ref.tools.team import TeamInboxTool, TeamSendTool

        registry = ToolRegistry()
        registry.register(ShellTool(workspace=member.workspace))
        registry.register(ReadTool(workspace=member.workspace))
        registry.register(WriteTool(workspace=member.workspace))
        registry.register(SearchTool(workspace=member.workspace))
        registry.register(TeamSendTool(self, member.name))
        registry.register(TeamInboxTool(self, member.name))
        return registry

    def _get_member(self, name: str) -> TeamMember:
        member = self.members.get(name)
        if member is None:
            raise TeamError(f"unknown team member '{name}'")
        return member

    def _validate_member_name(self, name: str) -> None:
        if name == LEAD:
            raise TeamError(f"'{LEAD}' is reserved for the lead")
        if not _MEMBER_NAME_PATTERN.match(name):
            raise TeamError(
                f"invalid member name '{name}': use letters, digits, '.', '_' or '-'"
            )
        if name in self.members:
            raise TeamError(f"member '{name}' already exists")

    def _validate_endpoint(self, name: str) -> None:
        if name == LEAD:
            return
        self._get_member(name)


def _extract_text(content: list[Any]) -> str:
    parts = []
    for block in content:
        text = getattr(block, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)


def _format_incoming(message: TeamMessage) -> str:
    return f"{message.sender} ({message.kind}): {message.content}"

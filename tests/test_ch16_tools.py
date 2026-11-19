"""Tests for ch16: team tool surface."""

from __future__ import annotations

from pathlib import Path

from conftest import MockLLMClient
from tiny_claude_code.team import TeamManager
from tiny_claude_code.tools.team import TeamInboxTool, TeamSendTool


def test_member_registry_has_mailbox_tools_but_no_team_spawn(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")

    schemas = team.members["alice"].registry.get_schemas()
    names = {schema["name"] for schema in schemas}

    assert {"TeamSend", "TeamInbox"} <= names
    assert "TeamSpawn" not in names
    assert "SubAgent" not in names


def test_send_tool_queues_message(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role")
    tool = TeamSendTool(team, "alice")

    result = tool.execute("lead", "finished the fix")

    assert "queued" in result
    assert team.inbox("lead")[0].content == "finished the fix"


def test_inbox_tool_formats_and_drains(tmp_path: Path) -> None:
    team = TeamManager(MockLLMClient(), tmp_path)
    team.spawn("alice", "role", task="fix the cart")
    tool = TeamInboxTool(team, "alice")

    output = tool.execute()

    assert "lead (task): fix the cart" in output
    assert tool.execute() == "No new messages."

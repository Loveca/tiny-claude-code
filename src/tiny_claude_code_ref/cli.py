"""CLI entry point — interactive REPL.

ch01: Implement main() — read user input, call agent_loop, print response.
ch09: you will add /compact command handling.
ch10: you will add --resume flag and /memory command.
ch17: you will add /goal for budgeted autonomous runs.
ch18: you will add --mcp to load tools from an MCP server.
"""

from __future__ import annotations

import argparse
import atexit
import shlex
import sys
from pathlib import Path
from typing import Any

from tiny_claude_code_ref.agent import agent_loop
from tiny_claude_code_ref.background import BackgroundManager
from tiny_claude_code_ref.compact import CompactManager
from tiny_claude_code_ref.context import ContextManager
from tiny_claude_code_ref.cron import CronScheduler
from tiny_claude_code_ref.error_recovery import ErrorHandler
from tiny_claude_code_ref.goal import GoalManager
from tiny_claude_code_ref.hooks import HookSystem, StopLogHook, ToolLogHook
from tiny_claude_code_ref.llm import create_client
from tiny_claude_code_ref.mcp import MCPClient, MCPError
from tiny_claude_code_ref.memory import MemoryManager
from tiny_claude_code_ref.permissions import PermissionManager
from tiny_claude_code_ref.session import SessionManager
from tiny_claude_code_ref.skills import SkillLoader
from tiny_claude_code_ref.tools import create_default_registry
from tiny_claude_code_ref.workflow import (
    WorkflowError,
    WorkflowManager,
    format_run_result,
)


SYSTEM_PROMPT = (
    "You are a coding agent working in {workspace}. "
    "Use the available tools to inspect files, edit code, and run commands. "
    "Act to solve the user's task, then summarize what changed."
)


def build_system_prompt(
    workspace: Path, memory_context: str = "", skill_context: str = ""
) -> str:
    system = SYSTEM_PROMPT.format(workspace=workspace)
    if memory_context:
        system += "\n\n" + memory_context
    if skill_context:
        system += "\n\n" + skill_context
    return system


def _force_utf8_console() -> None:
    """Make stdout/stderr UTF-8 so em dashes and CJK paths survive.

    Windows consoles default to a legacy codepage (GBK here), which turns
    "—" into "??" and mangles non-ASCII workspace paths.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main(argv: list[str] | None = None) -> None:
    """REPL main loop.

    Flow:
    1. Initialize LLMClient
    2. while True: read user input
    3. If input is /exit or /quit -> exit
    4. Append user input to messages
    5. Call agent_loop(messages, ...)
    6. Print agent response
    7. Continue loop

    ch01: implement basic REPL (read input -> call agent_loop -> print response)
    ch02: initialize tool_handlers and pass to agent_loop
    ch09: add /compact command
    ch10: add --resume and /memory commands
    """
    _force_utf8_console()
    parser = argparse.ArgumentParser(description="tiny-claude-code — AI coding agent")
    parser.add_argument(
        "--workspace",
        "-w",
        type=Path,
        default=Path.cwd(),
        help="Target workspace directory (default: current directory)",
    )
    parser.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        help="Resume the latest session or the given session id",
    )
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="Load a named skill from .tiny-claude-code/skills",
    )
    parser.add_argument(
        "--plugins",
        default=".tiny-claude-code/plugins",
        help="Directory containing Python tool plugins",
    )
    parser.add_argument(
        "--workflows",
        default=".tiny-claude-code/workflows",
        help="Directory containing JSON workflow definitions",
    )
    parser.add_argument(
        "--mcp",
        help='MCP server command, e.g. --mcp "python examples/mcp/echo_server.py"',
    )
    parser.add_argument(
        "task",
        nargs="*",
        help="Optional task to execute directly (non-interactive mode)",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    client = create_client()
    sessions = SessionManager(workspace)
    memory = MemoryManager(workspace)
    skills = SkillLoader(workspace)
    background_manager = BackgroundManager(workspace)
    cron_scheduler = CronScheduler(workspace)
    if args.resume:
        session_id = (
            sessions.latest_session_id() if args.resume == "latest" else args.resume
        )
        messages = sessions.load(session_id) if session_id else []
        session_id = session_id or sessions.new_session_id()
    else:
        session_id = sessions.new_session_id()
        messages: list[dict] = []

    hooks = HookSystem()
    permissions = PermissionManager(workspace=workspace)
    tool_log = ToolLogHook()
    stop_log = StopLogHook()
    error_handler = ErrorHandler()
    context_manager = ContextManager()
    compact_manager = CompactManager(archive_dir=sessions.session_dir / "archives")
    goal_manager = GoalManager(
        client,
        hooks=hooks,
        error_handler=error_handler,
        context_manager=context_manager,
        compact_manager=compact_manager,
    )
    hooks.register("PreToolUse", permissions.as_hook, priority=100)
    hooks.register("PostToolUse", tool_log.post_tool_use)
    hooks.register("Stop", stop_log.stop)

    mcp_client = _start_mcp_client(args.mcp)
    system = build_system_prompt(
        workspace,
        memory.build_system_context(),
        skills.build_system_context(args.skill),
    )
    workflow_manager = WorkflowManager(
        client,
        workspace=workspace,
        system=system,
        hooks=hooks,
        error_handler=error_handler,
    )
    workflow_names = workflow_manager.load_definitions(workspace / args.workflows)

    tools = create_default_registry(
        workspace,
        client=client,
        background_manager=background_manager,
        cron_scheduler=cron_scheduler,
        plugin_dir=workspace / args.plugins,
        goal_manager=goal_manager,
        mcp_client=mcp_client,
        workflow_manager=workflow_manager,
    )

    if args.task:
        messages.append({"role": "user", "content": " ".join(args.task)})
        response = agent_loop(
            messages,
            tool_handlers=tools,
            client=client,
            system=system,
            hooks=hooks,
            error_handler=error_handler,
            context_manager=context_manager,
            compact_manager=compact_manager,
        )
        sessions.save(session_id, messages, {"workspace": str(workspace)})
        print(response)
        return

    print(f"tiny-claude-code — working in {workspace}")
    if mcp_client is not None:
        server = mcp_client.server_info.get("name", "unknown")
        print(f"MCP server: {server}")
    if workflow_names:
        print(f"Workflows: {', '.join(workflow_names)}")
    print('Type /exit to quit, or pass a task directly: tiny-claude-code "your task"')
    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            sessions.save(session_id, messages, {"workspace": str(workspace)})
            print("Bye!")
            break
        if user_input == "/compact":
            messages[:] = compact_manager.compact(messages, client)
            sessions.save(session_id, messages, {"workspace": str(workspace)})
            print(f"Compacted conversation to {len(messages)} messages.")
            if compact_manager.last_archive_path is not None:
                print(f"Pre-compact transcript archived to {compact_manager.last_archive_path}")
            continue
        if user_input.startswith("/memory"):
            print(handle_memory_command(memory, user_input))
            system = build_system_prompt(
                workspace,
                memory.build_system_context(),
                skills.build_system_context(args.skill),
            )
            continue
        if user_input.startswith("/skill"):
            print(handle_skill_command(skills, user_input))
            continue
        if user_input.startswith("/goal"):
            print(
                handle_goal_command(
                    goal_manager, tools, messages, system, user_input
                )
            )
            sessions.save(session_id, messages, {"workspace": str(workspace)})
            continue
        if user_input.startswith("/workflow"):
            print(handle_workflow_command(workflow_manager, tools, user_input))
            continue

        prompt_override = hooks.trigger(
            "UserPromptSubmit", prompt=user_input, messages=messages
        )
        if prompt_override is not None:
            user_input = str(prompt_override)

        notifications = background_manager.completed_notifications()
        if notifications:
            messages.append({"role": "user", "content": "\n\n".join(notifications)})

        messages.append({"role": "user", "content": user_input})
        response = agent_loop(
            messages,
            tool_handlers=tools,
            client=client,
            system=system,
            hooks=hooks,
            error_handler=error_handler,
            context_manager=context_manager,
            compact_manager=compact_manager,
        )
        sessions.save(session_id, messages, {"workspace": str(workspace)})
        print(f"\n{response}\n")


def handle_memory_command(memory: MemoryManager, command: str) -> str:
    parts = shlex.split(command)
    if len(parts) >= 4 and parts[1] == "add":
        title = parts[2]
        content = " ".join(parts[3:])
        path = memory.save("user", title, content)
        return f"Saved memory: {path.name}"
    if len(parts) >= 2 and parts[1] == "list":
        index = memory.build_index()
        return index.read_text(encoding="utf-8")
    return 'Usage: /memory add "title" "content" or /memory list'


def handle_skill_command(skills: SkillLoader, command: str) -> str:
    parts = shlex.split(command)
    if len(parts) >= 2 and parts[1] == "list":
        found = skills.list_skills()
        if not found:
            return "No skills found."
        return "\n".join(f"- {skill.name}: {skill.summary}" for skill in found)
    if len(parts) >= 3 and parts[1] == "show":
        return skills.load(parts[2])
    return 'Usage: /skill list or /skill show "name"'


def _start_mcp_client(spec: str | None) -> MCPClient | None:
    if not spec:
        return None
    parts = shlex.split(spec)
    if not parts:
        print("MCP: empty server command", file=sys.stderr)
        return None
    client = MCPClient(command=parts[0], args=parts[1:])
    try:
        client.start()
    except MCPError as exc:
        print(f"MCP server failed to start: {exc}", file=sys.stderr)
        return None
    atexit.register(client.close)
    return client


def handle_goal_command(
    goal_manager: GoalManager,
    tools: Any,
    messages: list[dict],
    system: str,
    command: str,
) -> str:
    objective = command[len("/goal"):].strip()
    if not objective:
        status = goal_manager.status()
        if status is None:
            return "No goal has been started yet."
        return (
            f"Goal: {status['objective']}\n"
            f"Status: {status['status']} "
            f"({status['turns']}/{status['max_turns']} turns)\n"
            f"Summary: {status['summary'] or '-'}\n"
            f"Reason: {status['reason'] or '-'}"
        )
    result = goal_manager.run(messages, tools, objective, system=system)
    lines = [f"Goal {result['status']} after {result['turns']} turn(s)."]
    if result["summary"]:
        lines.append(f"Summary: {result['summary']}")
    if result["reason"]:
        lines.append(f"Reason: {result['reason']}")
    return "\n".join(lines)


def handle_workflow_command(
    workflow_manager: WorkflowManager, tools: Any, command: str
) -> str:
    parts = shlex.split(command)
    try:
        if len(parts) >= 2 and parts[1] == "status":
            result = workflow_manager.status(parts[2] if len(parts) >= 3 else None)
            return format_run_result(result) if result else "No workflow runs yet."
        if len(parts) >= 4 and parts[1] == "approve":
            decision = parts[3].lower()
            if decision not in ("approve", "deny"):
                return "Decision must be 'approve' or 'deny'."
            result = workflow_manager.approve(
                parts[2],
                tools,
                approved=decision == "approve",
                comment=" ".join(parts[4:]),
            )
            return format_run_result(result)
        if len(parts) >= 3 and parts[1] == "resume":
            return format_run_result(workflow_manager.resume(parts[2], tools))
        if len(parts) >= 2:
            return format_run_result(workflow_manager.run(parts[1], tools))
    except WorkflowError as exc:
        return f"Error: {exc}"
    return (
        "Usage: /workflow <name> | /workflow status [run_id] | "
        "/workflow approve <run_id> approve|deny [comment] | /workflow resume <run_id>"
    )


if __name__ == "__main__":
    main()


"""CLI entry point — interactive REPL.

ch01: Implement main() — read user input, call agent_loop, print response.
ch09: you will add /compact command handling.
ch10: you will add --resume flag and /memory command.
"""

from __future__ import annotations

import sys
import argparse
import shlex
from pathlib import Path

from tiny_claude_code_ref.agent import agent_loop
from tiny_claude_code_ref.background import BackgroundManager
from tiny_claude_code_ref.compact import CompactManager
from tiny_claude_code_ref.context import ContextManager
from tiny_claude_code_ref.cron import CronScheduler
from tiny_claude_code_ref.error_recovery import ErrorHandler
from tiny_claude_code_ref.hooks import HookSystem, StopLogHook, ToolLogHook
from tiny_claude_code_ref.llm import LLMClient
from tiny_claude_code_ref.memory import MemoryManager
from tiny_claude_code_ref.permissions import PermissionManager
from tiny_claude_code_ref.session import SessionManager
from tiny_claude_code_ref.skills import SkillLoader
from tiny_claude_code_ref.tools import create_default_registry


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
        "--workspace", "-w",
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
        "task",
        nargs="*",
        help="Optional task to execute directly (non-interactive mode)",
    )
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).resolve()
    client = LLMClient()
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

    tools = create_default_registry(
        workspace,
        client=client,
        background_manager=background_manager,
        cron_scheduler=cron_scheduler,
        plugin_dir=workspace / args.plugins,
    )
    system = build_system_prompt(
        workspace,
        memory.build_system_context(),
        skills.build_system_context(args.skill),
    )
    hooks = HookSystem()
    permissions = PermissionManager(workspace=workspace)
    tool_log = ToolLogHook()
    stop_log = StopLogHook()
    error_handler = ErrorHandler()
    context_manager = ContextManager()
    compact_manager = CompactManager()
    hooks.register("PreToolUse", permissions.as_hook, priority=100)
    hooks.register("PostToolUse", tool_log.post_tool_use)
    hooks.register("Stop", stop_log.stop)

    if args.task:
        # Non-interactive mode: execute one-shot task and exit
        task_str = " ".join(args.task)
        messages.append({"role": "user", "content": task_str})
        response = agent_loop(
            messages,
            tool_handlers=tool_handlers,
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
    print("Type /exit to quit, or pass a task directly: tiny-claude \"your task\"")
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


if __name__ == "__main__":
    main()


"""CLI entry point — interactive REPL.

ch01: Implement main() — read user input, call agent_loop, print response.
ch09: you will add /compact command handling.
ch10: you will add --resume flag and /memory command.
"""
from __future__ import annotations
import argparse
import logging
import shlex
from pathlib import Path
from tiny_claude_code.agent import agent_loop
from tiny_claude_code.background import BackgroundManager
from tiny_claude_code.compact import CompactManager
from tiny_claude_code.context import ContextManager
from tiny_claude_code.cron import CronScheduler
from tiny_claude_code.error_recovery import ErrorHandler
from tiny_claude_code.hooks import HookSystem, ProgressHook, StopLogHook, ToolLogHook
from tiny_claude_code.llm import LLMClient
from tiny_claude_code.memory import MemoryManager
from tiny_claude_code.permissions import PermissionManager
from tiny_claude_code.session import SessionManager
from tiny_claude_code.skills import SkillLoader
from tiny_claude_code.tools import create_default_registry
SYSTEM_PROMPT = "You are a coding agent working in {workspace}. Use the available tools to inspect files, edit code, and run commands. Act to solve the user's task, then summarize what changed."

def build_system_prompt(workspace: Path, memory_context: str='', skill_context: str='') -> str:
    system = SYSTEM_PROMPT.format(workspace=workspace)
    if memory_context:
        system += "\n\n" + memory_context
    if skill_context:
        system += "\n\n" + skill_context
    return system

def main(argv: list[str] | None=None) -> None:
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
    ch06: create ProgressHook and register it on PreToolUse / PostToolUse
    ch09: add /compact command
    ch10: add --resume and /memory commands
    """
    parser = argparse.ArgumentParser(description="tiny-claude-code")
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
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging (shows subagent and tool dispatch details)",
    )
    args = parser.parse_args(argv)

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="  \033[2m[%(name)s]\033[0m %(message)s")

    workspace = Path.cwd()
    client = LLMClient()
    sessions = SessionManager(workspace)
    memory = MemoryManager(workspace)
    skills = SkillLoader(workspace)
    if args.resume:
        session_id = (
            sessions.latest_session_id() if args.resume == "latest" else args.resume
        )
        messages = sessions.load(session_id) if session_id else []
        session_id = session_id or sessions.new_session_id()
    else:
        session_id = sessions.new_session_id()
        messages: list[dict] = []

    tool_handlers = create_default_registry(
        workspace, client=client, plugin_dir=workspace / args.plugins
    )
    system = build_system_prompt(
        workspace,
        memory.build_system_context(),
        skills.build_system_context(args.skill),
    )
    permissions = PermissionManager(workspace=workspace)
    hooks = HookSystem()
    tool_log = ToolLogHook()
    stop_log = StopLogHook()
    error_handler = ErrorHandler()
    context_manager = ContextManager()
    compact_manager = CompactManager()
    progress = ProgressHook()
    hooks.register("PreToolUse", permissions.as_hook, priority=100)
    hooks.register("PreToolUse", progress.pre_tool_use)
    hooks.register("PostToolUse", progress.post_tool_use)
    hooks.register("PostToolUse", tool_log.post_tool_use)
    hooks.register("Stop", stop_log.stop)

    print("tiny-claude-code (type /exit to quit)")
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

        messages.append({"role": "user", "content": user_input})
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
if __name__ == '__main__':
    main()

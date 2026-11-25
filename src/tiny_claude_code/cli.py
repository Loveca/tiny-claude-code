"""CLI entry point — interactive REPL.

ch01: Implement main() — read user input, call agent_loop, print response.
ch09: you will add /compact command handling.
ch10: you will add --resume flag and /memory command.
ch21: you will add --stream, which prints assistant text as it arrives.
"""
from __future__ import annotations
import argparse
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
    raise NotImplementedError('TODO: implement build_system_prompt')

def main(argv: list[str] | None=None) -> None:
    """REPL main loop.

    Flow:
    1. Initialize LLMClient
    2. If a task was passed as an argument, run it once, save the session, and exit
    3. while True: read user input
    4. If input is /exit or /quit -> exit
    5. Append user input to messages
    6. Call agent_loop(messages, ...)
    7. Print agent response
    8. Continue loop

    ch01: implement basic REPL (read input -> call agent_loop -> print response)
    ch02: initialize tool_handlers and pass to agent_loop
    ch06: create ProgressHook and register it on PreToolUse / PostToolUse
    ch09: add /compact command
    ch10: add --resume and /memory commands
    ch21: add --stream — pass a callback as agent_loop's on_text that prints
          each text piece immediately, and skip the final print when the
          answer was already shown
    """
    raise NotImplementedError('TODO: implement main')

def handle_memory_command(memory: MemoryManager, command: str) -> str:
    raise NotImplementedError('TODO: implement handle_memory_command')

def handle_skill_command(skills: SkillLoader, command: str) -> str:
    raise NotImplementedError('TODO: implement handle_skill_command')
if __name__ == '__main__':
    main()

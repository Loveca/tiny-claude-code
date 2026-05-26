"""CLI entry point — interactive REPL.

ch01: Implement main() — read user input, call agent_loop, print response.
ch09: you will add /compact command handling.
ch10: you will add --resume flag and /memory command.
"""

from __future__ import annotations

from tiny_claude_code.agent import agent_loop
from tiny_claude_code.llm import LLMClient


SYSTEM_PROMPT = "You are a helpful coding assistant."


def main() -> None:
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
    client = LLMClient()
    messages: list[dict] = []

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
            print("Bye!")
            break

        messages.append({"role": "user", "content": user_input})
        response = agent_loop(messages, tool_handlers=None, client=client)
        print(f"\n{response}\n")


if __name__ == "__main__":
    main()

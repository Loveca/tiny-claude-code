"""CLI entry point — interactive REPL."""

from __future__ import annotations

from tiny_claude_code_ref.llm import LLMClient
from tiny_claude_code_ref.agent import agent_loop


SYSTEM_PROMPT = "You are a helpful coding assistant."


def main() -> None:
    client = LLMClient()
    messages: list[dict] = [{"role": "user", "content": []}]

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

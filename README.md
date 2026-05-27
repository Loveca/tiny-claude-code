# tiny-claude-code

Build your own coding agent, step by step.

`tiny-claude-code` is a hands-on tutorial project for learning how a coding agent works from the inside: an LLM, a loop, tools, file access, safety, context, memory, tasks, and collaboration.

Current release: Part 5. The repository implements the full ch01-ch15 curriculum plus the checkpoint exercises, with the roadmap laid out in [docs/ROADMAP.md](./docs/ROADMAP.md).

## What You Get

- A minimal CLI coding agent
- Shell, file read/write, search, and tool registry support
- Mock-LLM chapter tests that run without an API key
- A real LLM REPL for hands-on verification
- A checkpoint project that lets the agent fix a real bug
- Permission hooks and basic LLM error recovery
- Context compaction, session resume, and project memory
- Todo tracking, subagents, background tasks, and cron scheduling
- Real challenge projects, skill loading, and Python tool plugins
- Chapter-by-chapter教材 under [chapters/src/](./chapters/src)

## Current Release

What is implemented now:

- ch01: Agent loop and CLI
- ch02: Shell tool
- ch03: File tools
- ch04: Tool registry
- Checkpoint 1: first bug-fix exercise
- ch05: Permission system
- ch06: Hook system
- ch07: Error recovery
- ch08: Context budget
- ch09: `/compact`
- ch10: Session and memory
- ch11: Todo and task system
- ch12: Subagent delegation
- ch13: Background tasks and cron
- ch14: Real project challenge
- ch15: Skills and plugin extension

The roadmap is now implemented end to end. Future work can focus on polishing UX, expanding examples, and hardening real-world safety.

## Quick Start

```bash
git clone git@github.com:Loveca/tiny-claude-code.git
cd tiny-claude-code
pip install -r requirements.txt
cp .env.example .env
```

Set `ANTHROPIC_API_KEY` in `.env`, then choose a model in `MODEL_ID` if needed.

## Run It

### Chapter tests

```bash
python scripts/dev.py test --ch 01
python scripts/dev.py test --ch 02
python scripts/dev.py test --ch 03
python scripts/dev.py test --ch 04
python scripts/dev.py test --ch 05
python scripts/dev.py test --ch 06
python scripts/dev.py test --ch 07
python scripts/dev.py test --ch 08
python scripts/dev.py test --ch 09
python scripts/dev.py test --ch 10
python scripts/dev.py test --ch 11
python scripts/dev.py test --ch 12
python scripts/dev.py test --ch 13
python scripts/dev.py test --ch 14
python scripts/dev.py test --ch 15
python scripts/dev.py test --all
```

### Real agent

```bash
python scripts/dev.py run
```

Resume the latest session:

```bash
python scripts/dev.py run -- --resume
```

Inside the REPL:

```text
/compact
/memory add "Testing" "Run tests with pytest -q"
/memory list
/skill list
```

### Reference implementation

```bash
python scripts/dev.py run --ref
```

### Check remaining TODOs

```bash
python scripts/dev.py check
```

## Learning Path

| Part | Chapters | What you build |
|------|----------|----------------|
| Part 1 | ch01-04 | Agent loop, shell, file tools, registry |
| Checkpoint 1 |  | Fix your first bug with the agent |
| Part 2 | ch05-07 | Permission, hooks, error recovery |
| Part 3 | ch08-10 | Context budget, `/compact`, session and memory |
| Checkpoint 2 |  | Long conversation and session resume |
| Part 4 | ch11-13 | Todo/task, subagent, background and cron |
| Part 5 | ch14-15 | Real project challenge, skills and plugins |

## Workflow

```bash
# Read the chapter
cat chapters/src/ch01-agent-loop.md

# Implement or compare
diff src/tiny_claude_code/agent.py src/tiny_claude_code_ref/agent.py

# Run released tests
python scripts/dev.py test --ch 01

# Run the actual agent
python scripts/dev.py run
```

## Checkpoint 1

Checkpoint 1 is intentionally small and practical:

- Run tests in `examples/simple-bug/`
- Read the failure
- Fix the off-by-one bug
- Re-run the tests until they pass

The checkpoint project is deliberately failing at first and is not part of the default `pytest` run. The released test suite lives under `tests/`.

## Repository Layout

```text
tiny-claude-code/
  src/
    tiny_claude_code/       # student implementation
    tiny_claude_code_ref/   # reference implementation
  chapters/src/             # tutorial chapters
  examples/simple-bug/      # checkpoint exercise
  examples/buggy-python-project/
  examples/tiny-web-app/
  examples/plugins/
  examples/skills/
  tests/                    # released chapter tests
  tests_all/                # full chapter test set
  scripts/dev.py            # test/run/check helper
```

## Notes

- `python -m pytest` runs the released `tests/` suite by default.
- `examples/simple-bug/`, `examples/buggy-python-project/`, and `examples/tiny-web-app/` are meant to fail until the agent fixes them.
- Runtime session and memory files are stored under `.tiny-claude-code/`.
- The full roadmap is implemented, but the project remains intentionally small enough to study.

## License

MIT

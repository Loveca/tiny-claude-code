# tiny-claude-code

Build your own coding agent — a hands-on tutorial project.

From scratch, step by step, implement a working CLI coding agent that can read code, edit files, run commands, and fix bugs.

## Quick Start

```bash
git clone https://github.com/xxx/tiny-claude-code
cd tiny-claude-code
pip install -r requirements.txt
cp .env.example .env  # fill in ANTHROPIC_API_KEY
```

## Learning Path

| Part | Chapters | What you build |
|------|----------|---------------|
| Part 1: Minimum Viable Agent | ch01-04 | Agent loop, shell, file tools, registry |
| Checkpoint 1 | | Fix your first bug with your agent! |
| Part 2: Safety & Robustness | ch05-07 | Permission, hooks, error recovery |
| Part 3: Context & Memory | ch08-10 | Context budget, /compact, session & memory |
| Checkpoint 2 | | Long conversation + session resume |
| Part 4: Tasks & Collaboration | ch11-13 | Todo/task, subagent, background & cron |
| Part 5: Practice & Extensions | ch14-15 | Real project challenge, skills & plugins |

## Workflow

```bash
# Read the chapter tutorial
cat chapters/src/ch01-agent-loop.md

# Implement the TODOs
# edit src/tiny_claude_code/agent.py ...

# Run unit tests (mock LLM, no API key needed)
python scripts/dev.py test --ch 01

# Run your agent (real LLM, needs API key)
python scripts/dev.py run

# Stuck? Compare with reference implementation
diff src/tiny_claude_code/agent.py src/tiny_claude_code_ref/agent.py
```

## Commands

```bash
python scripts/dev.py test --ch 01     # Run tests for chapter 01
python scripts/dev.py test --all       # Run all tests
python scripts/dev.py run              # Run your agent (real LLM)
python scripts/dev.py run --ref        # Run reference implementation
python scripts/dev.py check            # Check which TODOs remain
```
# tiny-claude-code

[English](./README.md) | [中文](./README.zh-CN.md)

用一周时间，从零实现一个 Claude Code 风格的 Coding Agent。

`tiny-claude-code` 是一个面向开发者的 Python AI Coding Agent 教程。它会带你拆开 Claude Code、Codex、Cursor 这类 LLM 编程助手背后的核心机制：agent loop、tool calling、shell 工具、文件读写、权限控制、hooks、上下文压缩、记忆、任务系统、subagent、后台任务和插件扩展。

[文档站](https://loveca.github.io/tiny-claude-code/) | [快速开始](#快速开始) | [课程路线](#课程路线)

![tiny-claude-code terminal demo](./docs/assets/demo.gif)

这个项目不是黑盒 demo，而是同时提供两套代码：

- `src/tiny_claude_code/`：学生版骨架，保留 TODO，适合跟着章节动手实现
- `src/tiny_claude_code_ref/`：完整参考实现，方便对照学习和验证行为

你可以按章节学习，不需要 API Key 就能跑章节测试；实现卡住时，再对照参考实现看设计细节。

## 你会学到什么

如果你正在搜索这些问题，这个项目会很适合：

- 如何从零实现一个 Coding Agent
- Claude Code 风格的工具调用是怎么工作的
- 如何用 Python 实现 LLM agent loop
- `tool_use` 和 `tool_result` 消息怎么流转
- 如何给 AI 编程助手增加 shell、文件工具、记忆、hooks、subagent 和插件
- 如何不花 LLM API 费用也能测试 agent 行为

## 核心预览

Coding Agent 的核心循环其实很小：

```text
messages -> LLM -> response -> tool_use -> tool_result -> messages
```

也就是：模型决定下一步要说话还是调用工具；本地 harness 执行工具，把结果作为观察写回消息历史；模型看到结果后继续判断下一步。

实现前几章之后，agent 就可以通过 shell 观察项目：

```text
> list the files in this repo and tell me what kind of project this is

[tool_use: bash]
command: dir

[tool_result]
exit_code: 0
stdout:
README.md
src
tests
chapters

This is a hands-on Python tutorial project for building a coding agent...
```

学完整套课程后，你会得到一个小而完整的 agent 框架：工具、权限边界、记忆、任务追踪、subagent 和扩展点都会逐步实现出来。

## 为什么做这个项目

很多 Agent 教程停在“调用一次 LLM，然后打印回答”。但真实的 Coding Agent 还需要：

- 持续的 message loop，而不是一次性 prompt
- 给模型看的工具 schema，以及本地真正执行的 handler
- 能返回结构化观察结果的 shell 和文件工具
- 包在危险操作外面的权限与 hook 层
- 上下文预算和压缩
- 会话恢复和项目记忆
- Todo、subagent、后台任务、cron、skills 和 plugins

这个项目的重点不是堆框架，而是把这些能力拆成可测试的小章节，一步一步实现。

## 适合谁

- 想自己实现 AI Coding Assistant 的 Python 开发者
- 想理解 Claude Code、Codex、Cursor 工作原理的工程师
- 正在学习 LLM tool calling / agent framework 的开发者
- 更喜欢小章节、可测试练习，而不是直接读完整大型框架的人

## 快速开始

克隆并安装依赖：

```bash
git clone git@github.com:Loveca/tiny-claude-code.git
cd tiny-claude-code
pip install -r requirements.txt
```

无需 API Key，直接跑章节测试：

```bash
python scripts/dev.py test --ch 01
python scripts/dev.py test --ch 02
python scripts/dev.py test --all
```

运行完整参考实现：

```bash
python scripts/dev.py run --ref
```

运行你自己的学生版实现：

```bash
python scripts/dev.py run
```

学生版使用 `src/tiny_claude_code/`，需要你按章节实现 TODO 后才能完整工作。

## 使用真实 LLM

复制环境变量文件：

```bash
cp .env.example .env
```

Anthropic 配置示例：

```env
ANTHROPIC_API_KEY=your-api-key
MODEL_ID=claude-sonnet-4-6
```

如果服务商兼容 Anthropic Messages API，也可以通过 `ANTHROPIC_BASE_URL` 配置。

DeepSeek 示例：

```env
ANTHROPIC_API_KEY=your-deepseek-key
MODEL_ID=deepseek-v4-flash
# 或：
# MODEL_ID=deepseek-v4-pro

# 兼容服务商示例：MiniMax、GLM、Kimi、DeepSeek
ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
```

## 课程路线

| 阶段 | 章节 | 你会实现什么 |
|------|------|--------------|
| Part 1 | ch01-ch04 | agent loop、shell 工具、文件工具、工具注册表 |
| Checkpoint 1 | ch04 后 | 用 agent 修复一个真实小 bug |
| Part 2 | ch05-ch07 | 权限检查、hooks、LLM 错误恢复 |
| Part 3 | ch08-ch10 | 上下文预算、`/compact`、session、memory |
| Part 4 | ch11-ch13 | Todo 系统、subagent、后台任务、cron |
| Part 5 | ch14-ch15 | 真实项目挑战、skills、plugins |

已发布章节：

- ch01: Agent loop and CLI
- ch02: Shell tool
- ch03: File read/write/search tools
- ch04: Tool registry
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

章节材料在 [chapters/src/](./chapters/src)。

## 常用命令

运行某一章测试：

```bash
python scripts/dev.py test --ch 03
```

检查剩余 TODO：

```bash
python scripts/dev.py check
```

对照参考实现：

```bash
diff src/tiny_claude_code/agent.py src/tiny_claude_code_ref/agent.py
```

后续章节会加入的 REPL 命令：

```text
/compact
/memory add "Testing" "Run tests with pytest -q"
/memory list
/skill list
```

## 仓库结构

```text
tiny-claude-code/
  src/
    tiny_claude_code/       # 学生版骨架，包含 TODO
    tiny_claude_code_ref/   # 完整参考实现
  chapters/src/             # 分章节教程
  examples/simple-bug/      # 第一个 checkpoint 练习
  examples/buggy-python-project/
  examples/tiny-web-app/
  examples/plugins/
  examples/skills/
  tests/                    # 已发布章节测试
  tests_all/                # 完整章节测试集
  scripts/dev.py            # test/run/check 辅助脚本
```

## FAQ

### 这是 Claude Code 克隆吗？

不是生产级克隆。它是一个教学项目，用小而完整的代码重建 Claude Code 风格 Coding Agent 的核心概念：message loop、tool use、tool result、shell、文件工具、权限、记忆、subagent 和插件。

### 必须要 Anthropic API Key 吗？

不需要。章节测试使用 mock LLM，不需要 API Key。只有运行交互式 agent 并接真实模型时才需要。

### 能用 DeepSeek、Kimi、GLM 或其他模型吗？

默认客户端使用 Anthropic SDK 和 Anthropic Messages API 格式。兼容该格式的服务可以通过 `ANTHROPIC_BASE_URL` 使用。只提供 OpenAI-compatible chat completions 的服务，需要在 `llm.py` 里写一个小适配器。

### 为什么不用 LangChain 这类框架？

这个项目的目标是学习底层机制。代码规模刻意保持小，方便你读懂每一部分为什么存在，以及它应该放在 agent harness 的哪个位置。

## License

MIT

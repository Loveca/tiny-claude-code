# ch01: Agent Loop + CLI

> 一个循环，把“会回答问题的模型”变成“能持续工作的 agent”。

## 本章目标

本章要完成 tiny-claude-code 的第一个可运行版本：一个 CLI 程序，能读取用户输入，把对话发给 LLM，再把模型回复打印出来。

更重要的是，你要理解 coding agent 的核心不是一堆复杂框架，而是一个很小的 harness：

```text
messages -> LLM -> response -> maybe tool_use -> tool_result -> messages
```

模型负责判断下一步该说话还是该行动；harness 负责保存状态、调用模型、执行模型请求的动作，并把观察结果喂回模型。后续章节的 shell、文件读写、权限、hooks、上下文压缩、记忆、任务系统，都叠在这个循环之上。

## 先建立心智模型

### Agent 和 Harness 的区别

在这个课程里，“agent”不是一堆 if-else，也不是固定工作流。真正的决策能力来自模型：模型读上下文、推理目标、决定下一步。

你写的代码叫 harness。它给模型提供一个可操作的环境：

- `messages` 是模型看到的历史和当前状态
- `tools` 是模型可以采取的动作
- `tool_result` 是动作执行后的观察结果
- CLI 是用户和 agent 交互的入口

一个 coding agent 可以理解成：

```text
Coding Agent = LLM + Harness

Harness = 对话状态 + 工具接口 + 执行循环 + 安全边界 + 上下文管理
```

本章只做 harness 的第一块：执行循环。

### 为什么需要循环

如果没有 agent loop，模型最多只能给出建议：

```text
用户：帮我看看目录里有什么文件
模型：你可以运行 ls
```

真正的 coding agent 需要多走一步：模型说要运行命令，harness 替它运行，再把输出交还给模型。模型看见输出后，可以继续决定下一步。

这就是循环的意义：

```text
用户提出目标
  |
  v
模型决定下一步
  |
  +-- 回复文本：任务结束
  |
  +-- 调用工具：harness 执行工具
                    |
                    v
              结果写回 messages
                    |
                    v
              再次调用模型
```

本章的 CLI 默认还没有真实工具，但 `agent_loop` 会先实现工具协议的骨架。这样 ch02 加入 shell tool 时，主循环不用重写。

## Messages API 是状态机

LLM API 本身是无状态的。每次调用 `client.messages.create(...)`，它只知道你这次传进去的 `messages`，不知道你上一次说了什么。

所以 harness 必须维护完整对话历史：

```python
messages = [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": [TextBlock(text="你好，有什么可以帮你？")]},
    {"role": "user", "content": "用一句话解释 Agent"},
]
```

这里有两个关键点：

1. `messages` 是 agent 的短期记忆。本章先直接保存在 Python list 里，ch10 会把它保存到磁盘。
2. assistant 的 `content` 在 Anthropic API 中不是简单字符串，而是 content blocks 列表。常见 block 有 `text` 和 `tool_use`。

### Text Block

当模型普通回复时，响应内容里会有 text block：

```text
TextBlock(type="text", text="Agent 是能根据目标持续观察和行动的模型系统。")
```

这时循环可以结束，CLI 打印文本。

### Tool Use Block

当模型决定使用工具时，响应内容里会有 tool use block：

```text
ToolUseBlock(
    type="tool_use",
    id="toolu_01",
    name="bash",
    input={"command": "ls"}
)
```

这不是工具结果，而是模型发出的动作请求。harness 必须：

1. 找到名为 `bash` 的工具 handler
2. 用 `input` 调用它
3. 把执行结果包装成 `tool_result`
4. 作为新的 user message 追加进 `messages`
5. 再次调用模型

### 为什么 tool_result 是 user message

工具结果来自外部世界，不是 assistant 自己说的话。对模型来说，它类似用户补充的新观察：

```python
messages.append({
    "role": "user",
    "content": [{
        "type": "tool_result",
        "tool_use_id": "toolu_01",
        "content": "README.md\nsrc\ntests",
    }],
})
```

`tool_use_id` 很重要。它把某个工具结果和前面那次工具调用对应起来。如果模型一次调用多个工具，API 需要靠这个 id 区分每个结果属于谁。

## stop_reason 是循环控制信号

Anthropic response 上有一个 `stop_reason` 字段。本章只关心两个情况：

| `stop_reason` | 含义 | harness 动作 |
|---|---|---|
| `"tool_use"` | 模型请求使用工具 | 执行工具，把结果写回 messages，继续循环 |
| 其他值 | 模型没有继续请求工具 | 提取文本，返回给 CLI |

所以最小 agent loop 可以被压缩成一句话：

```text
只要模型还在 tool_use，就执行工具并继续；否则返回最终文本。
```

生产级 agent 会遇到更多细节：流式响应、工具并发、错误恢复、token 超限、权限审批、上下文压缩。这个课程后面会逐个加上，但核心循环不会变。

## 本章要实现什么

本章主要修改 3 个文件。

### `src/tiny_claude_code/llm.py`

实现 `LLMClient`，把 Anthropic SDK 包起来。

职责：

- 读取 `ANTHROPIC_API_KEY`
- 读取 `MODEL_ID`
- 可选读取 `ANTHROPIC_BASE_URL`
- 暴露 `chat(messages, tools=None, max_tokens=8000)`

设计原因：后续 ch07 会给 LLM 调用加重试、fallback 和 token 恢复。如果 API 调用散落在各处，后面很难统一改。

### `src/tiny_claude_code/agent.py`

实现 `agent_loop(messages, tool_handlers, client)`。

职责：

- 调用 `client.chat`
- 把 assistant response 追加进 `messages`
- 根据 `stop_reason` 判断是否结束
- 如果有 `tool_use`，执行对应 handler
- 把 `tool_result` 追加进 `messages`
- 最多循环 50 轮，避免失控

这里有一个容易忽略的区别：

- `tool_handlers is None`：表示本章的无工具模式
- `tool_handlers == {}`：表示有工具机制，但没有注册任何工具

第二种情况下，如果模型调用了未知工具，harness 应该把错误作为 `tool_result` 回传给模型，让模型有机会修正，而不是直接退出。

### `src/tiny_claude_code/cli.py`

实现最小 REPL。

职责：

- 初始化 `LLMClient`
- 维护 `messages`
- 读取用户输入
- 支持 `/exit` 和 `/quit`
- 每轮调用 `agent_loop`
- 打印最终文本

CLI 现在很薄，这是有意的。复杂机制应该尽量放在 agent loop、工具、hooks、session manager 等模块里，而不是堆进入口文件。

## 实现路线

### 第一步：LLMClient

你需要把真实 SDK 调用藏在 `LLMClient.chat` 里：

```python
kwargs = {
    "model": self.model,
    "max_tokens": max_tokens,
    "messages": messages,
}
if tools:
    kwargs["tools"] = tools
return self.client.messages.create(**kwargs)
```

这里的 `tools` 是工具 schema 列表，不是工具函数本身。schema 给模型看，handler 给 harness 执行。ch02 会正式展开这个区别。

### 第二步：提取文本

模型 response 的 `content` 是 block 列表。CLI 最终需要字符串，所以可以写一个小函数：

```python
def _extract_text(content):
    parts = []
    for block in content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)
```

这个函数只关心 text block，忽略 tool_use block。

### 第三步：实现 agent loop

循环的骨架是：

```python
for _ in range(MAX_TURNS):
    response = client.chat(messages, tools=tools)
    messages.append({"role": "assistant", "content": response.content})

    if response.stop_reason != "tool_use":
        return _extract_text(response.content)

    # tool_use path
```

工具调用路径先不用写复杂安全逻辑。ch05 会引入权限系统，本章只负责协议正确。

### 第四步：实现 CLI

REPL 不需要一次做太多：

```text
tiny-claude-code (type /exit to quit)
> 用一句话解释什么是 Agent

Agent 是一个能基于目标持续观察、推理并行动的模型系统。
```

你要确认 `messages` 在多轮对话中持续增长。否则模型不会记得前面说过什么。

## 测试讲解

本章测试使用 mock LLM，不需要 API key。测试的重点不是 Anthropic SDK，而是 agent loop 的控制流。

测试覆盖这些行为：

- 模型返回纯文本时，循环立即结束
- 模型先调用工具、再返回文本时，循环会执行工具并继续
- 模型连续调用两次工具时，循环会执行两次
- 模型调用未知工具时，harness 会回传错误结果
- 空消息列表不会导致崩溃
- 循环过程中 `messages` 会持续增长

运行：

```bash
python scripts/dev.py test --ch 01
```

检查 TODO：

```bash
python scripts/dev.py check
```

期望：

```text
6 passed
All TODOs completed!
```

## 验收任务

配置 `.env`：

```bash
cp .env.example .env
```

填入：

```text
ANTHROPIC_API_KEY=...
MODEL_ID=...
```

运行：

```bash
python scripts/dev.py run
```

输入：

```text
用一句话解释什么是 Agent
```

如果 CLI 能返回自然语言回答，本章验收通过。

注意：此时 agent 还不能读文件、写文件或执行命令。你只是完成了“会持续对话的 harness 内核”。从 ch02 开始，我们会给它真正的行动能力。

## 常见错误

### 忘记追加 assistant message

如果不把 response 追加到 `messages`，下一轮模型看不到自己刚刚请求过工具，tool_result 也失去上下文。

### 把 tool_result 放进 assistant message

工具结果应该作为 user message 追加，因为它是外部环境的观察结果，不是模型生成的内容。

### 把空 dict 当成无工具模式

`None` 和 `{}` 不一样：

- `None`：没有工具机制
- `{}`：有工具机制，但没有注册工具

未知工具测试会检查这个区别。

### 直接 `str(response.content)`

这样会把 block 对象的调试表示打印给用户。CLI 应该提取 text block 的 `text` 字段。

## 思考题

1. 为什么说 LLM API 是无状态的，而 agent 需要有状态？
2. 如果模型一次返回多个 `tool_use` block，harness 应该怎样组织多个 `tool_result`？
3. 为什么工具 schema 给模型看，而工具 handler 留在本地执行？
4. 为什么 agent loop 不应该直接关心权限、日志、上下文压缩等所有机制？
5. 如果真实 API 的 `stop_reason` 不可靠，还可以用什么信号判断是否需要继续循环？

## Bonus Tasks

- 给 CLI 增加 `/help` 命令，显示 `/exit`、`/quit` 和当前章节能力。
- 在 `agent_loop` 中捕获工具 handler 异常，把异常文本作为 `tool_result` 返回。
- 给 `_extract_text` 增加单元测试，确认多个 text block 会按顺序拼接。
- 在 CLI 中显示当前对话轮数，观察 `messages` 如何增长。

## 本章小结

你已经实现了 agent harness 的最小内核：

```text
保存 messages
调用 LLM
检查 stop_reason
执行工具请求
写回 tool_result
继续循环
```

后续每一章都会往这个内核上加一个能力，但不要忘记最重要的边界：模型负责决策，harness 负责执行和提供环境。理解这个分工，后面的工具、权限、hooks、上下文和记忆都会变得顺理成章。

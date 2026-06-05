# ch07: Error Recovery

> Agent 不能假设每次 API 调用、每次工具请求、每轮循环都顺利。

## 本章目标

前面几章默认 LLM 调用会成功，工具请求格式正确，循环不会失控。真实系统里这些假设都不可靠。

本章实现 `ErrorHandler`，给 LLM 调用加恢复策略：

- 429 rate limit：指数退避重试
- 529 overload：按 `Retry-After` 等待
- token limit：增大 `max_tokens`
- 主模型失败：切换 fallback model
- agent loop：最多运行 50 轮，避免无限循环
- malformed tool_use：不崩溃，返回错误结果

```text
client.chat
  |
  v
ErrorHandler.chat
  |
  +-- success -> response
  +-- retryable error -> wait and retry
  +-- fallback needed -> switch model
  +-- exhausted -> return readable failure
```

## 先建立心智模型

### 错误恢复不是“吞掉错误”

恢复的目标是让 agent 有机会继续工作，同时保留足够信息。错误不应该悄悄消失，也不应该让整个程序立刻崩溃。

```text
错误发生
  |
  +-- 临时错误：重试
  +-- 可调整错误：改变参数再试
  +-- 无法恢复：返回清楚的失败文本
```

### LLM 调用要集中包装

如果每个地方都直接调用 Anthropic SDK，重试、fallback、token 恢复会散落在项目里。ch01 把 SDK 包成 `LLMClient`，本章再在外层加 `ErrorHandler`：

```text
agent_loop -> ErrorHandler -> LLMClient -> Anthropic SDK
```

这样 agent loop 不需要知道每种 API 错误细节。

## 常见失败类型

### 429: Rate Limit

429 表示请求太频繁。处理方式是指数退避：

```text
第 1 次失败 -> 等 2 秒
第 2 次失败 -> 等 4 秒
第 3 次失败 -> 等 8 秒
```

教学测试会 mock 等待，所以实现时要让等待函数可控，避免测试真的睡很久。

### 529: Overload

529 表示服务过载。如果响应里有 `Retry-After`，优先使用它。

```text
Retry-After: 5 -> 等 5 秒再试
```

### Token Limit

有些错误表示输出 token 不够。可以逐步增大 `max_tokens`：

```text
8000 -> 16000 -> 32000 -> 64000
```

注意这只解决“输出限制”问题，不解决上下文太长。上下文预算会在 ch08 处理。

### Fallback Model

如果主模型持续失败，可以切换备用模型。实现上通常是临时修改 client 的 model，调用后再根据需要保留或恢复。

## 本章要实现什么

主要修改：

- [error_recovery.py](../../src/tiny_claude_code/error_recovery.py)
- [agent.py](../../src/tiny_claude_code/agent.py)

需要实现：

- `ErrorHandler.__init__`
- `ErrorHandler.chat`
- `_backoff`
- `_status_code`
- `_retry_after`
- `_is_token_limit`
- agent loop 的最大轮数保护
- malformed tool_use 的容错

## 实现路线

### 第一步：包装 chat

`ErrorHandler.chat(...)` 接收和 `client.chat(...)` 类似的参数。内部循环尝试调用 client，遇到可恢复错误就调整后重试。

```text
for attempt in range(max_retries):
    try:
        return client.chat(...)
    except error:
        decide retry / fallback / raise
```

### 第二步：识别错误码

不同 SDK 错误对象形状可能不同。可以写 `_status_code(error)`，从 `status_code`、`response.status_code` 等位置尝试读取。

### 第三步：控制等待

把等待逻辑放进 `_backoff`，方便测试替换或 mock。

### 第四步：保护 agent loop

即使 API 每次成功，模型也可能一直请求工具。`max_turns` 是最后防线：

```text
超过 50 轮 -> 返回 "Stopped after max turns"
```

### 第五步：容错 tool_use

如果 block 缺少 id、name 或 input，不要让程序崩溃。返回错误 tool result 或最终错误文本，让模型看到问题。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 07
```

测试覆盖：

- 429 重试后成功
- 429 重试耗尽后失败
- 529 使用 Retry-After
- token limit 会增加 max_tokens
- 主模型失败后使用 fallback model
- agent loop 超过最大轮数会停止
- malformed tool_use 不会崩溃

## 验收任务

真实 API 错误不容易稳定复现。你可以重点手工验证两件事：

1. 正常 agent 行为没有被 ErrorHandler 改坏。
2. 人为设置很小的 `max_turns` 时，循环能停止并返回清楚信息。

## 常见错误

### 所有异常都无限重试

只有临时错误适合重试。未知错误应在有限次数后返回或抛出。

### 重试时丢失原始参数

messages、tools、system 都要继续传递。否则重试调用和原调用不是同一个任务。

### max_turns 只保护 tool_use

保护应该覆盖整个 loop。每次 LLM 调用都算一轮。

### malformed tool_use 直接访问属性

真实 block 可能不是预期形状。读取属性时要有默认值和错误路径。

## 思考题

1. 哪些错误适合重试，哪些不适合？
2. fallback model 会带来哪些行为变化？
3. max_turns 设置太低或太高分别有什么风险？
4. ErrorHandler 应该返回字符串错误，还是继续抛异常？

## Bonus Tasks

- 给重试增加 jitter。
- 记录每次重试的原因和等待时间。
- 支持多个 fallback model。
- 把 max_turns 变成 CLI 参数。

## 本章小结

你给 agent 加上了基础韧性：

```text
API 临时失败 -> 重试
服务过载 -> 等待
输出限制 -> 调参
主模型失败 -> fallback
循环失控 -> 强制停止
```

下一章会处理另一类资源限制：上下文窗口有限，工具输出和历史消息必须被管理。

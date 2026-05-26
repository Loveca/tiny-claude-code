# ch07: Error Recovery

> 错误不是终点，而是恢复策略的入口。

## 本章目标

真实 LLM 调用会失败：限流、服务过载、输出 token 不够、主模型临时不可用。本章实现 `ErrorHandler`，把 LLM 调用包起来，提供最小可用的恢复策略。

当前实现支持：

- 429 rate limit 指数退避重试
- 529 overload 按 `Retry-After` 等待
- token limit 时提升 `max_tokens`
- 主模型失败后切换 fallback model
- agent loop 最大轮次保护
- malformed `tool_use` 不让循环崩溃

## 恢复策略

### 429 Rate Limit

限流通常可以重试。默认退避时间是：

```text
2s -> 4s -> 8s
```

超过最大重试次数后，把异常抛给上层。

### 529 Overload

服务过载时，如果异常带 `Retry-After`，优先使用它。否则使用退避时间。

### Token Limit

如果错误信息显示 token limit，`ErrorHandler` 会尝试提升 `max_tokens`：

```text
8000 -> 16000 -> 32000 -> 64000
```

这不是完整上下文管理。ch08 会处理输入上下文预算；本章只处理输出 token 不够的恢复。

### Fallback Model

如果主模型失败，可以配置备用模型：

```python
ErrorHandler(fallback_models=["backup-model"])
```

handler 会临时设置 `client.model` 再重试。

## Agent Loop 保护

`agent_loop` 已经有最大轮次保护。默认 50 轮，测试里可以用更小的 `max_turns` 验证：

```python
agent_loop(messages, tools, client, max_turns=2)
```

如果模型一直调用工具，循环会返回错误文本，而不是无限运行。

## Malformed Tool Use

模型或 mock 可能返回不完整的 `tool_use` block，例如缺少 `id`。agent loop 会把它转换成错误 `tool_result`，继续让模型恢复。

## 运行测试

```bash
python scripts/dev.py test --ch 07
```

测试覆盖：

- 429 重试后成功
- 429 超过次数后抛错
- 529 使用 `Retry-After`
- token limit 提升 `max_tokens`
- fallback model 生效
- 最大轮次保护
- malformed `tool_use` 不崩溃

## 验收任务

可以用 mock 或低限流 key 手动观察重试行为。真实验收重点是：遇到 API 临时错误时，agent 不应该立刻崩溃。

## 思考题

1. 哪些错误应该重试，哪些应该立即失败？
2. fallback model 会带来哪些行为差异？
3. token limit 恢复和上下文压缩有什么区别？

## 本章小结

Part 2 到这里结束：agent 有了行动边界、扩展点和基本恢复能力。下一阶段会进入上下文和记忆，让 agent 能工作更久。

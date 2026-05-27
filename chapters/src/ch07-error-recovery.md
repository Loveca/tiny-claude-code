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

## 问题：真实 LLM 调用不是稳定函数

到 ch06 为止，agent 的结构已经比较干净，但它默认模型调用总能成功、响应总是格式正确、循环总会结束。真实环境不会这么配合：API 会限流，服务会过载，返回内容可能超出窗口，模型也可能生成缺字段的 `tool_use`。

如果没有恢复策略，任何一次外部抖动都会让 agent 直接失败：

```text
client.messages.create(...)
   |
   +-- 429 rate limit      -> retry later
   +-- 529 overload        -> wait and retry
   +-- context too large   -> compact / reduce
   +-- malformed tool_use  -> return structured error
```

这些不是某个工具的业务错误，而是运行时错误。它们应该由 agent runtime 统一处理。

## 解决方案：按错误类型决定下一步

错误恢复不是简单重试。不同错误需要不同动作：

- 限流说明当前请求频率太高，应等待后重试。
- 过载说明服务端临时不可用，应尊重 `Retry-After` 或使用较短重试。
- token limit 说明上下文超预算，应触发上下文管理或压缩。
- malformed tool_use 说明模型输出不满足协议，应把结构化错误回填给模型。

这让 agent 的行为从“报错退出”变成“把错误变成下一轮可用观察”。

## 为什么错误恢复不能只靠 try/except

真实 LLM 应用里，失败不是异常情况，而是常态：API 可能限流，模型可能过载，响应可能超出 token limit，tool_use 也可能格式不完整。一个 agent 如果只在 happy path 上能跑，进入真实项目后会非常脆弱。

错误恢复应该放在运行时控制层，而不是散落在每个业务工具里。LLMClient 负责识别 API 层错误，Agent loop 负责保护循环边界，工具 handler 负责返回结构化失败结果。这样每一层只处理自己能理解的错误。

本章的策略刻意保持朴素：限流重试、过载重试、token limit 触发压缩、必要时 fallback model。真正产品还会加入指数退避、抖动、最大预算、请求幂等性和可观测性指标。教材里先实现最小策略，是为了让你看清：恢复不是“try/except 包住全部”，而是“按错误类型决定下一步动作”。

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

## 工作原理

`ErrorHandler` 包在 LLM 调用外层，但不吞掉所有异常。它只处理自己认识的错误，并且每类错误都有最大次数：

```python
def chat_with_recovery(call):
    for attempt in range(max_retries):
        try:
            return call()
        except RateLimitError:
            sleep(backoff(attempt))
        except OverloadError as exc:
            sleep(exc.retry_after or backoff(attempt))
        except TokenLimitError:
            raise NeedsCompaction()
    raise
```

agent loop 还需要独立的轮次上限，因为模型可能一直要求工具调用。这个保护和 API 重试不是一回事：重试解决“请求失败”，轮次上限解决“循环不收敛”。

## 相对 ch06 的变化

| 组件 | ch06 | ch07 |
| --- | --- | --- |
| LLM 调用 | 直接调用 client | 通过 ErrorHandler 包装 |
| 循环保护 | 依赖模型停止 | 增加最大轮次 |
| tool_use 协议 | 默认格式正确 | malformed 时回填错误 |
| 失败处理 | 异常冒泡 | 可恢复错误转成控制动作 |

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

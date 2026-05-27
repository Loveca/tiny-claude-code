# ch08: Context Budget

> 上下文窗口不是无限仓库，而是 agent 每一轮都要精打细算的工作台。

## 本章目标

前面的 agent 已经能执行工具、读写文件，也能在错误时重试。但只要对话足够长，工具输出足够大，最终都会撞上模型的上下文上限。本章实现 `ContextManager`，在每次调用 LLM 前主动估算、裁剪和压缩消息历史。

## 问题：工具越有用，上下文越容易爆

coding agent 最占上下文的通常不是用户问题，而是工具结果。读一个 1000 行文件、跑一次失败测试、打印一个长日志，都可能把几千到几万字符塞进消息历史。工具越会工作，越容易把后续请求挤满。

```text
messages
  user goal
  assistant tool_use(read large file)
  user tool_result(large file content)
  assistant tool_use(run tests)
  user tool_result(long failure output)
  ...
```

如果不管理上下文，agent 会在任务中途突然因为 token 超限停下。更糟的是，模型每轮都要重新读取这些历史，成本和延迟都会增加。

## 解决方案：在每次模型调用前做体检

ContextManager 不是等 API 报错后再补救，而是在 `_chat(...)` 前检查消息历史：

```text
before LLM call
   |
   v
estimate_tokens
   |
   v
trim oversized tool_result
   |
   v
snip old middle messages
   |
   v
if still too large -> compact
```

这是一条从便宜到昂贵的策略链。裁剪字符串最便宜，裁掉旧消息次之，调用 LLM 生成摘要最贵，所以 compact 应该放在最后。

## 为什么要先算上下文预算

上下文窗口经常被误解成“模型的记忆”。更准确地说，它是这一次请求能带给模型的工作区。工作区有限、昂贵，并且每轮都要重新发送。agent 真正的长期状态应该保存在本地 transcript、session、memory 或项目文件里，进入上下文的只是当前最值得模型看的那部分。

因此上下文管理的目标不是简单删旧消息，而是在预算内保留决策所需信息。最近的观察通常更重要，因为它们描述当前环境；早期的探索可以被摘要替代；巨大工具输出可以被裁剪或用文件引用替代。

本章先做 token 估算和预算检查，是后续 compact 的地基。没有预算层，压缩就只能在“已经爆了”之后补救；有了预算层，agent 才能在接近限制时主动选择 trim、snip 或 compact。

## 核心概念

上下文预算不是等报错以后再补救，而是在每轮请求前做体检：

1. `estimate_tokens(messages)`：用字符数除以 4 做粗略 token 估算。
2. `trim_tool_output(messages)`：优先截断过长的 `tool_result`，因为工具输出常常最占空间。
3. `snip_old_messages(messages)`：保留开头和结尾，把中间旧消息替换成占位说明。
4. `compact(messages)`：按顺序执行这些策略，并原地更新消息列表。

这个策略的重点是先保留对任务最有用的信息：开头通常有用户目标，结尾通常有当前状态，中间冗长输出可以先牺牲。

## 工作原理

一个最小上下文管理器可以这样组织：

```python
class ContextManager:
    def compact(self, messages, client=None, compact_manager=None):
        if self.estimate_tokens(messages) <= self.max_tokens:
            return messages

        self.trim_tool_output(messages)
        if self.estimate_tokens(messages) <= self.max_tokens:
            return messages

        self.snip_old_messages(messages)
        if self.estimate_tokens(messages) <= self.max_tokens:
            return messages

        if compact_manager is not None:
            return compact_manager.summarize_and_replace(messages, client)

        return messages
```

这里的 `estimate_tokens` 可以先用字符数近似，不需要一开始就接入精确 tokenizer。教材选择近似算法，是为了让重点落在策略顺序和状态变化上，而不是依赖某个模型供应商的 tokenizer。

## 相对 ch07 的变化

| 组件 | ch07 | ch08 |
| --- | --- | --- |
| 失败恢复 | token limit 只是错误类型 | token limit 有主动预算管理 |
| 工具输出 | 原样进入历史 | 过长输出可被裁剪 |
| 历史消息 | 持续增长 | 可保留 head/tail 并 snip 中间 |
| 调用前准备 | 直接请求模型 | 请求前先检查上下文预算 |

## 修改文件

- `src/tiny_claude_code/context.py`
- `src/tiny_claude_code/agent.py`

`agent_loop` 在每次 `_chat(...)` 前调用：

```python
context_manager.compact(messages, client=client, compact_manager=compact_manager)
```

这保证无论 agent 连续调用多少次工具，进入模型之前都会先检查上下文预算。

## 运行测试

```bash
python scripts/dev.py test --ch 08
```

测试覆盖：

- token 估算与字符数成比例
- 长工具输出被截断并带有 `[truncated]` 标记
- 旧消息被裁剪，首尾保留
- compact 后上下文规模下降
- 空消息不崩溃
- agent loop 调用 LLM 前会触发上下文管理

## 验收任务

运行：

```bash
python scripts/dev.py run
```

让 agent 连续读取多个文件并总结。预期行为是对话能持续推进，不会因为工具输出太长直接污染后续所有请求。

## 思考题

1. 为什么工具输出通常比用户消息更适合先截断？
2. 保留 head/tail 的策略有什么缺点？
3. 粗略 token 估算在什么时候会误判？

## 本章小结

ch08 给 agent 加上了上下文预算意识。它还不理解历史内容的重要性，但已经会在窗口耗尽前主动回收空间。

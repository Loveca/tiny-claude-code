# ch08: Context Budget

> 上下文窗口不是无限仓库，而是 agent 每一轮都要精打细算的工作台。

## 本章目标

前面的 agent 已经能执行工具、读写文件，也能在错误时重试。但只要对话足够长，工具输出足够大，最终都会撞上模型的上下文上限。本章实现 `ContextManager`，在每次调用 LLM 前主动估算、裁剪和压缩消息历史。

## 知识串讲：上下文是预算，不是记忆

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

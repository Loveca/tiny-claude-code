# ch09: Compact

> 裁剪是丢弃信息，compact 是把旧信息压缩成可继续工作的摘要。

## 本章目标

ch08 的裁剪可以快速降上下文，但它会丢失细节。本章实现 `CompactManager`，用一次 LLM 调用把长历史总结成短摘要，再保留最近几轮消息，让 agent 能继续接着做事。

## 问题：裁剪能省空间，但不懂任务

ch08 的 `trim` 和 `snip` 是机械策略。它们能减少 token，但不知道哪些信息对继续工作重要。比如一次长调试里，早期某个失败假设、用户指定的约束、已经验证过的命令，都可能不在最近几条消息里，却对后续决策很重要。

简单删历史会带来三个风险：

- agent 重复探索已经排除过的方向。
- agent 忘记用户的明确约束。
- agent 不知道哪些文件已经改过、哪些测试已经跑过。

这就是 compact 要解决的问题：用一次总结把旧历史变成可继续工作的任务状态。

## 解决方案：把长 transcript 折叠成 continuation summary

Compact 不应该写成普通聊天总结。它面向的是下一轮 agent 继续工作，所以摘要要像交接文档：

```text
Goal:
- 用户要完成什么

Current state:
- 已经看过/修改过哪些文件
- 做过哪些决策
- 哪些命令已经验证过

Open items:
- 下一步应该做什么
- 还有哪些风险
```

压缩后，active context 变短；完整 transcript 仍然可以保存在磁盘上，用于审计或恢复。

## Compact 解决什么问题

Compact 的本质是把长 transcript 变成短上下文。这个过程一定有损：原始命令输出、模型犹豫、失败路径和局部细节都会被折叠。好的摘要不是把聊天记录改写得更顺，而是保留后续继续工作的最小充分信息。

对 coding agent 来说，摘要至少应该覆盖五类内容：当前目标、已经做出的关键决策、改过或看过的文件、验证过的命令和结果、下一步计划或未解决风险。缺少这些信息，模型恢复后就容易重复探索、误判状态，或者覆盖用户已有改动。

需要区分 active context 和 durable transcript。压缩可以改变下一轮发给模型的内容，但不应该抹掉本地完整记录。真实系统通常会保留完整 transcript，同时把摘要作为新的上下文入口；这让 agent 既能继续工作，也能在需要时追溯原始事实。

## 工作原理

`CompactManager` 做两件事：先生成摘要，再用摘要和最近消息重建上下文。

```python
summary = compact_manager.summarize(messages, client)
messages[:] = [
    {"role": "user", "content": "[Conversation compacted]\n" + summary},
    *recent_messages,
]
```

保留最近消息是为了避免摘要遗漏刚刚发生的观察。摘要负责承载长期状态，recent tail 负责承载短期细节。

## 相对 ch08 的变化

| 组件 | ch08 | ch09 |
| --- | --- | --- |
| 压缩方式 | 机械 trim/snip | LLM 生成任务摘要 |
| 触发方式 | 调用前自动检查 | 支持 `/compact` 手动触发 |
| 信息保留 | 保留 head/tail | 保留摘要 + 最近消息 |
| 风险 | 可能删掉重要历史 | 可能总结遗漏或幻觉 |

## 核心概念

`CompactManager` 做三件事：

1. `summarize(messages, client)`：把历史格式化成 transcript，请 LLM 总结。
2. `build_compact_messages(summary, recent_messages)`：构造新的消息列表。
3. `compact(messages, client)`：摘要 + 最近消息，形成短上下文。

摘要不应该只是聊天总结。对 coding agent 来说，它必须保留：

- 用户目标
- 已做决策
- 修改过的文件
- 运行过的命令和测试结果
- 未解决问题和下一步

## CLI 命令

本章新增交互命令：

```text
/compact
```

执行后，当前会话消息会被压缩并保存到 session 中。

## 自动触发

`ContextManager.compact(...)` 如果裁剪后仍然超过预算，并且传入了 `compact_manager` 与 `client`，会自动触发 LLM 摘要压缩。

这意味着用户可以手动 `/compact`，agent 也可以在即将超预算时自动 compact。

## 实现路线

### 第一步：定义摘要提示词

摘要提示词要面向“继续工作”，而不是面向“聊天总结”。它应该要求模型保留目标、已改文件、已运行命令、失败信息和下一步。

### 第二步：生成 summary

`CompactManager.summarize(...)` 调用 LLM，把旧 messages 转成短文本。测试里用 mock client 返回固定摘要。

### 第三步：重建 messages

用 summary 加最近几轮消息替代旧历史。不要只保留 summary，否则刚刚发生的工具结果可能被摘要遗漏。

### 第四步：接入 `/compact`

CLI 命令和自动触发都应该复用同一个 compact manager，避免两套压缩行为不一致。

## 测试讲解

本章测试要检查 compact 后的 messages 结构，而不只是检查长度变短。至少要确认摘要存在、最近消息还在、旧的大段内容不再直接进入 active context。

自动触发测试要构造一个明显超预算的消息列表，并验证 compact manager 被调用。这样能证明 ch08 和 ch09 真正接上了。

## 常见错误

### 摘要写得像聊天记录

“用户问了很多问题，助手做了回答”这种摘要对继续编码没用。摘要应该像交接文档。

### 丢掉最近消息

摘要可能漏细节。保留 recent tail 是为了让模型看见刚发生的事实。

### compact 后无法追溯

active context 变短不代表原始 transcript 应该删除。真实系统要保留完整记录，方便审计和恢复。

## 运行测试

```bash
python scripts/dev.py test --ch 09
```

测试覆盖：

- summarize 会调用 LLM 并返回摘要文本
- compact 后消息数量显著减少
- 摘要消息和最近消息同时保留
- context manager 可以自动触发 LLM compact
- agent loop 自动 compact 后仍能继续回答

## 验收任务

在长对话中输入：

```text
/compact
```

预期：CLI 显示压缩后的消息数量，后续对话仍能基于摘要继续工作。

## 思考题

1. 摘要里最不能丢的信息是什么？
2. compact 摘要本身如果写得不准确，会带来什么风险？
3. 什么时候应该手动 compact，而不是等自动触发？

## 本章小结

ch09 让 agent 能把历史变成工作摘要。相比简单裁剪，它保留了更高层的信息结构，是长任务持续推进的基础。

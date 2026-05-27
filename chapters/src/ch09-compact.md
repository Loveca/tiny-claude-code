# ch09: Compact

> 裁剪是丢弃信息，compact 是把旧信息压缩成可继续工作的摘要。

## 本章目标

ch08 的裁剪可以快速降上下文，但它会丢失细节。本章实现 `CompactManager`，用一次 LLM 调用把长历史总结成短摘要，再保留最近几轮消息，让 agent 能继续接着做事。

## Compact 解决什么问题

Compact 的本质是把长 transcript 变成短上下文。这个过程一定有损：原始命令输出、模型犹豫、失败路径和局部细节都会被折叠。好的摘要不是把聊天记录改写得更顺，而是保留后续继续工作的最小充分信息。

对 coding agent 来说，摘要至少应该覆盖五类内容：当前目标、已经做出的关键决策、改过或看过的文件、验证过的命令和结果、下一步计划或未解决风险。缺少这些信息，模型恢复后就容易重复探索、误判状态，或者覆盖用户已有改动。

需要区分 active context 和 durable transcript。压缩可以改变下一轮发给模型的内容，但不应该抹掉本地完整记录。真实系统通常会保留完整 transcript，同时把摘要作为新的上下文入口；这让 agent 既能继续工作，也能在需要时追溯原始事实。

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

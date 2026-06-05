# ch09: Compact

> 当机械裁剪不够时，让模型把历史压成一段可继续工作的摘要。

## 本章目标

ch08 的 `ContextManager` 会截断工具输出、裁剪旧消息。这种机械压缩很快、便宜，但它不理解内容。旧消息里可能有重要结论，一旦裁掉就丢了。

本章实现 `CompactManager`，用一次 LLM 调用把长对话总结成短摘要，再保留最近几轮消息：

```text
long messages
  |
  v
LLM summarize
  |
  v
[summary message] + recent messages
```

同时 CLI 支持 `/compact`，用户可以手动触发压缩。ContextManager 也可以在机械裁剪仍超预算时自动触发 compact。

## 先建立心智模型

### 裁剪是删除，compact 是改写

ch08 的裁剪像这样：

```text
旧消息 -> 直接省略
```

ch09 的 compact 像这样：

```text
旧消息 -> 提炼成摘要 -> 放回上下文
```

摘要不是完整历史，但它保留了继续任务所需的要点：

- 用户目标
- 已经检查过的文件
- 已经做过的修改
- 测试结果
- 当前未解决的问题

### compact 后的 messages 仍然要像对话

压缩结果不能只是一段孤立文本。它要变成模型下一轮能理解的上下文。

推荐形状：

```python
[
    {
        "role": "user",
        "content": "Conversation summary so far:\n..."
    },
    ...recent_messages
]
```

这样模型会把摘要当作用户提供的背景，再结合最近消息继续工作。

## Compact 的流程

```text
用户输入 /compact
  |
  v
format transcript
  |
  v
client.chat(summary_prompt)
  |
  v
extract summary text
  |
  v
build_compact_messages(summary, recent_messages)
```

自动 compact 的流程类似，只是触发点从 CLI 变成 context budget 超限。

## 本章要实现什么

主要修改：

- [compact.py](../../src/tiny_claude_code/compact.py)
- [context.py](../../src/tiny_claude_code/context.py)
- [cli.py](../../src/tiny_claude_code/cli.py)
- [agent.py](../../src/tiny_claude_code/agent.py)

需要实现：

- `CompactManager.__init__`
- `summarize`
- `build_compact_messages`
- `compact`
- `_format_transcript`
- `_content_to_text`
- `_extract_text`
- CLI 的 `/compact` 命令
- ContextManager 自动 compact 的接入点

## 实现路线

### 第一步：格式化 transcript

LLM 总结前，需要把 messages 转成可读文本：

```text
user: ...
assistant: ...
tool_result: ...
```

不需要保留所有底层 block 结构。目标是让总结模型看懂发生过什么。

### 第二步：调用 LLM 生成摘要

summary prompt 要明确要求输出继续工作需要的信息，而不是泛泛总结。

```text
Summarize this agent conversation for continuation.
Include goals, files inspected, changes made, test results, and open issues.
```

测试里会用 mock LLM，所以实现应走 `client.chat(...)`，不要绕过客户端。

### 第三步：构造新 messages

保留最近 N 条消息，前面加摘要消息：

```text
[summary] + messages[-keep_recent:]
```

N 不宜太小，否则模型会失去当前动作上下文；也不宜太大，否则 compact 效果不明显。

### 第四步：接入手动和自动触发

手动触发：

```text
/compact
```

自动触发：

```text
ContextManager.compact(...)
  |
  +-- trim/snip 后仍超预算
  |
  +-- CompactManager.compact(...)
```

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 09
```

测试覆盖：

- summarize 会调用 LLM 并返回文本
- build_compact_messages 会包含摘要和最近消息
- compact 会减少消息数量
- ContextManager 可以自动调用 LLM 总结
- agent loop 自动 compact 后仍能回答

## 验收任务

进行一段多轮对话后输入：

```text
/compact
```

期望行为：

- CLI 显示压缩完成
- messages 数量明显减少
- agent 仍然知道当前任务背景

可以继续输入：

```text
继续刚才的任务
```

看模型是否能基于摘要继续。

## 常见错误

### 摘要太泛

“我们讨论了项目”没有用。摘要要包含文件名、命令结果、修改点和未完成事项。

### compact 删除最近消息

最近几轮通常包含当前工具调用和最新错误。必须保留一段 tail。

### summary message 角色不清楚

建议用 user role 注入摘要背景。不要假装这是 assistant 刚刚说的话。

### 自动 compact 递归调用失控

ContextManager 调用 CompactManager 时要避免反复压缩同一批消息。

## 思考题

1. LLM 摘要相比机械裁剪有什么优势？
2. 摘要可能引入哪些错误？
3. `/compact` 应该由用户手动触发，还是完全自动？
4. 摘要中应该保留工具原始输出吗？

## Bonus Tasks

- 给摘要增加固定模板。
- compact 后显示压缩前后的 token 估算。
- 保存 compact 摘要到 session metadata。
- 给 `/compact preview` 显示将要生成的 transcript。

## 本章小结

你让 agent 有了长对话续航能力：

```text
机械压缩保底
LLM 摘要保留语义
最近消息保留现场
```

下一章会把这种“继续工作”的能力扩展到进程之外：退出 CLI 后，agent 仍然能恢复会话，并记住项目长期知识。

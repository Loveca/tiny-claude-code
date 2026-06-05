# ch10: Session and Memory

> 会话让 agent 能恢复现场，记忆让 agent 能跨任务积累项目知识。

## 本章目标

前面几章的 `messages` 都保存在内存里。CLI 一退出，对话就丢了。用户下次回来时，agent 不知道之前查过什么、改过什么、测试结果怎样。

本章实现两类持久化：

- `SessionManager`：保存和恢复完整对话历史
- `MemoryManager`：保存可复用的长期项目知识

```text
短期状态: messages -> .tiny-claude-code/sessions/
长期知识: memory   -> .tiny-claude-code/memory/
```

## 先建立心智模型

### Session 是“恢复这次对话”

Session 保存的是一次具体对话的上下文。它适合回答：

- 上次聊到哪里？
- 上次 agent 调用了哪些工具？
- 最近一次任务结果是什么？

```text
session_id.json
  |
  +-- messages
  +-- metadata
  +-- updated_at
```

`--resume` 就是加载最近 session，然后继续往同一个 messages 列表里追加。

### Memory 是“项目长期知识”

Memory 不保存所有聊天细节，而是保存提炼后的稳定事实。例如：

- 这个项目用 `pytest` 跑测试
- 示例 bug 目录本来设计为失败
- 插件示例放在 `examples/plugins`

这些知识应该在新会话开始时也能注入 system prompt。

```text
memory entry
  |
  +-- category
  +-- title
  +-- content
```

## Session 工作流程

```text
CLI 启动
  |
  +-- 普通启动 -> new_session_id()
  |
  +-- --resume -> latest_session_id() -> load()
  |
  v
每轮 agent_loop 后 save(messages, metadata)
```

session 文件建议使用 JSON，便于测试和调试。

## Memory 工作流程

用户输入：

```text
/memory add "Testing" "Run tests with pytest -q"
```

MemoryManager 保存为 Markdown 文件：

```text
---
category: Testing
title: Run tests with pytest -q
---

Run tests with pytest -q
```

启动时，MemoryManager 可以根据当前 query 或全部索引构建 system context：

```text
Project memory:
- Testing: Run tests with pytest -q
```

## 本章要实现什么

主要修改：

- [session.py](../../src/tiny_claude_code/session.py)
- [memory.py](../../src/tiny_claude_code/memory.py)
- [cli.py](../../src/tiny_claude_code/cli.py)

需要实现：

- `SessionManager.__init__`
- `new_session_id`
- `save`
- `load`
- `list_sessions`
- `latest_session_id`
- `MemoryManager.save`
- `load_relevant`
- `build_index`
- `build_system_context`
- `/memory add` 和 `/memory list`

## 实现路线

### 第一步：session 目录结构

所有运行时文件放在 `.tiny-claude-code/` 下：

```text
.tiny-claude-code/
  sessions/
  memory/
```

这样不会污染源码目录，也方便 `.gitignore` 排除。

### 第二步：保存完整 messages

`messages` 里可能有 dict、list、字符串。测试使用的是可 JSON 序列化对象，直接 `json.dump` 即可。真实 SDK block 可能需要先转 dict，这是后续可以增强的点。

### 第三步：按时间列 session

`list_sessions()` 应该返回最新的在前面。`latest_session_id()` 只需要取第一个。

### 第四步：保存 memory entry

文件名可以由 title slugify 得到。slug 不需要完美，只要稳定、可读、不含危险字符。

### 第五步：按关键词加载 relevant memory

教学版本可以用简单关键词匹配。query 命中 title、category 或 content 时返回对应记忆。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 10
```

测试覆盖：

- session save/load 往返
- session 列表按最新排序
- memory 保存 frontmatter
- memory 可以按关键词匹配
- memory index 会列出条目
- system prompt 包含 memory context
- `/memory add` 能写入记忆

## 验收任务

启动 agent，添加记忆：

```text
/memory add "Testing" "This project runs chapter tests with python scripts/dev.py test --ch NN"
```

退出后重新启动：

```bash
python scripts/dev.py run -- --resume
```

期望行为：

- 上次会话可以恢复
- system prompt 中包含项目记忆

## 常见错误

### 把 memory 当 session 保存

session 是完整历史，memory 是提炼知识。不要把所有聊天都写进 memory。

### session_id 不唯一

可以用时间戳加随机后缀，避免同一秒启动多次时覆盖。

### list_sessions 不排序

`--resume` 依赖最新 session。如果排序错，会恢复旧对话。

### frontmatter 格式不稳定

测试会读取 YAML 风格 frontmatter。分隔线和字段名要稳定。

## 思考题

1. 哪些信息适合进入 memory，哪些只适合留在 session？
2. memory 自动写入是否安全？为什么？
3. 如果 memory 中有过期信息，应该如何更新或删除？
4. session 文件是否应该加密？

## Bonus Tasks

- 增加 `/memory delete`。
- 给 session 增加标题。
- 保存 compact 摘要到 session metadata。
- 用更好的检索算法加载 memory。

## 本章小结

你把 agent 从“一次性进程”变成了可恢复系统：

```text
session 恢复现场
memory 积累长期知识
system prompt 注入项目背景
```

下一章会让 agent 在单次任务内部也更有条理：用 todo 系统管理步骤和进度。

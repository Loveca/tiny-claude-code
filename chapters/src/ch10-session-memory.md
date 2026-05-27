# ch10: Session and Memory

> session 让 agent 记住这次对话，memory 让 agent 记住这个项目。

## 本章目标

前两章解决了“当前对话太长”的问题。本章解决两个更长期的问题：

- 退出 CLI 后，下一次还能恢复会话。
- 项目经验可以被保存成长期记忆，之后启动时注入 system prompt。

## 问题：压缩解决不了进程退出和跨任务经验

Context 和 compact 都发生在一次运行中的消息列表里。如果用户关掉 CLI，内存里的 messages 就没了；如果明天重新打开项目，agent 也不会自然记得“这个项目用 pytest”“不要提交 `.tiny-claude-code/` 目录”这类稳定事实。

这里其实有两类状态：

- 这次对话的完整轨迹：用户说了什么，模型调用了哪些工具，结果是什么。
- 跨任务仍然有价值的知识：项目约定、用户偏好、常用验证命令。

前者需要 session，后者需要 memory。

## 解决方案：把短期轨迹和长期知识分层保存

```text
.tiny-claude-code/
  sessions/
    session-id.json      # messages + metadata
  memory/
    project.md           # long-lived facts
    preferences.md
```

Session 负责恢复“这次任务进行到哪”。Memory 负责在新任务开始时注入“这个项目有哪些稳定背景”。分开以后，agent 可以恢复旧对话，也可以在全新任务里只加载相关长期知识。

## 为什么 Session 和 Memory 要分开

Session 是一次任务的运行轨迹，Memory 是跨任务复用的稳定事实。前者像工作日志，记录用户输入、模型回复、工具调用和结果；后者像项目偏好或长期知识，例如“这个仓库用 pytest 验证”“不要自动格式化某些生成文件”。

把二者混在一起会带来两个问题。第一，session 太细，全部长期保存会污染未来任务；第二，memory 太粗，如果塞进当前 transcript，会让模型误以为所有偏好都和当前任务有关。好的 agent 会在需要时检索相关 memory，而不是每轮无差别注入全部记忆。

本章实现的 session/memory 是最小版本，但边界要先立住：session 解决“这次对话怎么恢复”，memory 解决“下次任务应该继承什么稳定知识”。

## Session

`SessionManager` 把消息保存到：

```text
.tiny-claude-code/sessions/
```

它提供：

- `save(session_id, messages, metadata)`
- `load(session_id)`
- `list_sessions()`
- `latest_session_id()`

CLI 支持：

```bash
python scripts/dev.py run -- --resume
```

或者直接运行模块时：

```bash
tiny-claude-code --resume
```

`--resume` 不带参数时恢复最近一次 session；带参数时恢复指定 session id。

## 工作原理

保存 session 时，关键是把消息和元数据一起落盘。元数据用于列表展示和恢复选择，messages 用于真正恢复上下文：

```python
session_manager.save(
    session_id,
    messages=messages,
    metadata={
        "created_at": now,
        "updated_at": now,
        "cwd": str(workspace),
        "title": first_user_prompt[:80],
    },
)
```

恢复时不要把 session 当作 memory 注入 system prompt，而是直接恢复 messages。它仍然是对话历史的一部分。

## Memory

`MemoryManager` 把长期记忆保存到：

```text
.tiny-claude-code/memory/
```

每条记忆是一个带 frontmatter 的 Markdown 文件：

```markdown
---
category: project
title: Uses pytest
created_at: ...
---

Run tests with pytest -q
```

CLI 支持：

```text
/memory add "Testing" "Run tests with pytest -q"
/memory list
```

启动时，相关 memory 会被注入 system prompt，帮助 agent 继承项目经验。

## 相对 ch09 的变化

| 组件 | ch09 | ch10 |
| --- | --- | --- |
| 状态范围 | 当前 active context | 磁盘持久化状态 |
| 恢复能力 | 压缩后继续当前对话 | CLI 退出后恢复 session |
| 长期知识 | 摘要里临时保留 | memory 文件跨任务复用 |
| 加载策略 | 摘要 + recent tail | session 全量恢复，memory 按需检索 |

## 实现路线

### 第一步：定义 session 文件格式

Session 至少要保存 `messages` 和 `metadata`。metadata 用于列表展示和恢复选择，messages 用于真正恢复对话。

### 第二步：实现 save/load/list

先让 session 可以完整落盘和恢复，再接 CLI。不要一开始就把 `--resume` 写进入口逻辑里，否则很难单独测试。

### 第三步：定义 memory 文件格式

Memory 适合用 Markdown 加 frontmatter。正文适合人读，frontmatter 适合程序检索。

### 第四步：启动时注入相关 memory

不要无差别注入所有 memory。先用简单关键字匹配，后续再考虑向量检索或更复杂的索引。

## 测试讲解

Session 测试要证明 messages 能原样恢复，包括 tool_use 和 tool_result 这类结构化内容。只测普通文本消息不够。

Memory 测试要证明检索是相关的，而不是把所有记忆都塞进 system prompt。否则 memory 越多，agent 越容易被无关信息干扰。

## 常见错误

### 把 session 当 memory

Session 是一次任务的详细轨迹，不适合长期注入所有未来任务。它太细，会污染后续上下文。

### 把 memory 当 transcript

Memory 应该是稳定事实，不应该保存每一轮对话细节。否则 memory 会快速膨胀并失去检索价值。

### 恢复 session 时丢掉工具消息

只恢复 user/assistant 文本会破坏 agent loop 的状态。tool_use 和 tool_result 也是对话协议的一部分。

## 运行测试

```bash
python scripts/dev.py test --ch 10
```

测试覆盖：

- session 保存和加载
- session 按更新时间排序
- memory frontmatter 格式
- memory 关键词检索
- `MEMORY.md` 索引生成
- system prompt 注入 memory
- `/memory add` 命令

## 验收任务

1. 启动 agent，进行几轮对话后退出。
2. 使用 `--resume` 启动，确认上一轮消息被恢复。
3. 输入 `/memory add "Testing" "Run tests with pytest -q"`。
4. 再次启动，确认 agent 的 system prompt 会包含这条项目记忆。

## 思考题

1. session 和 memory 的边界是什么？
2. 哪些信息适合长期保存，哪些只应该留在当前会话？
3. memory 关键词检索有什么局限？

## 本章小结

ch10 让 agent 从一次性脚本变成可恢复的工作伙伴。session 保存短期上下文，memory 保存跨会话经验，二者共同支撑更长周期的项目开发。

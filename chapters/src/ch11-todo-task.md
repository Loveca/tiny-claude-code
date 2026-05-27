# ch11: Todo and Task System

> 复杂任务不是靠记忆硬扛，而是靠显式状态推进。

## 本章目标

Part 3 让 agent 能保存和压缩上下文，但它还没有真正的任务状态。本章实现 `TaskManager` 和 `TodoWrite` 工具，让 agent 可以创建 todo、更新进度、处理依赖，并把任务状态持久化到项目目录。

## 为什么 Todo 要存在于模型之外

长任务里，模型很容易在局部细节中丢失全局目标。Todo 系统的作用不是替模型思考，而是把计划状态外部化：哪些事待做，哪件事正在做，哪些事已经完成。它给 agent 一个可检查、可恢复、可向用户解释的任务骨架。

“最多一个 `in_progress`”看起来像小规则，但它能显著降低混乱度。agent 每次只承诺一个当前动作，完成后再移动状态；这样失败、暂停、恢复和用户插话时，都能看清当前工作点。

真实 Claude Code 这类工具还会用 reminder 或系统提示把 Todo 状态重新注入模型，形成轻量的自我约束。但关键仍然是：Todo 存在于模型外部，由 harness 持久化和校验，而不是只靠模型在自然语言里记住计划。

## 核心概念

`TaskManager` 管理一组 `TodoItem`：

- `pending`：等待执行
- `in_progress`：正在执行
- `completed`：已完成
- `blocked`：被依赖阻塞

系统保证同一时间最多只有一个 `in_progress`。如果一个 todo 设置了 `blocked_by`，依赖未完成时会自动变成 `blocked`；依赖完成后会回到 `pending`。

## 持久化

任务文件写入：

```text
.tiny-claude-code/tasks/{id}.json
```

这个目录已经在 `.gitignore` 中，属于本地运行状态，不进入仓库。

## 工具接入

`TodoWriteTool` 暴露为工具名：

```text
TodoWrite
```

它接收 todo 列表，创建或更新任务。默认工具注册表会自动包含它。

## 运行测试

```bash
python scripts/dev.py test --ch 11
```

测试覆盖：

- 新 todo 默认是 `pending`
- 同一时间只有一个 `in_progress`
- 依赖未完成时自动 `blocked`
- 依赖完成后自动解除阻塞
- 连续多轮未更新时产生提醒
- `TodoWrite` 工具写入 manager

## 验收任务

让 agent 完成一个多步小任务，例如：

```text
给这个项目新增一个说明文件，并运行测试确认没有破坏现有功能。
```

预期 agent 会先写 todo，再逐步更新状态。

## 思考题

1. 为什么 todo 状态应该持久化，而不只放在 prompt 里？
2. “同一时间只有一个 in_progress” 会限制哪些场景？
3. 依赖关系应该由 agent 自己维护，还是由任务系统强制维护？

## 本章小结

ch11 给 agent 增加了任务骨架。它不再只是连续聊天，而是能把复杂工作拆成显式、可恢复的步骤。

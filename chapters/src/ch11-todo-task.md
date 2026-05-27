# ch11: Todo and Task System

> 复杂任务不是靠记忆硬扛，而是靠显式状态推进。

## 本章目标

Part 3 让 agent 能保存和压缩上下文，但它还没有真正的任务状态。本章实现 `TaskManager` 和 `TodoWrite` 工具，让 agent 可以创建 todo、更新进度、处理依赖，并把任务状态持久化到项目目录。

## 问题：长任务需要可见进度

没有 Todo 的 agent 也能完成简单任务，但一旦任务超过三五步，它就容易出现几类问题：重复做已完成的事，跳过验证步骤，在用户插话后忘记当前阶段，或者把“正在做什么”藏在自然语言回复里。

任务状态如果只存在于模型上下文里，会受上下文压缩、摘要遗漏和注意力漂移影响。Todo 工具把状态移到 harness 里：

```text
LLM proposes plan
      |
      v
TodoWrite tool
      |
      v
TaskManager persists state
      |
      v
reminder/status re-enters future turns
```

这让计划变成可检查数据，而不是聊天记录里的愿望。

## 解决方案：让计划成为一个工具

TodoWrite 和 ShellTool、ReadTool 一样是工具。区别在于它不改变项目代码，而是改变 agent 自己的执行状态。模型需要显式调用它来声明计划和进度。

这有两个好处：

- harness 可以校验状态，例如只允许一个 `in_progress`。
- 用户和后续模型轮次可以看到同一份任务状态。

真实 agent 的 Todo 不只是 UI 功能，它是运行时控制的一部分。

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

## 工作原理

TaskManager 的更新不是简单覆盖列表，而是先规范化、再校验、再持久化：

```python
def update(items):
    normalized = normalize_items(items)
    ensure_only_one_in_progress(normalized)
    resolve_blocked_items(normalized)
    save_each_item(normalized)
    return render_status(normalized)
```

reminder 机制则在模型长时间不更新 todo 时介入。它不是强迫模型照做，而是把“你已经很久没更新计划了”变成下一轮上下文中的观察，帮助模型回到任务轨道。

## 相对 ch10 的变化

| 组件 | ch10 | ch11 |
| --- | --- | --- |
| 持久化内容 | 对话和长期记忆 | 显式任务状态 |
| 模型行为 | 自然语言描述计划 | 通过 TodoWrite 更新计划 |
| 状态校验 | 基本文件读写 | 单一 in_progress、依赖检查 |
| 恢复价值 | 恢复对话 | 恢复任务进度 |

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

## 实现路线

### 第一步：定义 TodoItem

先把 `id`、`content`、`status`、`blocked_by` 这些字段固定下来。任务系统最怕字段随意漂移，后续恢复和渲染都会出问题。

### 第二步：实现状态校验

状态机规则应该由 TaskManager 强制执行，而不是让模型自觉遵守。尤其是“同一时间只有一个 in_progress”。

### 第三步：实现 TodoWriteTool

TodoWriteTool 只是工具入口，真正状态更新交给 TaskManager。这样 CLI、测试和未来 UI 都能复用同一套任务逻辑。

### 第四步：加入 reminder

reminder 是轻量反馈机制：当模型长时间不更新 todo，就把状态提醒重新放回上下文，帮助它回到主线。

## 测试讲解

本章测试要证明任务系统会纠正或拒绝非法状态，而不是只保存模型传来的列表。依赖关系、blocked 状态和单一 in_progress 都应该被 TaskManager 统一处理。

reminder 测试要控制轮次计数。它不是每轮都出现，而是在模型连续忽略任务状态后出现。

## 常见错误

### Todo 只做展示

如果 Todo 只是打印给用户看，不参与模型后续上下文，它对 agent 行为帮助有限。Todo 状态必须能回到后续轮次。

### 允许多个 in_progress

多个当前任务会让恢复和用户插话变得混乱。除非做真正并行调度，否则保持单一焦点更稳。

### 依赖关系只靠自然语言描述

`blocked_by` 应该是结构化字段。自然语言里的“先做 A 再做 B”很容易在长上下文里丢失。

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

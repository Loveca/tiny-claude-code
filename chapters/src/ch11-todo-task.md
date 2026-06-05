# ch11: Todo and Task System

> 复杂任务不能只靠模型临场发挥；agent 需要显式记录计划和进度。

## 本章目标

前面的 agent 已经能读写代码、跑测试、恢复会话。但面对多步骤任务时，它可能会忘记做过什么、跳过验证，或者在多个方向之间来回切换。

本章实现 `TaskManager` 和 `TodoWrite` 工具，让模型能显式维护 todo 列表：

```text
pending -> in_progress -> completed
          |
          v
        blocked
```

完成后，agent 可以把复杂任务拆成小步骤，并在执行过程中更新状态。

## 先建立心智模型

### Todo 是外化的工作记忆

模型可以在文本里说“我将先做 A 再做 B”，但这不稳定。Todo 工具把计划写进本地状态：

```text
1. pending     阅读失败测试
2. in_progress 定位实现文件
3. pending     修改代码
4. pending     重新运行测试
```

状态变成结构化数据后，harness 可以检查规则，例如同一时间只能有一个 `in_progress`。

### TodoWrite 是给模型用的工具

用户不需要手动维护 todo。模型在任务开始时可以调用：

```text
TodoWrite([
  {"id": "1", "content": "Run tests", "status": "pending"},
  {"id": "2", "content": "Fix failure", "status": "pending"}
])
```

agent loop 把它当作普通工具调用，TaskManager 负责保存和规范化。

## 状态规则

### 只能有一个 in_progress

如果模型一次把多个任务标为 `in_progress`，TaskManager 应该规范化，只保留一个，其余改回 `pending`。

```text
bad:
  A in_progress
  B in_progress

normalized:
  A in_progress
  B pending
```

### blockedBy 表示依赖

任务可以声明依赖：

```text
B blockedBy A
```

如果 A 没完成，B 不能开始。A 完成后，B 可以从 blocked 回到 pending。

### 长时间不更新要提醒

如果 agent 连续几轮没有更新 todo，可以向模型注入提醒：

```text
Remember to update the todo list as you make progress.
```

这不是强制，但能让模型更稳定地跟踪任务。

## 本章要实现什么

主要修改：

- [tasks.py](../../src/tiny_claude_code/tasks.py)
- [tools/__init__.py](../../src/tiny_claude_code/tools/__init__.py)
- [agent.py](../../src/tiny_claude_code/agent.py)

需要实现：

- `TaskManager.__init__`
- `create`
- `update`
- `write`
- `list`
- `tick_without_update`
- `load`
- `_normalize`
- `_persist`
- `TodoWriteTool`
- 默认注册表包含 todo 工具

## 实现路线

### 第一步：定义 todo 数据形状

每个 todo 至少包含：

```python
{
    "id": "1",
    "content": "Run tests",
    "status": "pending",
}
```

可选字段：

```python
{"blockedBy": ["1"]}
```

### 第二步：实现状态规范化

`write` 接收一组 todo 后，先规范化再保存：

- 缺失 status 时默认 `pending`
- 多个 `in_progress` 只保留一个
- 依赖未完成时标为 `blocked`
- 依赖完成后解除 blocked

### 第三步：持久化

todo 状态保存到 `.tiny-claude-code/tasks/`。这样 session 恢复后，任务状态也能加载。

### 第四步：实现工具

`TodoWriteTool.schema` 告诉模型参数是 todo 列表。`execute` 调用 TaskManager，并返回当前列表摘要。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 11
```

测试覆盖：

- 新 todo 默认 pending
- 同一时间只能一个 in_progress
- blocked 依赖完成后恢复 pending
- 连续三轮无更新会产生提醒
- TodoWriteTool 能更新 manager
- 默认注册表包含 todo 工具

## 验收任务

运行 agent：

```bash
python scripts/dev.py run
```

输入：

```text
给这个项目添加一个合理的 .gitignore，并验证不会误删已有内容
```

期望行为：模型先创建 todo，再按步骤读取现状、写入文件、检查结果。

## 常见错误

### 允许多个 in_progress

这会让 todo 失去“当前正在做什么”的意义。规范化时必须处理。

### blocked 状态不会解除

依赖完成后，要重新计算被阻塞任务的状态。

### reminder 每轮都出现

只有连续多轮没有更新时才提醒。更新 todo 后计数要清零。

### TodoWrite 不持久化

任务系统如果只在内存里，resume 后就丢失进度。

## 思考题

1. Todo 是给用户看的，还是给模型看的？
2. 任务状态应该由模型决定，还是由 TaskManager 强制规范？
3. blockedBy 能表达哪些常见开发依赖？
4. 什么时候 todo 反而会增加负担？

## Bonus Tasks

- 增加优先级字段。
- 增加 `/todo list` CLI 命令。
- 在最终回答里自动总结完成的 todo。
- 支持任务分组。

## 本章小结

你让 agent 拥有了显式任务状态：

```text
计划可见
进度可追踪
依赖可表达
长任务不容易散掉
```

下一章会进一步处理复杂任务：把旁路探索交给子 agent，让主上下文保持干净。

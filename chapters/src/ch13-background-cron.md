# ch13: Background and Cron

> 慢任务不应该阻塞思考，定时任务不应该依赖人工提醒。

## 本章目标

本章实现两个协作能力：

- `BackgroundManager`：把慢命令放到后台执行。
- `CronScheduler`：用简单 cron 表达式保存定时 prompt。

这让 agent 可以发起长时间运行的命令，同时继续对话；也可以记录未来需要触发的任务。

## 问题：慢命令会卡住交互

很多开发命令不是瞬间完成的：完整测试套件、构建、启动 dev server、长时间 lint、日志监控。如果 agent 每次都同步等待，用户只能看着 CLI 卡住，模型也无法处理新的输入或继续其他工作。

同步执行适合短命令：

```text
tool_use(shell: "pytest -q")
        |
        v
wait until finished
        |
        v
tool_result
```

但长命令更适合拆成“提交任务”和“稍后观察结果”。

## 解决方案：把慢操作变成可轮询任务

BackgroundManager 让 agent 先拿到一个 task id，然后继续工作：

```text
submit(command) -> task_id
poll(task_id)   -> running / completed / failed
result(task_id) -> stdout / stderr / exit_code
```

当后台任务完成时，它的结果可以作为下一轮观察注入 messages。这样 agent 不需要一直阻塞等待，也不会丢失命令结果。

## 为什么需要后台任务

有些命令很慢：测试套件、构建、长时间服务、文件监控。如果主 agent 每次都阻塞等待，用户体验会变差，模型也会被迫把“等待”当作主要工作。后台任务的价值是让慢操作独立运行，主循环继续处理用户输入和其他观察。

后台任务的结果应该以结构化观察回到 agent，而不是在终端里悄悄消失。这样模型能在下一轮看到“任务完成、退出码、关键输出”，再决定是否继续修复或报告结果。

Cron 则是另一类能力：它表达“未来按计划触发某件事”。在 tiny-claude-code 里我们实现的是轻量版本，重点是持久化意图和可检查状态；生产系统还需要更可靠的调度器、重试策略、时区处理和权限隔离。

## Background

`BackgroundManager` 提供：

- `submit(command)`：提交后台命令，立即返回 task id。
- `poll(task_id)`：查询状态。
- `get_result(task_id)`：读取完成结果。
- `completed_notifications()`：返回一次性完成通知。

默认工具注册表包含：

```text
BackgroundSubmit
BackgroundPoll
```

CLI 会在下一轮 agent 执行前，把已完成的后台任务结果注入消息历史。

## 工作原理

后台任务的最小实现可以用线程或子进程管理：

```python
task_id = background.submit("pytest -q")

while True:
    status = background.poll(task_id)
    if status.done:
        result = background.get_result(task_id)
        break
```

关键是状态要可查询，结果要可回填。否则后台任务只是“把命令扔出去”，agent 无法可靠地基于结果继续推理。

## Cron

`CronScheduler` 支持五字段表达式：

```text
*/5 * * * *
```

当前实现支持：

- `*`
- `*/N`
- 单个数字

定时任务写入：

```text
.tiny-claude-code/scheduled_tasks.json
```

默认工具注册表包含：

```text
CronSchedule
```

## 相对 ch12 的变化

| 组件 | ch12 | ch13 |
| --- | --- | --- |
| 并行方式 | 子 agent 探索子任务 | 后台进程执行慢命令 |
| 返回时机 | 子 agent 完成后立即返回摘要 | 主循环稍后轮询或接收通知 |
| 状态保存 | 子上下文临时存在 | task/cron 状态可持久化 |
| 典型用途 | 搜索、调查、分析 | 长测试、服务、定时提醒 |

## 实现路线

### 第一步：定义后台任务状态

任务至少需要 `id`、`command`、`status`、`stdout`、`stderr`、`exit_code`。状态结构越清楚，后续轮询越简单。

### 第二步：提交后立即返回 task_id

后台任务的意义是主循环不阻塞。提交命令后应该尽快返回，而不是等命令完成。

### 第三步：实现 poll/result

轮询和取结果分开，agent 可以先看任务是否完成，再决定是否读取完整输出。

### 第四步：实现 cron 持久化

cron 表达的是未来意图。即使当前进程退出，任务定义也应该能恢复。

## 测试讲解

后台任务测试要证明 submit 不阻塞。可以用一个短 sleep 命令，并断言 submit 很快返回 task id。

cron 测试要 mock 时间。不要依赖真实分钟流逝，否则测试会慢且不稳定。

## 常见错误

### 后台任务绕过权限

后台执行仍然是执行命令，必须走同样的 shell 权限检查。

### 结果只打印到终端

如果结果没有结构化保存，agent 后续就无法基于它继续推理。

### cron 当成完整调度系统

本章 cron 是最小教学实现。生产级调度还需要时区、错过执行、重试、并发和持久 worker。

## 运行测试

```bash
python scripts/dev.py test --ch 13
```

测试覆盖：

- 后台任务提交立即返回
- 后台任务完成后可 poll
- 后台通知只返回一次
- cron `*/5` 匹配
- cron 任务持久化和恢复
- `CronSchedule` 工具写入任务
- 默认 registry 包含后台和 cron 工具

## 验收任务

运行 agent 后输入：

```text
在后台运行 pytest -q，然后继续告诉我这个项目目前实现到哪一章。
```

预期 agent 可以提交后台任务，继续对话，并在后续轮次拿到测试结果。

## 思考题

1. 后台任务结果应该什么时候注入上下文？
2. cron 表达式需要支持完整语法吗？
3. 后台命令和普通 `bash` 工具应该共享同一套权限策略吗？

## 本章小结

ch13 让 agent 开始具备协作式执行能力。它可以把慢操作放到后台，也可以把未来任务保存下来，为后续更完整的自动化打基础。

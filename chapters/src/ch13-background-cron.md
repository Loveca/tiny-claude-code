# ch13: Background and Cron

> 慢任务不应该阻塞思考，定时任务不应该依赖人工提醒。

## 本章目标

本章实现两个协作能力：

- `BackgroundManager`：把慢命令放到后台执行。
- `CronScheduler`：用简单 cron 表达式保存定时 prompt。

这让 agent 可以发起长时间运行的命令，同时继续对话；也可以记录未来需要触发的任务。

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

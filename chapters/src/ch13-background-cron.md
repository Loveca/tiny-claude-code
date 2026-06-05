# ch13: Background and Cron

> 有些工作很慢，有些工作应该定时发生；agent 不应该只能同步等待。

## 本章目标

到目前为止，工具调用都是同步的。模型调用 `bash` 跑测试，agent loop 等命令结束后才继续。如果命令很慢，用户只能等。

本章实现两类异步能力：

- `BackgroundManager`：后台运行命令，之后轮询结果
- `CronScheduler`：保存定时任务，在指定时间返回待执行 prompt

```text
后台任务:
submit -> task_id -> poll -> result

定时任务:
schedule cron -> persist -> due(now) -> prompts
```

## 先建立心智模型

### 后台任务解决“慢”

同步工具调用：

```text
run tests
  |
  v
等待很久
  |
  v
返回结果
```

后台工具调用：

```text
submit tests -> task_id
  |
  v
主 agent 可以继续对话
  |
  v
poll task_id -> completed result
```

这适合长测试、构建、静态分析等任务。

### Cron 解决“以后”

CronScheduler 不直接让模型睡到未来。它保存计划，并在轮询时告诉系统哪些任务到期。

```text
"*/5 * * * *" + "run tests"
  |
  v
每分钟检查 now 是否匹配
  |
  v
匹配则返回 prompt
```

本章只实现简化 cron：五字段表达式，支持 `*`、具体数字、`*/n`。

## Background 工作流程

```text
BackgroundSubmitTool.execute(command)
  |
  v
BackgroundManager.submit(command)
  |
  v
创建线程运行命令
  |
  v
立即返回 task_id
```

稍后：

```text
BackgroundPollTool.execute(task_id)
  |
  v
pending / running / completed + result
```

后台任务完成后，还可以通过 `completed_notifications()` 返回一次性通知，注入下一轮消息。

## Cron 工作流程

```text
CronScheduleTool.execute(expression, prompt)
  |
  v
CronScheduler.schedule(...)
  |
  v
保存到 .tiny-claude-code/scheduled_tasks.json
```

检查到期任务：

```text
CronScheduler.due(now)
  |
  v
返回匹配当前时间的任务列表
```

## 本章要实现什么

主要修改：

- [background.py](../../src/tiny_claude_code/background.py)
- [cron.py](../../src/tiny_claude_code/cron.py)
- [tools/__init__.py](../../src/tiny_claude_code/tools/__init__.py)

需要实现：

- `BackgroundManager`
- `BackgroundSubmitTool`
- `BackgroundPollTool`
- `CronScheduler`
- `CronScheduleTool`
- 默认注册表包含后台和 cron 工具

## 实现路线

### 第一步：后台任务数据结构

每个 task 需要：

```python
{
    "id": "...",
    "command": "...",
    "status": "running",
    "result": None,
}
```

线程结束后更新为 `completed`，并保存 stdout、stderr、exit code。

### 第二步：submit 立即返回

`submit` 不能等待命令完成。它创建线程后立刻返回 task_id。

### 第三步：poll 查询状态

`poll(task_id)` 返回状态摘要。未知 task_id 返回可读错误。

### 第四步：cron 匹配

五字段分别是：

```text
minute hour day month weekday
```

本章只需要支持：

- `*`
- `*/5`
- `10`

### 第五步：持久化 cron

定时任务要保存到 `.tiny-claude-code/scheduled_tasks.json`，并能重新 load。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 13
```

测试覆盖：

- submit 会立即返回，不等待结果
- poll 能拿到 completed result
- 后台工具 submit/poll 可用
- 完成通知只返回一次
- `*/5 * * * *` 能匹配正确分钟
- cron schedule 会持久化
- cron 工具能保存任务
- due 返回匹配任务
- 默认注册表包含后台工具

## 验收任务

运行 agent：

```text
在后台运行 pytest -q，然后继续告诉我这个项目的目录结构
```

期望行为：agent 提交后台任务后，不必一直等待测试完成，可以继续其他工作。稍后再 poll 任务结果。

## 常见错误

### submit 阻塞到命令结束

这就不是后台任务了。测试会检查 submit 迅速返回。

### completed_notifications 重复返回

通知应该只返回一次，否则每轮都会重复提醒同一结果。

### cron 不持久化

定时任务如果只存在内存里，重启后全部丢失。

### cron 匹配 weekday 错误

先明确使用 Python 的 weekday 还是 cron 的 weekday 语义。教学测试通常只覆盖简单分钟匹配，但实现要保持一致。

## 思考题

1. 后台任务结果应该自动注入上下文，还是让模型主动 poll？
2. 后台命令需要权限检查吗？
3. cron 任务到期后，应该自动执行还是只生成 prompt？
4. 多个后台任务同时写文件时会有什么风险？

## Bonus Tasks

- 给后台任务增加取消功能。
- 保存后台任务日志到文件。
- 支持 cron 范围表达式，例如 `1-5`。
- 给 cron 任务增加 enabled/disabled 状态。

## 本章小结

你让 agent 从同步工具调用扩展到异步工作：

```text
慢任务 -> 后台运行
未来任务 -> cron 调度
完成结果 -> 稍后回到对话
```

下一章不再增加核心机制，而是把已有能力用于真实项目挑战。

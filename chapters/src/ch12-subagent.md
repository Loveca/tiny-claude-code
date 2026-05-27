# ch12: Subagent

> 子 agent 的价值不是更聪明，而是隔离上下文。

## 本章目标

当任务很大时，主 agent 不应该把所有细节都塞进自己的上下文。本章实现 `SubAgent` 和 `SubAgent` 工具，让主 agent 可以委派一个聚焦子任务，子 agent 使用独立消息历史完成工作，只把摘要返回给主 agent。

## 问题：不是所有探索都应该进入主上下文

复杂任务里经常会有旁路探索：搜索所有 TODO、调查某个失败测试、阅读一组不确定相关的文件。这些探索可能产生大量中间输出，但主 agent 最终只需要结论。

如果把所有探索都放进主上下文，会出现两个问题：

- 主线被中间细节淹没，后续决策成本变高。
- compact 时更难判断哪些信息属于当前主任务。

Subagent 的核心价值就是把这类探索隔离出去。

## 解决方案：子任务独立运行，父任务只收摘要

```text
Parent agent
   |
   | calls SubAgentTool(task)
   v
Child agent loop with fresh messages
   |
   | uses selected tools
   v
summary result
   |
   v
Parent receives one tool_result
```

父 agent 不需要读取子 agent 的完整 transcript。它只需要子任务结论、关键证据和建议下一步。

## 为什么需要 Subagent

Subagent 不是“再开一个更聪明的模型”，而是给某个子任务创建独立上下文。父 agent 可以把一个边界清楚的问题交给子 agent，子 agent 在自己的消息历史里探索，最后只把总结结果返回给父 agent。

这种设计解决的是上下文污染问题。比如父 agent 正在实现功能，同时需要调查一段测试失败原因；如果把所有探索输出都塞回父上下文，主线会被大量细节淹没。Subagent 让探索发生在旁路，父 agent 只接收结论、证据和建议动作。

边界也很重要：子 agent 不应该无限递归创建更多 agent，也不应该把完整子 transcript 原样灌回父上下文。本章的深度限制和摘要返回，就是为了保留隔离带来的收益。

## 工作原理

SubAgentTool 可以复用现有 `agent_loop`，但传入新的 messages 和受控工具集合：

```python
def execute(task):
    child_messages = [{"role": "user", "content": task}]
    result = agent_loop(
        messages=child_messages,
        tools=child_tools,
        max_turns=child_max_turns,
        depth=parent_depth + 1,
    )
    return summarize_child_result(result)
```

这里的关键不是代码多复杂，而是边界要明确：限制轮次、限制递归深度、控制可用工具、只返回摘要。

## 相对 ch11 的变化

| 组件 | ch11 | ch12 |
| --- | --- | --- |
| 任务拆分 | Todo 状态拆分 | 可委派子 agent 执行 |
| 上下文 | 单一消息历史 | 父子上下文隔离 |
| 返回结果 | 工具直接返回执行结果 | 子 agent 返回摘要 |
| 风险控制 | todo 校验 | max turns + recursion guard |

## 核心概念

`SubAgent` 做四件事：

1. 创建独立 `messages`。
2. 使用同一个 LLM client 和工具集合执行 `agent_loop`。
3. 限制最大轮数，避免子任务失控。
4. 禁止递归子 agent。

子 agent 会拿到一个专用 system prompt：

```text
You are a focused subagent...
```

它应该完成被委派的任务，然后返回简短结果。

## 递归保护

默认工具注册表会给主 agent 注册 `SubAgent` 工具。但子 agent 自己执行时，会从工具集合里移除 `SubAgent`，避免出现无限递归委派。

## 运行测试

```bash
python scripts/dev.py test --ch 12
```

测试覆盖：

- 子 agent 返回摘要
- 子 agent 触发最大轮数保护
- 递归子 agent 被拒绝
- `SubAgentTool` 能执行任务
- 子 agent 工具集合移除 `SubAgent`
- 默认 registry 在有 client 时包含 `SubAgent`

## 验收任务

让 agent 搜索项目中某类信息，例如：

```text
搜索项目中所有和 memory 相关的实现，并总结它们的职责。
```

预期主 agent 可以把搜索或总结委派给子 agent，主上下文只保留结果摘要。

## 思考题

1. 子 agent 应该共享主 agent 的全部上下文吗？
2. 子 agent 返回全文结果和返回摘要有什么取舍？
3. 为什么必须限制递归和最大轮数？

## 本章小结

ch12 引入了上下文隔离。主 agent 负责规划和整合，子 agent 负责局部探索或执行。

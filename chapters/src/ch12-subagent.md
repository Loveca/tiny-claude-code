# ch12: Subagent

> 有些探索会产生大量中间信息，主 agent 只需要结论。

## 本章目标

复杂任务中经常有旁路探索：搜索所有 TODO、调查一个失败测试、阅读一组可能相关的文件。这些动作会产生很多中间输出。如果全部塞进主 `messages`，上下文会膨胀，主线也会变乱。

本章实现 `SubAgent` 和 `SubAgentTool`：

```text
Main Agent
  |
  +-- SubAgent(task)
          |
          +-- 独立 messages
          +-- 独立工具调用
          +-- 返回摘要给 Main Agent
```

子 agent 做探索，主 agent 只接收总结。

## 先建立心智模型

### 子 agent 是隔离上下文，不是更聪明的模型

SubAgent 仍然使用同一个 agent loop 思想，只是它有自己的 messages。

```text
主上下文:
  用户目标
  子任务请求
  子任务摘要

子上下文:
  子任务说明
  搜索输出
  文件片段
  中间推理
```

这样主上下文不会被大量搜索细节污染。

### 子 agent 必须有限制

如果允许子 agent 再派生子 agent，很容易递归失控。本章限制：

- 子 agent 最多运行 30 轮
- 子 agent 不能再调用 SubAgentTool
- 返回主 agent 的只有摘要文本

```text
Main -> SubAgent -> tools
Main -> SubAgent -> SubAgent  不允许
```

## 工作流程

模型在主循环里请求：

```text
SubAgentTool.execute(task="Search all TODO comments and summarize")
```

工具内部：

```text
创建子 messages
  |
  v
移除 SubAgentTool 的工具注册表
  |
  v
调用 agent_loop(max_turns=30)
  |
  v
返回子 agent 最终摘要
```

主 agent 把摘要当成普通 tool_result，继续决策。

## 本章要实现什么

主要修改：

- [subagent.py](../../src/tiny_claude_code/subagent.py)
- [tools/__init__.py](../../src/tiny_claude_code/tools/__init__.py)

需要实现：

- `SubAgent.__init__`
- `spawn`
- `_without_subagent_tool`
- `SubAgentTool.__init__`
- `SubAgentTool.schema`
- `SubAgentTool.execute`
- 默认注册表在有 client 时包含 subagent 工具

## 实现路线

### 第一步：spawn 创建独立 messages

子 agent 的第一条消息可以是用户角色：

```python
{"role": "user", "content": task_description}
```

不要直接复用主 agent 的 messages；否则隔离就失效了。

### 第二步：移除递归工具

如果 registry 里有 `subagent`，子 agent 使用的工具集合要去掉它。

```text
child_registry = registry without "subagent"
```

可以复制注册表中的工具，也可以创建一个不包含 subagent 的默认注册表。

### 第三步：调用 agent_loop

传入子 messages、子 registry、同一个 client，并设置较小的 `max_turns`。

### 第四步：返回摘要

子 agent 的最终文本就是返回给主 agent 的工具结果。不要把子 messages 全量合并回主 messages。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 12
```

测试覆盖：

- spawn 会返回子 agent 摘要
- 超过 30 轮会被截断
- 递归 subagent 会被拒绝
- SubAgentTool 能执行任务
- 子 agent 工具集中不再包含 subagent
- 有 client 时默认注册表包含 subagent

## 验收任务

运行 agent：

```text
搜索项目中所有 TODO 注释并总结它们分布在哪里
```

理想行为：主 agent 派生子 agent 搜索，子 agent 返回汇总，主 agent 基于汇总回答。

## 常见错误

### 子 agent 复用主 messages

这样不会减少上下文，反而会污染主线。必须创建独立消息列表。

### 把子 agent 的完整历史合并回来

主 agent 只需要摘要。完整历史会抵消 subagent 的价值。

### 忘记禁用递归

子 agent 可以再派子 agent 时，很容易失控或耗尽上下文。

### 没有 max_turns

子任务也可能无限工具调用。子 agent 更需要严格轮数上限。

## 思考题

1. 什么任务适合派给子 agent？
2. 子 agent 返回摘要会丢失什么信息？
3. 子 agent 是否应该共享主 agent 的 memory？
4. 多个子 agent 并行执行时，需要哪些额外机制？

## Bonus Tasks

- 给 SubAgentTool 增加 `allowed_tools` 参数。
- 返回摘要时附带置信度。
- 保存子 agent transcript 到调试目录。
- 支持多个子 agent 并行搜索后合并摘要。

## 本章小结

你让 agent 能把旁路探索隔离出去：

```text
主 agent 保持任务主线
子 agent 承担局部调查
摘要回传，细节隔离
```

下一章会处理另一种隔离：让耗时命令在后台运行，不阻塞主对话。

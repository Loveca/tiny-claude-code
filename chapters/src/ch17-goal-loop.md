# ch17: Goal Loop

> 从“回答一个问题”升级到“自己跑完一件事”。

## 本章目标

前面的 `agent_loop` 有一个明确的结束条件：模型不再调用工具，就返回文本。这对一次对话是对的，但对一个目标不一定对。

以“让测试全部通过”为例，真实过程往往是：

```text
第 1 轮：读测试，发现断言错误
第 2 轮：改代码
第 3 轮：跑测试，还有 1 个失败
第 4 轮：继续改
第 5 轮：测试通过，报告结果
```

如果第 1 轮模型只回复了一句“我找到了失败的断言”，`agent_loop` 就结束了——它把“进度汇报”当成了“任务完成”。

本章在工具分发之上加一层 goal loop，补三个机制：

- **轮次预算**：一个目标最多花多少次模型调用；
- **显式完成信号**：只有调用 `GoalDone` 才算完成，文本不自动等于结束；
- **进度日志**：`GoalCheckpoint` 记录的要点会在每轮 continuation prompt 中重复，熬过上下文压缩。

完成后，主 agent 可以接到 `/goal 让 test suite 全绿` 这样的目标，自己一轮轮推进，直到完成或预算耗尽。

## 先建立心智模型

### 一次对话 vs 一个目标

| | `agent_loop`（ch01） | goal loop（本章） |
|---|---|---|
| 结束条件 | 模型不调用工具 | `GoalDone`、预算耗尽或空转 |
| 状态 | 只有 messages | messages + 目标状态、轮次、进度日志 |
| 单轮含义 | 用户的一次输入 | 目标推进的一步 |
| 文本回复 | 任务结束 | 进度汇报，继续跑 |
| 失败语义 | 抛异常 | `paused` / `failed` 可区分 |

一句话：`agent_loop` 管“这一轮怎么用工具”，goal loop 管“这件事什么时候算完”。

### 为什么完成必须显式声明

如果把“返回文本”当成完成，会产生两个问题：

1. 模型经常在中间回复“我先看看测试结果”，这句话也是文本；
2. 完成是一个可以被记录、审查、测试的结论，不应该依赖措辞。

所以完成是一个工具调用：

```text
assistant:  [tool_use: GoalDone] {"summary": "修复了 cart.py 的 off-by-one，测试全绿"}
tool_result: Goal marked complete: 修复了 cart.py 的 off-by-one，测试全绿
```

`GoalDone` 和普通工具走同一条链路：`PreToolUse` 权限检查、注册表分发、`PostToolUse` 日志。目标模式不会绕开 ch05 的安全边界。

### 为什么 checkpoint 要反复注入

长任务一定会撞上上下文预算。ch08/ch09 能腾出空间，但它们不知道哪些信息重要——压缩之后，模型可能忘了“已经试过方案 A，失败原因是 B”。

`GoalCheckpoint(note)` 是一份模型自己维护的短进度日志：

```text
GoalCheckpoint: 失败测试是 test_cart_total_rounding
GoalCheckpoint: 期望是四舍五入到两位小数，不是截断
GoalCheckpoint: cart.py:42 已改，等待验证
```

每轮的 continuation prompt 只带最近 3 条。它们很短，却能回答“我在哪、下一步是什么”，而且和 messages 是否被压缩无关。

### 预算与空转守卫

两个数字控制一次 run 的规模：

| 参数 | 作用 | 触顶后的状态 |
|---|---|---|
| `max_turns` | 最多调用多少次模型 | `paused`，原因 `turn budget exhausted` |
| `max_idle_turns` | 连续多少轮没有工具调用 | `paused`，原因 `no tool calls in the last N turns` |

预算是“花完了”，空转是“不干活”。两者都不是 `failed`：任务没完成，但过程和状态都还在，调用方可以把进度汇报给用户。`failed` 只留给模型调用抛异常这类真正的错误。

## 运行机制

```text
messages += 目标 prompt
loop:
  compact(messages)                     # ch08/ch09，按需
  response = client.chat(messages, tools)
  执行 response 里的工具                  # 包括 GoalDone / GoalCheckpoint
  if GoalDone 被调用:      -> done      # 追加 tool_result 后退出
  if 连续 N 轮没有工具:     -> paused
  if 轮次用尽:             -> paused
  追加 tool_result + continuation prompt
                         # 带剩余轮次和最近 3 条 checkpoint
```

每一轮只调用一次模型。这个“一轮 = 一次 chat”的约定让测试完全可复现：mock client 按顺序吐出预设响应，就能精确断言第几轮发生了什么。

## 本章要实现什么

- [goal.py](../../src/tiny_claude_code_ref/goal.py)：`Goal`、`GoalManager`、目标 prompt、轮次与空转控制
- [tools/goal.py](../../src/tiny_claude_code_ref/tools/goal.py)：`GoalDone` 和 `GoalCheckpoint`
- [tools/\_\_init\_\_.py](../../src/tiny_claude_code_ref/tools/__init__.py)：`create_default_registry(..., goal_manager=...)` 接线
- [cli.py](../../src/tiny_claude_code_ref/cli.py)：`/goal <objective>` 与 `/goal` 状态查询

注册表由调用方传给 `run()`，而不是由 manager 持有：注册表要先有 manager 才能创建 goal 工具，如果 manager 又反过来持有注册表就形成了循环依赖。CLI 用同一个注册表跑普通对话和 goal run，工具面完全一致。

## 实现路线

### 第一步：Goal 状态

```python
goal = Goal(objective="让测试全绿", max_turns=12)
goal.status       # active
goal.turns_used   # 已花轮次
goal.checkpoints  # ["失败测试是 ...", ...]
```

状态只有四个：`active`、`done`、`paused`、`failed`。不要在字符串里塞额外语义，原因放到 `reason`。

### 第二步：单轮循环

`run()` 的骨架就是“调用一次模型 → 执行工具 → 追加结果”：

```python
while goal.turns_used < goal.max_turns:
    response = self._chat(messages, schemas, system)
    goal.turns_used += 1
    messages.append({"role": "assistant", "content": response.content})
    tool_results, tool_calls = self._dispatch(registry, response)
    if goal.status == "done":
        messages.append({"role": "user", "content": tool_results})
        break
    ...
```

注意 `GoalDone` 是普通工具：它通过修改 manager 的当前 goal 来发出完成信号，循环在分发结束后检查状态。

### 第三步：continuation prompt

有工具结果的轮次，不能直接追加“纯文本 user 消息”——上一条 user 消息是 tool_result。可以把 continuation 作为一个 text block 追加到同一条 user 消息里：

```python
tool_results.append({"type": "text", "text": continuation})
messages.append({"role": "user", "content": tool_results})
```

continuation 至少包含剩余轮次和最近 checkpoint：

```text
Continue working toward the goal. Turns remaining: 7.
Progress so far:
- 失败测试是 test_cart_total_rounding
- cart.py:42 已改，等待验证
Call GoalCheckpoint to record progress, or GoalDone with a summary when finished.
```

### 第四步：空转与预算

统计“这一轮有没有 tool_use”。连续 `max_idle_turns` 轮没有，就暂停。预算耗尽则落在 while 的 else 分支——注意别把两条路径混成一个状态。

### 第五步：接线到 CLI

`/goal <objective>` 直接调用 `run()`，复用已有的 registry、hooks、context manager。`/goal` 不带参数时打印当前目标的状态和最近结果。目标 transcript 与普通对话在同一个 session 里，退出后用 `--resume` 还能看到全过程。

## 试一下

不花 API 费用，先看测试契约：

```bash
python scripts/dev.py test --ch 17 --ref
```

盯着这几种行为：

- `GoalDone` 让 run 在第 1 轮结束，messages 里不会出现 continuation；
- 第 2 次 chat 收到的最后一条消息里有 `Turns remaining: 1` 和 checkpoint 原文；
- 连续两次纯文本回复 → `paused`，原因是 `no tool calls`；
- `max_turns=2` 且每轮都有工具调用 → `paused`，原因是 `turn budget exhausted`；
- `PreToolUse` 返回拒绝文本时，`GoalDone` 不会生效。

接真实模型时：

```text
> /goal 让 tests 全绿，先跑测试再定位失败原因
...
Goal done after 6 turn(s).
Summary: 修复了 cart.py 的数量舍入，pytest -q 全部通过
```

## 测试覆盖

- 目标生命周期：空目标、重复启动、finish/checkpoint 的前置状态；
- 完成路径：`GoalDone` 结束循环、summary 写入结果；
- 轮次路径：预算耗尽与空转守卫分别暂停，原因可读；
- 进度路径：checkpoint 出现在 continuation prompt，轮次数字正确；
- 错误路径：模型异常 → `failed`；缺少 `GoalDone` 工具 → 直接拒绝运行；
- 安全边界：`PreToolUse` 拒绝进入 tool_result，`Stop` hook 只触发一次；
- 集成：默认注册表下真实写文件并完成；`/goal` 命令的输出格式。

## 验收任务

1. 用 `/goal` 修一个真实失败测试，观察第 1 轮是否只是“读文件”而不是“宣布完成”；
2. 把 `max_turns` 调到 2，确认状态是 `paused` 而不是报错；
3. 让模型在过程中调用 `GoalCheckpoint`，再手动 `/compact`，确认下一轮 continuation 里仍有这些要点。

## 常见错误

| 现象 | 原因 |
|---|---|
| goal 永远不结束 | 模型没有调用 `GoalDone`，或注册表里根本没有这个工具 |
| 第 1 轮就 done | 把“文本回复”误当成完成信号 |
| continuation 没出现 | 轮次已用尽（`has_more_turns` 为假），这是有意的 |
| 压缩后模型重复劳动 | checkpoint 写得太少，或只写了“继续加油”这种无信息内容 |
| 空转守卫误伤 | `max_idle_turns` 太小；模型在纯思考轮次里没有调用工具 |

## 思考题

1. 如果允许 paused 的 goal 原地恢复，哪些字段必须持久化？恢复时 continuation 应该怎么写？
2. `GoalDone` 由模型自己声明，模型可能“骗完成”。你会怎样加入一个独立的验收步骤？它应该复用哪些工具？
3. 预算按模型调用计数，而不是按 token 或按实际耗时。三种计量方式分别适合什么场景？
4. 现在一个 manager 同时只能跑一个 goal。支持并发 goal 需要改哪些状态？

## Bonus Tasks

- 把 goal 状态写入 `.tiny-claude-code/goals/<id>.json`，支持进程重启后 `/goal --resume`；
- 增加 `GoalBlocked(reason)` 工具：模型判断被外部依赖卡住时主动暂停，而不是把预算烧完；
- 在 `Stop` hook 里汇总 checkpoint，生成一份 markdown 进度报告；
- 比较 `agent_loop` 与 `GoalManager.run` 的代码：哪些逻辑重复了？哪些是目标模式独有的？

## 小结

goal loop 没有发明新的工具能力，它只是在正确的时机继续调用模型，并给“完成”一个可检验的定义。预算、显式完成、进度日志和空转守卫，是让自主循环可控的最小集合。

下一章 ch18 会把工具来源从“自己写插件”扩展到 MCP 客户端：同一套 `Tool` 接口，接上社区现成的工具服务。

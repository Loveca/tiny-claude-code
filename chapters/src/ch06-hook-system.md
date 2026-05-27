# ch06: Hook System

> 扩展逻辑挂在循环上，不写死在循环里。

## 本章目标

ch05 已经实现了权限检查。如果把权限、日志、停止事件、未来的上下文压缩都硬编码进 `agent_loop`，循环会迅速膨胀。本章引入 `HookSystem`，把扩展点抽象成事件。

当前实现支持：

- `UserPromptSubmit`
- `PreToolUse`
- `PostToolUse`
- `Stop`

其中 `PreToolUse` 返回非 `None` 会短路，通常用于拒绝工具调用。

## 问题：主循环不能承受所有横切逻辑

ch05 里权限已经能工作，但如果直接把权限、日志、审计、通知、压缩、统计都塞进 `agent_loop`，主循环会越来越难读。agent loop 最重要的职责是维持模型和工具之间的往返协议，它不应该知道每一种附加能力的细节。

可以把这类逻辑理解成“围绕循环发生”的事情：

```text
User prompt submit
        |
        v
    agent loop
        |
  before tool use  -> permission / audit
        |
  after tool use   -> log / metrics / notification
        |
        v
Stop
```

这些点不是业务工具本身，却又确实需要参与执行流程。Hook 系统就是给它们一个稳定入口。

## 解决方案：把生命周期事件显式化

本章把循环中的关键位置命名为事件，并允许外部 callback 注册到事件上。agent loop 只负责触发事件，不负责知道事件背后有多少逻辑。

```python
hooks.trigger("UserPromptSubmit", prompt=prompt)
denial = hooks.trigger("PreToolUse", tool_name=name, tool_input=input)
result = registry.dispatch(name, input)
hooks.trigger("PostToolUse", tool_name=name, result=result)
hooks.trigger("Stop", messages=messages, response=final_text)
```

这带来一个重要收益：新增机制时优先问“它应该挂在哪个生命周期点”，而不是“我要往 agent.py 哪一段插代码”。

## 为什么需要 Hook

Agent loop 应该保持稳定：接收消息、调用模型、解析 tool_use、执行工具、回填结果。可真实产品里总会有额外需求，例如执行前审计、执行后记录、命令完成提醒、失败时收集诊断。如果每增加一个需求就改主循环，循环会很快变成难以推理的巨型函数。

Hook 的价值是把这些横切逻辑挂在生命周期事件上。本章只实现四个事件：工具执行前、工具执行后、agent turn 开始、agent turn 结束。它们覆盖了最小 agent 的关键边界，也足够展示扩展点设计的基本形态。

需要注意的是，Hook 不是权限系统的替代品。权限是强制安全边界，Hook 是扩展机制；Hook 可以记录、提示、短路一部分流程，但不能绕过 `deny` 这样的硬规则。这个区分能避免把“可扩展”做成“任何插件都能破坏核心不变量”。

本章的 non-`None` 短路返回是一种常见设计：普通 Hook 返回 `None` 表示继续执行；返回具体结果表示它接管了这一步。这样扩展能力可以被显式表达，而不是靠修改全局状态暗中影响流程。

## Hook 规则

hook 有两个关键行为：

- 按 priority 从高到低执行。
- 任一 callback 返回非 `None`，事件立即短路并返回该值。

这让权限系统可以成为普通 hook：

```python
hooks.register("PreToolUse", permissions.as_hook, priority=100)
```

也让日志 hook 不影响主流程：

```python
hooks.register("PostToolUse", tool_log.post_tool_use)
hooks.register("Stop", stop_log.stop)
```

## 工作原理

HookSystem 的核心是一个按事件分组的 callback 列表。注册时保存优先级，触发时排序执行：

```python
class HookSystem:
    def register(self, event, callback, priority=0):
        self._hooks[event].append((priority, callback))

    def trigger(self, event, **payload):
        callbacks = sorted(self._hooks[event], reverse=True)
        for _, callback in callbacks:
            result = callback(**payload)
            if result is not None:
                return result
        return None
```

`PreToolUse` 的短路语义让权限检查可以阻止工具执行；`PostToolUse` 和 `Stop` 通常只做观察和记录，所以返回 `None`。同一个机制在不同事件上的语义不同，这是 Hook 设计里最容易忽略的点。

## 相对 ch05 的变化

| 组件 | ch05 | ch06 |
| --- | --- | --- |
| 权限接入 | agent loop 直接调用权限逻辑 | 权限注册成 `PreToolUse` hook |
| 扩展方式 | 修改主循环 | 注册事件 callback |
| 执行顺序 | 固定代码顺序 | priority 控制顺序 |
| 短路能力 | 权限专用 | 任意 hook 可按事件语义短路 |

## Agent Loop 如何使用

工具执行前：

```python
denial = hooks.trigger("PreToolUse", tool_name=name, tool_input=input)
if denial is not None:
    output = str(denial)
else:
    output = registry.dispatch(name, input)
```

工具执行后：

```python
hooks.trigger("PostToolUse", tool_name=name, tool_input=input, result=output)
```

结束时：

```python
hooks.trigger("Stop", messages=messages, response=final_text)
```

## 实现路线

### 第一步：实现事件到回调的映射

HookSystem 本质上是 `event -> callbacks`。先让注册和触发跑通，再考虑优先级和短路。

### 第二步：加入 priority

权限类 hook 通常要比日志类 hook 更早执行。priority 表达的是扩展点之间的依赖关系，不只是排序装饰。

### 第三步：把短路写进 trigger

短路语义应该由 HookSystem 统一处理，而不是散落在 agent loop 里。这样主循环不需要知道哪个 hook 会阻止执行。

### 第四步：把权限迁移成 hook

迁移完成后，agent loop 不再直接调用权限规则。它只触发 `PreToolUse`，然后根据返回值决定是否继续 dispatch。

## 测试讲解

本章测试要分两层：HookSystem 自身是否正确，以及 agent loop 是否在正确的生命周期点触发事件。前者测 priority、短路和空 hook；后者测工具执行前后与最终停止事件。

最关键的测试是：当 `PreToolUse` 返回拒绝结果时，真实工具 handler 没有被调用。这能证明 Hook 不只是记录日志，而是真的参与了控制流。

## 常见错误

### Hook payload 暴露太多内部对象

Hook 只应该拿到事件需要的信息。把整个 agent 内部状态都暴露出去，会让扩展点反过来绑死主循环结构。

### 所有事件都允许短路

`PreToolUse` 短路合理；`PostToolUse` 通常只是观察。短路语义必须和事件含义匹配。

### priority 方向不清楚

项目必须明确“数字越大越早”还是“数字越小越早”，并用测试固定下来。

## 运行测试

```bash
python scripts/dev.py test --ch 06
```

测试覆盖：

- 多个 hook 按优先级执行
- `PreToolUse` 能阻止工具执行
- `PostToolUse` 能收到工具名和结果
- `Stop` 在最终响应时触发
- 没有 hook 时正常返回 `None`

## 验收任务

行为应与 ch05 相同：权限仍然生效。但结构上，权限已经从主循环硬编码变成了 hook。

## 思考题

1. 哪些逻辑适合做 hook，哪些不适合？
2. `PreToolUse` 短路后，是否还应该触发 `PostToolUse`？
3. priority 应该越大越早执行，还是越小越早执行？

## 本章小结

Hook 的价值不是功能多，而是让主循环保持清晰。后续章节可以继续加机制，但 agent loop 的形状不用不断重写。

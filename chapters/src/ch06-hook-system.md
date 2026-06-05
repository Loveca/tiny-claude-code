# ch06: Hook System

> 不要把所有机制都塞进 agent loop；让循环在关键节点发出事件。

## 本章目标

ch05 把权限检查放到了工具执行前。这个位置很重要，但如果继续把日志、权限、统计、会话保存、通知都写进 agent loop，核心循环会再次变得臃肿。

本章实现 `HookSystem`。agent loop 在关键节点触发事件，外部模块注册回调来扩展行为。

```text
UserPromptSubmit -> 用户提交输入后
PreToolUse       -> 工具执行前
PostToolUse      -> 工具执行后
Stop             -> agent 本轮结束时
```

权限系统会变成 `PreToolUse` hook。工具日志会变成 `PostToolUse` hook。结束日志会变成 `Stop` hook。

## 先建立心智模型

### Hook 是“在这里插一段逻辑”

agent loop 的主路径仍然是：

```text
call LLM -> maybe tool_use -> dispatch tool -> append result -> repeat
```

hook 不改变主路径的含义，只是在节点旁边挂扩展逻辑。

```text
              +-------------------+
tool_use ---> | trigger PreToolUse | -- denial? --> skip tool
              +-------------------+
                       |
                       v
                 dispatch tool
                       |
                       v
              +--------------------+
              | trigger PostToolUse |
              +--------------------+
```

### 有些 hook 可以短路

`PreToolUse` 和其他事件不同。权限检查如果返回拒绝原因，工具就不能执行。所以 hook system 需要支持短路：

```text
callback returns None     -> 继续下一个 hook
callback returns "denied" -> 停止，返回这个结果
```

这让权限 hook 可以拦截工具调用。

## HookSystem 要提供什么

最小接口只有两个：

```python
hooks.register(event, callback, priority=0)
hooks.trigger(event, *args)
```

priority 用来控制执行顺序。数字越小越早执行，或者你也可以选择数字越大越早执行；关键是测试和实现保持一致。

```text
PreToolUse hooks:
  priority 0  -> permission
  priority 10 -> audit log
```

如果前面的 permission 返回拒绝结果，后面的 hook 可以不用执行。

## 本章要实现什么

主要修改：

- [hooks.py](../../src/tiny_claude_code/hooks.py)
- [permissions.py](../../src/tiny_claude_code/permissions.py)
- [agent.py](../../src/tiny_claude_code/agent.py)

需要实现：

- `HookSystem.__init__`
- `register`
- `trigger`
- `ToolLogHook.post_tool_use`
- `StopLogHook.stop`
- 权限管理器的 `as_hook`
- agent loop 中的 hook 触发点

## 实现路线

### 第一步：保存事件到回调列表

内部结构可以是：

```python
self._hooks = {
    "PreToolUse": [(priority, callback), ...],
}
```

注册后按 priority 排序。

### 第二步：实现 trigger 短路

遍历回调：

```text
for callback in callbacks:
    result = callback(*args)
    if result is not None:
        return result
return None
```

这个规则简单但非常有用：普通日志 hook 返回 None，权限拒绝 hook 返回文本。

### 第三步：接入 agent loop

在工具执行前：

```text
denial = hooks.trigger("PreToolUse", name, input)
if denial:
    result = denial
else:
    result = registry.dispatch(...)
```

工具执行后：

```text
hooks.trigger("PostToolUse", name, input, result)
```

最终回复前：

```text
hooks.trigger("Stop", final_text)
```

### 第四步：把权限变成 hook

`PermissionManager.as_hook()` 返回一个函数。这个函数接收工具名和输入，内部调用 `check`，如果拒绝就返回拒绝文本，否则返回 None。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 06
```

测试覆盖：

- 多个 hook 按 priority 执行
- `PreToolUse` 返回拒绝时，工具不会执行
- `PostToolUse` 能收到工具名和结果
- `Stop` 在最终回复时触发
- 没有注册 hook 时返回 None，不影响主流程

## 验收任务

运行 agent，并尝试一个会触发权限检查的操作：

```text
读取 ../secret.txt
```

行为应该和 ch05 一样，但内部结构更干净：agent loop 触发 `PreToolUse`，权限 hook 决定拒绝。

## 常见错误

### hook 返回值被忽略

`PreToolUse` 的返回值必须能阻止工具执行。否则权限 hook 只是日志，没有安全意义。

### 所有 hook 都短路

短路规则是“返回非 None 才停止”。日志 hook 应该返回 None，避免拦截后续逻辑。

### priority 排序不稳定

测试会检查执行顺序。注册后要排序，而不是依赖 dict 顺序。

### agent loop 仍然直接调用 PermissionManager

本章目标是解耦。权限应该通过 hook 进入 loop。

## 思考题

1. hook 和直接函数调用相比，优点和代价是什么？
2. 哪些事件应该允许短路？哪些不应该？
3. 如果两个 hook 都想修改工具输入，应该如何设计？
4. hook 出错时应该终止 agent 还是记录错误后继续？

## Bonus Tasks

- 支持移除 hook。
- 给 hook 增加名称，方便日志和调试。
- 记录每个 hook 的耗时。
- 区分 `PreToolUse` 的 deny 和 transform 两种返回值。

## 本章小结

你把 agent loop 从“所有机制的堆放处”变成了事件源：

```text
核心循环保持简单
扩展逻辑挂在事件上
权限、日志、保存都可以独立演进
```

下一章会处理另一个真实运行中一定会遇到的问题：LLM API 和工具调用会失败，agent 需要恢复能力。

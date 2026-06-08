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

## 你有没有发现这个问题

在前面几章里，每次输入一个需要工具的任务，比如"帮我看看这个目录里有什么文件"——CLI 会陷入一段沉默。你不知道 agent 在做什么，跑了什么命令，有没有卡住，还是正在等 API。只能盯着光标干等，直到最终回复突然出现。

Claude Code 不是这样的。它会实时打印每一步：

```text
> 帮我看看 examples/ 目录里有什么文件

  ⚙ bash  ls examples/
  exit_code: 0
  simple-bug/
  buggy-python-project/
  ...

examples/ 目录下有三个子目录：...
```

这种可见性不是靠特殊 API 实现的，**用 hook 就能做到**。

`PreToolUse` 在工具执行前触发——这时打印工具名和参数，用户立刻知道 agent 要做什么，不用等结果。

`PostToolUse` 在工具执行后触发——这时打印结果的前几行，用户看到实际输出，不再是黑盒。

本章要实现的 `ProgressHook` 就负责这件事。

## 本章要实现什么

主要修改：

- [hooks.py](../../src/tiny_claude_code/hooks.py)
- [permissions.py](../../src/tiny_claude_code/permissions.py)
- [agent.py](../../src/tiny_claude_code/agent.py)
- [cli.py](../../src/tiny_claude_code/cli.py)

需要实现：

- `HookSystem.__init__`
- `register`
- `trigger`
- `ToolLogHook.post_tool_use`
- `StopLogHook.stop`
- `ProgressHook.pre_tool_use`
- `ProgressHook.post_tool_use`
- 权限管理器的 `as_hook`
- agent loop 中的 hook 触发点
- cli.py 中注册 `ProgressHook`

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

### 第五步：实现 ProgressHook

`ProgressHook` 有两个方法，分别挂在 `PreToolUse` 和 `PostToolUse` 上。

**pre_tool_use**：工具执行前打印工具名和最有意义的那个参数。不同工具的关键参数不同：

```text
bash    -> command
read    -> path
write   -> path
search  -> pattern
```

可以用 `tool_input.get("command") or tool_input.get("path") or tool_input.get("pattern") or ""` 来取。如果参数太长就截断到 60 字符。

```python
detail = tool_input.get("command") or tool_input.get("path") or tool_input.get("pattern") or ""
if len(detail) > 60:
    detail = detail[:60] + "…"
print(f"  ⚙ {tool_name}  {detail}", flush=True)
```

**post_tool_use**：工具执行后打印结果的前 `PREVIEW_LINES`（默认 5）行。超出的部分显示 `… (N more lines)`。

```python
lines = result.splitlines()
preview = "\n    ".join(lines[:self.PREVIEW_LINES])
suffix = f"\n    … ({len(lines) - self.PREVIEW_LINES} more lines)" if len(lines) > self.PREVIEW_LINES else ""
print(f"    {preview}{suffix}", flush=True)
```

**在 cli.py 中注册**：

```python
progress = ProgressHook()
hooks.register("PreToolUse", progress.pre_tool_use)
hooks.register("PostToolUse", progress.post_tool_use)
```

注意 `ProgressHook` 的两个方法都应该返回 `None`，不能短路后续 hook。

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

### 第一步：运行自动测试

```bash
python scripts/dev.py test --ch 06
```

期望输出：

```text
N passed in ...s
```

### 第二步：验证 ProgressHook 的实时输出

启动 agent：

```bash
python scripts/dev.py run
```

输入一个会触发多个工具调用的任务：

```text
列出 examples/ 目录里有哪些文件，然后读取 examples/simple-bug/calculator.py 的内容
```

期望在最终回复出现之前，终端里能实时看到每个工具的进度，例如：

```text
  ⚙ bash  ls examples/
    exit_code: 0
    stdout:
    buggy-python-project/
    simple-bug/
    … (2 more lines)
  ⚙ read  examples/simple-bug/calculator.py
    def add(a, b):
        return a + b
    … (3 more lines)

examples/ 目录下有两个子目录：...
```

如果工具调用开始执行就能看到 `⚙` 那一行，说明 `PreToolUse` 正常工作；如果工具执行完立刻看到结果预览，说明 `PostToolUse` 正常工作。

### 第三步：验证权限 hook 仍然有效

输入：

```text
读取 ../secret.txt
```

期望 agent 拒绝执行，行为和 ch05 一致。但此时内部结构更干净：agent loop 只触发事件，权限逻辑在 hook 里独立运行。

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

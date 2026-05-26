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

# ch05: Permission System

> Agent 有能力做一件事，不代表它应该直接做。

## 本章目标

前四章已经让 agent 能运行命令、读文件、写文件、搜索代码。能力足够以后，新的问题立刻出现：模型可能请求危险操作。本章实现三层权限检查，让工具执行前先经过明确边界。

当前实现的 `PermissionManager` 会作为 `PreToolUse` hook 注册到 agent loop 中。这样权限逻辑可以拦截工具调用，但不用散落到每个工具内部。

## 三道闸门

权限检查分成三类：

1. 硬拒绝：永远不允许，例如 `rm -rf /`、fork bomb、磁盘破坏命令。
2. 规则检查：根据上下文判断，例如路径越界、破坏性 shell 命令。
3. 用户审批：对可能危险但不一定错误的操作询问用户。

当前版本的语义：

- 路径越界直接拒绝。
- deny list 命中直接拒绝。
- `rm temp.txt` 这类破坏性 shell 命令会询问用户。
- 用户输入 `always` 后，同一工具和同一参数下次自动通过。

## 接入方式

`PermissionManager` 暴露 `as_hook`：

```python
permissions = PermissionManager(workspace=workspace)
hooks.register("PreToolUse", permissions.as_hook, priority=100)
```

hook 返回 `None` 表示允许执行；返回字符串表示拒绝原因。agent loop 会把拒绝原因作为 `tool_result` 写回模型。

## 运行测试

```bash
python scripts/dev.py test --ch 05
```

测试覆盖：

- deny list 直接拒绝
- 路径越界直接拒绝
- 普通操作不询问
- 规则命中后可以批准
- 规则命中后可以拒绝
- `always` 记忆同参数授权

## 验收任务

运行：

```bash
python scripts/dev.py run
```

输入：

```text
读取 ../secret.txt
```

期望：工具调用被拒绝，agent 收到权限拒绝结果并向用户说明。

## 思考题

1. 为什么路径越界应该直接拒绝，而不是询问用户？
2. deny list 为什么不能作为完整安全机制？
3. `always` 应该记住参数，还是只记住工具名？

## 本章小结

Part 1 让 agent 能动手，ch05 开始给它边界。权限不是为了削弱 agent，而是让它能在真实项目里更可靠地行动。

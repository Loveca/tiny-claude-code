# ch05: Permission System

> Agent 有能力做一件事，不代表它应该直接做。

## 本章目标

前四章已经让 agent 能运行命令、读文件、写文件、搜索代码。能力足够以后，新的问题立刻出现：模型可能请求危险操作。本章实现三层权限检查，让工具执行前先经过明确边界。

当前实现的 `PermissionManager` 会作为 `PreToolUse` hook 注册到 agent loop 中。这样权限逻辑可以拦截工具调用，但不用散落到每个工具内部。

## 问题：能力扩大以后，风险也扩大

Part 1 的目标是让 agent 能动手。它现在可以跑命令、读文件、写文件、搜索代码，这些都是 coding agent 必须具备的能力。但能力一旦接入真实文件系统，就不再只是“生成文本是否正确”的问题，而是“错误动作会不会造成真实损失”的问题。

一个典型失败路径是这样的：

```text
+--------+       +-----------+       +----------------+
|  LLM   | ----> | tool_use  | ----> | Shell / Write  |
+--------+       +-----------+       +----------------+
     模型认为这是合理动作          本地环境真实执行副作用
```

如果中间没有权限层，模型的一次误判就会直接变成文件删除、越界写入或危险命令。提示词可以降低概率，但不能成为安全边界；安全边界必须由执行工具的 harness 控制。

## 解决方案：把工具执行变成可裁决动作

本章在工具执行前插入一个裁决点。agent loop 仍然负责解析 `tool_use`，但在调用 `registry.dispatch(...)` 之前，先把工具名和参数交给 `PermissionManager`。

```text
tool_use
   |
   v
[PermissionManager]
   | allow -> registry.dispatch(...)
   | ask   -> user confirms, then dispatch or deny
   | deny  -> return tool_result with denial reason
```

这样模型不会失去行动能力，但每次行动都会先经过本地策略检查。权限系统返回的拒绝原因仍然会作为 `tool_result` 写回模型，让模型可以换一种安全做法继续完成任务。

## 为什么权限必须在执行前判断

到 ch04 为止，模型已经可以调用工具。问题也随之出现：模型可能请求删除文件、写入敏感路径，或者运行带副作用的命令。真实 agent 不能只在 system prompt 里写“请谨慎操作”，因为 prompt 是给模型看的约束，真正的安全边界必须由本地 harness 在执行前强制检查。

权限系统的核心是把“模型想做什么”和“程序允许做什么”拆开。模型产出 tool_use，agent loop 准备执行，PermissionPolicy 在工具 handler 之前做裁决。这个位置很关键：太早时还不知道具体参数，太晚时副作用已经发生。

本章实现的 `allow`、`ask`、`deny` 是最小但完整的三态模型：

- `allow` 表示这类动作可以直接执行，例如只读文件。
- `ask` 表示动作不一定危险，但需要用户确认，例如写文件或运行命令。
- `deny` 表示无论模型怎么解释都不执行，例如越过工作区写入系统路径。

生产级系统会有更复杂的规则来源，例如项目配置、用户配置、企业策略、工具自身声明和一次性授权。但无论规则多复杂，原则都一样：权限结果必须在代码里落地，不能把“要不要执行”交给模型自判。

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

## 工作原理

权限检查是一个短路管线。越确定危险的规则越靠前，越需要人类判断的规则越靠后：

```python
def check(tool_name, tool_input):
    denial = check_hard_deny(tool_name, tool_input)
    if denial:
        return PermissionDecision("deny", denial)

    denial = check_workspace_boundary(tool_name, tool_input)
    if denial:
        return PermissionDecision("deny", denial)

    if matches_remembered_allow(tool_name, tool_input):
        return PermissionDecision("allow")

    if needs_user_confirmation(tool_name, tool_input):
        return ask_user(tool_name, tool_input)

    return PermissionDecision("allow")
```

这里有两个设计点需要记住。第一，`deny` 必须短路，不能再进入用户确认，因为硬拒绝代表程序已经知道该动作越过边界。第二，`always` 不能只记工具名，否则一次授权 `write_file` 可能会意外覆盖所有写入操作；它至少要绑定工具名和参数摘要。

## 相对 ch04 的变化

| 组件 | ch04 | ch05 |
| --- | --- | --- |
| 工具执行 | registry 直接 dispatch | dispatch 前先经过权限检查 |
| 安全边界 | 工具内部的基础校验 | 统一的 PermissionManager |
| 用户参与 | 无 | 危险但可接受的动作会询问用户 |
| 失败回填 | 未知工具或执行失败 | 权限拒绝也作为 tool_result 回填 |

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

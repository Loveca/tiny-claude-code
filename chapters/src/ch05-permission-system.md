# ch05: Permission System

> Agent 有能力做一件事，不代表它应该直接做。

## 本章目标

前四章让 agent 能运行命令、读文件、写文件、搜索代码。能力扩大以后，风险也立刻扩大：模型可能请求删除文件、越界读取、运行破坏性命令。

本章实现 `PermissionManager`，在工具真正执行前插入权限裁决。

```text
tool_use
  |
  v
PermissionManager
  |
  +-- allow -> 执行工具
  +-- ask   -> 用户确认后再决定
  +-- deny  -> 不执行，把拒绝原因回传模型
```

权限不是提示词。提示词是给模型看的，权限是本地 harness 强制执行的边界。

## 先建立心智模型

### 风险来自真实副作用

模型回复错一句话，通常只是答案不准。工具执行错一步，可能会改坏真实文件。

```text
LLM 判断
  |
  v
tool_use {"name": "bash", "input": {"command": "rm important.py"}}
  |
  v
如果没有权限层，本地环境直接执行
```

所以权限系统必须站在工具执行之前。太早时不知道具体参数；太晚时副作用已经发生。

### 权限结果应该回到模型

拒绝工具不等于终止任务。比如模型想读取 `../secret.txt`，权限系统拒绝后，可以把原因作为 `tool_result` 写回：

```text
Denied: path escapes workspace
```

模型看到后可以换一种安全路径继续完成任务。

## 三道闸门

本章实现三层检查：

```text
          +-----------------+
tool_use ->| 1. hard deny    | 命中直接拒绝
          +-----------------+
                    |
                    v
          +-----------------+
          | 2. rules        | 路径、危险命令等规则
          +-----------------+
                    |
                    v
          +-----------------+
          | 3. user prompt  | 需要人工确认
          +-----------------+
```

### Gate 1: 硬拒绝

硬拒绝用于永远不应该执行的动作，例如：

- `rm -rf /`
- fork bomb
- 明显破坏系统的命令

这类操作不需要询问用户，直接拒绝。

### Gate 2: 规则检查

规则检查根据工具参数判断。例如：

- 文件路径是否逃出 workspace
- shell 命令是否像删除操作
- 写入路径是否合理

路径越界应该直接拒绝，因为 workspace 是项目边界。

### Gate 3: 用户审批

有些动作不是绝对危险，但需要确认。例如删除项目内的临时文件、运行某些带副作用的命令。

用户可以回答：

- `y`：本次允许
- `n`：本次拒绝
- `always`：同一工具和同一参数下次自动允许

## 本章要实现什么

主要修改 [permissions.py](../../src/tiny_claude_code/permissions.py)，并让 agent loop 在工具执行前调用它。

需要实现：

- `PermissionDecision`：表示 `allow`、`ask`、`deny`
- `PermissionManager.check(...)`
- `PermissionManager.as_hook(...)`
- `_check_deny_list`
- `_check_rules`
- `_path_escapes_workspace`
- `_prompt_user`
- `_remember_key`

当前仓库后续会用 hook 系统承载权限；本章可以先把它理解成“工具执行前的拦截器”。

## 实现路线

### 第一步：定义返回值

不要只返回 `True` / `False`。权限判断需要说明原因：

```text
allow: 可以执行
deny + reason: 不执行，并把 reason 回给模型
```

### 第二步：实现 hard deny

检查 shell command 中是否包含危险模式。这里不追求完美，只做教学级防线。重点是理解：某些模式应该无条件拒绝。

### 第三步：实现路径越界

对 `read`、`write`、`search` 这类工具，检查参数中的路径。目标路径 resolve 后必须仍在 workspace 内。

### 第四步：实现用户确认和 always

`always` 需要记住“工具名 + 参数”的组合。可以把参数转成稳定 JSON 字符串作为 key。

```text
("bash", {"command": "rm temp.txt"}) -> remembered allow
```

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 05
```

测试覆盖：

- deny list 会拦截危险 shell 命令
- 路径越界会拒绝
- 正常只读操作可以直接通过
- 需要确认的动作可以被批准
- 需要确认的动作可以被拒绝
- `always` 会让同一参数下次自动通过

## 验收任务

运行 agent 后输入：

```text
读取 ../secret.txt
```

期望行为：工具不执行，模型收到权限拒绝原因并解释无法越界读取。

再输入：

```text
删除 temp.txt
```

如果权限规则把它视为需要确认，CLI 应该询问用户，而不是直接执行。

## 常见错误

### 让模型自己判断权限

模型可以建议，但不能裁决本地副作用。权限必须在 Python 代码中执行。

### 拒绝后直接退出 agent loop

拒绝原因应该作为 `tool_result` 回传，让模型有机会换方案。

### always 记得太宽

`always` 只能记住同一工具和同一参数。不能因为用户批准过一次 `bash`，就放行所有 bash 命令。

### 路径越界只检查字符串

仍然要用 `Path.resolve()`，否则 `../`、软链接、Windows 路径都容易绕过。

## 思考题

1. 权限系统为什么必须在工具执行前运行？
2. `deny` 和 `ask` 的边界应该怎么划分？
3. 如果模型被拒绝后反复请求同一危险操作，agent loop 应该如何处理？
4. 项目级权限配置应该放在哪里？

## Bonus Tasks

- 支持 `.tiny-claude-code/permissions.yaml`。
- 给不同工具设置默认策略。
- 记录每次权限拒绝到日志。
- 给用户确认提示显示更清晰的风险摘要。

## 本章小结

你给 agent 加上了第一层安全边界：

```text
模型可以请求动作
Harness 决定是否执行
拒绝原因回传模型
```

下一章会把权限检查接入更通用的 hook 系统，让“工具执行前后发生什么”不再硬编码在 agent loop 里。

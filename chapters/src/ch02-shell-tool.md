# ch02: Shell Tool

> 第一个工具，让 agent 从“能对话”变成“能动手”。

## 本章目标

ch01 已经搭好了 agent loop：模型可以回复文本，也可以发出 `tool_use`。但当时还没有真实工具，循环只是一个协议骨架。

本章要实现第一个真实工具：`bash`。模型请求运行命令，harness 在当前 workspace 中执行它，再把 `exit_code`、`stdout`、`stderr` 写回 `messages`。完成以后，agent 才能真正观察项目状态，例如列目录、运行脚本、跑测试。

```text
用户目标
  |
  v
LLM: 我要调用 bash
  |
  v
ShellTool.execute(command)
  |
  v
exit_code + stdout + stderr
  |
  v
tool_result 写回 messages
```

本章只做最小安全检查。完整的权限系统会在 ch05 加入。

## 先建立心智模型

### 工具不是让模型执行代码

模型不会拿到 Python 函数，也不会直接访问你的终端。模型只能看到工具的 schema，并生成一个结构化请求。

```text
schema  -> 给模型看：这个工具叫什么，需要什么参数
handler -> 本地执行：harness 根据模型请求调用真实代码
```

`ShellTool.schema` 告诉模型：

```python
{
    "name": "bash",
    "description": "Run a shell command in the current workspace.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "timeout": {"type": "integer"},
        },
        "required": ["command"],
    },
}
```

模型看到 schema 后，可能产生这样的请求：

```text
ToolUseBlock(name="bash", input={"command": "python -m pytest"})
```

真正运行命令的是本地的 `ShellTool.execute(...)`。这个边界很重要：模型负责决定“想做什么”，harness 负责决定“能不能做、怎么做、结果怎么回传”。

### 为什么第一个工具选 Shell

Shell 是最通用的开发动作入口。很多 coding agent 任务最终都会落到命令：

- `dir` / `ls`：看项目结构
- `python app.py`：运行程序
- `pytest`：验证修复
- `git status`：查看工作区

它的优点是覆盖面广；缺点是危险、输出松散、容易过长。所以本章的 ShellTool 必须至少做到三件事：

1. 绑定 workspace，避免命令在不确定目录里运行。
2. 捕获 stdout、stderr 和 exit code，避免丢失失败信息。
3. 限制命令长度、超时时间和输出长度，避免循环被无意义内容撑爆。

## 命令结果要怎样返回

一个命令不是只有“输出文本”。例如测试失败时，关键信息可能在 stderr；命令没有输出但 exit code 是 7，也表示失败。

推荐返回格式保持简单、可读：

```text
exit_code: 0
stdout:
hello
stderr:

```

这样模型可以判断：

- `exit_code: 0` 表示命令成功
- 非 0 exit code 表示命令失败
- stdout / stderr 分别保留普通输出和错误输出
- 输出过长时出现 `[truncated]`，提醒模型结果不完整

## 本章要实现什么

主要修改 [shell.py](../../src/tiny_claude_code/tools/shell.py)。

需要实现：

- `__init__`：保存 workspace、最大命令长度、最大输出长度。
- `schema`：返回名为 `bash` 的工具 schema。
- `validate_command`：拒绝空命令和过长命令。
- `execute`：用 `subprocess.run` 执行命令。
- `_truncate`：截断过长输出并追加 `[truncated]`。

`execute` 的核心形状是：

```python
result = subprocess.run(
    command,
    shell=True,
    cwd=self.workspace,
    capture_output=True,
    text=True,
    timeout=timeout,
)
```

注意，这里用了 `shell=True`。它让命令写法更接近用户平时使用的终端，但也带来更多风险。本章只做基础限制；ch05 会把权限检查接到工具执行前。

## 实现路线

### 第一步：让工具知道工作目录

如果没有传入 workspace，就使用当前目录：

```python
self.workspace = Path(workspace or os.getcwd()).resolve()
```

所有命令都在这个目录里执行。这样用户问“当前项目”，模型看到的项目和命令操作的项目是一致的。

### 第二步：先校验再执行

不要等到 `subprocess.run` 才发现命令为空。可以让 `validate_command` 返回错误文本或 `None`：

```text
command.strip() == "" -> reject
len(command) > max_command_length -> reject
otherwise -> allow
```

### 第三步：捕获失败而不是崩溃

命令超时要捕获 `subprocess.TimeoutExpired`，返回类似 `Command timed out` 的文本。非零 exit code 不需要抛异常，因为 `subprocess.run` 默认不会抛；把 exit code 写回结果即可。

### 第四步：截断输出

Shell 输出可能非常长。ch08 才会正式做上下文预算，但工具层现在就应该控制单次输出大小。

```text
原始输出超过 max_output_chars
  |
  v
保留前半段 + "\n[truncated]"
```

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 02
```

测试会检查这些行为：

- schema 名称是 `bash`，并要求 `command`
- 正常命令能返回 stdout
- 命令在绑定 workspace 中运行
- 非零 exit code 会保留
- 空命令被拒绝
- 过长命令被拒绝
- 超时命令被截断执行并返回错误
- 长输出会出现 `[truncated]`

如果第一条测试失败，先看 schema；如果后续测试失败，再看 `execute` 的返回格式和异常处理。

## 验收任务

配置好 `.env` 后运行：

```bash
python scripts/dev.py run
```

输入：

```text
列出当前目录文件，告诉我这是一个什么项目
```

期望行为：模型调用 `bash` 查看目录，再根据命令输出总结项目。此时 agent 还不会精准读写文件，但已经能用 shell 观察环境。

## 常见错误

### 只返回 stdout

这样会丢失 stderr 和 exit code。测试失败、命令不存在、脚本报错时，模型会缺少判断依据。

### 没有设置 cwd

命令会在启动进程的目录运行，不一定是项目目录。agent 的观察会和用户的工作区脱节。

### 超时直接崩溃

工具异常应该变成 `tool_result`，让模型看到问题并继续调整。agent loop 不应该因为一个命令超时就退出。

### 输出不截断

一次 `pytest -vv` 或 `dir /s` 就可能塞满上下文。工具层要先做基础防护。

## 思考题

1. 为什么工具 schema 给模型看，而 handler 必须留在本地？
2. 为什么 command result 要包含 exit code？
3. `shell=True` 带来哪些便利和风险？
4. 如果 shell 输出被截断，模型应该如何继续排查？

## Bonus Tasks

- 给 ShellTool 增加环境变量白名单。
- 把返回文本改成更稳定的分段格式。
- 在命令执行前记录开始时间，在结果里显示耗时。
- 为 Windows 和 Unix shell 写不同的安全提示。

## 本章小结

你给 agent 加上了第一只“手”。ch01 的 loop 负责来回传递消息；ch02 的 ShellTool 让其中一个 `tool_use` 变成真实动作。

```text
LLM 决定动作
Harness 执行动作
ShellTool 观察环境
tool_result 把观察交还给 LLM
```

下一章会把 shell 这种粗粒度能力拆成更稳定的文件读、写、搜索工具，让 agent 更可靠地理解和修改代码。

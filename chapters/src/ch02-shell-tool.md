# ch02: Shell Tool

> 第一个工具让 agent 从“能对话”变成“能动手”。

## 本章目标

ch01 的 agent loop 已经会处理 `tool_use`，但还没有真实工具。本章实现第一个工具：`bash`。模型可以请求运行 shell 命令，harness 执行命令，把 stdout、stderr 和 exit code 作为 `tool_result` 返回给模型。

完成后，agent 可以列目录、运行 Python 脚本、执行测试。它还不能安全地读写任意文件，也没有权限审批；这些会在后续章节逐步补上。

## 为什么第一个工具是 Shell

Shell 是 coding agent 最通用的动作接口。很多开发任务最终都会落到命令：

- `ls` / `dir` 查看目录
- `python script.py` 运行程序
- `pytest` 跑测试
- `git status` 看工作区

Shell 的优势是覆盖面广，缺点是危险且输出不可结构化。本章只做最小安全检查，目的是理解工具协议；真正的权限系统在 ch05。

## 工具协议分两半

一个工具在 harness 里有两种形态：

```text
schema  -> 给模型看，让模型知道怎么调用
handler -> 本地执行，模型永远拿不到函数本身
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
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["command"],
    },
}
```

模型只会产生这样的请求：

```text
ToolUseBlock(name="bash", input={"command": "python -m pytest"})
```

真正执行命令的是本地 `ShellTool.execute`。

## 输出为什么要包含 exit code

命令输出不只有 stdout。一个测试失败时，关键信息可能在 stderr；一个命令没有输出但 exit code 非 0，也表示失败。

所以工具结果应该包含：

- `exit_code`
- `stdout`
- `stderr`
- 无输出时的占位文本

这让模型能区分“命令成功但没输出”和“命令失败”。

## 需要修改的文件

- `src/tiny_claude_code/tools/shell.py`
- `src/tiny_claude_code/cli.py`

本章实现 `ShellTool`，并让 CLI 初始化默认工具集。ch04 会把工具注册表正式抽象出来；当前项目已经提前使用 `create_default_registry()`，所以后续扩展不需要再改 CLI。

## 实现提示

`ShellTool.execute` 的核心是 `subprocess.run`：

```python
result = subprocess.run(
    command,
    shell=True,
    capture_output=True,
    text=True,
    timeout=timeout,
)
```

本章至少做两个基础校验：

- 空命令直接拒绝
- 超长命令直接拒绝

超时要捕获 `subprocess.TimeoutExpired`，返回错误字符串，而不是让程序崩溃。

## 运行测试

```bash
python scripts/dev.py test --ch 02
```

测试覆盖：

- schema 包含 `command`
- 正常命令能返回 stdout
- 非零退出码会被保留
- 空命令被拒绝
- 超长命令被拒绝
- 超时命令被截断

## 验收任务

运行：

```bash
python scripts/dev.py run
```

输入：

```text
列出当前目录文件，告诉我这是什么项目
```

期望行为：模型调用 `bash`，执行目录查看命令，并根据输出回答。

## 思考题

1. 为什么 schema 不能直接暴露 Python 函数？
2. 为什么命令执行结果需要包含 exit code？
3. `shell=True` 带来了什么便利和风险？
4. 如果 shell 输出非常长，应该在哪里截断？

## 本章小结

你给 agent 加上了第一只“手”。从现在开始，模型不只是生成建议，而是可以请求 harness 执行真实动作。后面章节会把 shell 这种粗粒度能力拆成更可靠的文件读写和搜索工具。

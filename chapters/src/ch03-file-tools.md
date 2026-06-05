# ch03: File Tools

> 让 agent 直接读代码、改代码、搜代码，而不是所有事情都绕到 shell。

## 本章目标

Shell 很通用，但它不是最适合读写文件的接口。模型如果想看一个文件，用 `type README.md` 或 `cat README.md` 可以做到；如果想改文件，用 shell 拼重定向就不稳定，也更危险。

本章实现三个文件工具：

- `read`：读取文件或列目录
- `write`：写入新内容或做精确替换
- `search`：按文件名 glob 或按内容 grep

完成后，agent 可以用结构化工具理解项目，而不是靠 shell 输出猜测。

```text
              +-------- read: 读取文件 / 列目录
LLM tool_use -+-------- write: 写入 / 精确替换
              +-------- search: glob / grep
```

## 先建立心智模型

### 文件工具解决的是“可控性”

用 shell 读写文件时，模型需要自己拼命令：

```text
模型：bash {"command": "python - <<'PY'\n...\nPY"}
```

这类命令难读、难审计、难做权限控制。文件工具把常见动作拆成更清晰的接口：

```text
read(path="src/app.py", offset=20, limit=40)
write(path="src/app.py", old_text="helo", new_text="hello")
search(pattern="TODO", type="grep")
```

参数结构化以后，harness 更容易做路径检查、输出限制和错误提示。模型也更容易从结果里继续推理。

### 路径安全是文件工具的第一责任

文件工具必须绑定 workspace。模型可以请求 `../secret.txt`，但工具不能照做。

```text
用户 workspace: /project

read("src/app.py")       -> /project/src/app.py       allow
read("../secret.txt")    -> /secret.txt               deny
write("notes/todo.md")   -> /project/notes/todo.md    allow
```

判断方法很简单：把目标路径 resolve 后，确认它仍在 workspace 之内。

## 三个工具分别做什么

### ReadTool

`read` 有两种行为：

- 路径是文件：返回文件内容
- 路径是目录：列出目录项，目录名后加 `/`

读取文件时支持行窗口：

```text
read(path="notes.txt", offset=1, limit=2)
```

如果文件内容是：

```text
a
b
c
d
```

返回：

```text
b
c
```

这里 `offset` 是从 0 开始的行偏移，`limit` 是最多返回几行。

### WriteTool

`write` 支持两种模式，但一次只能选一种：

```text
完整写入：content="..."
精确替换：old_text="...", new_text="..."
```

精确替换很适合修 bug，因为它要求旧文本确实存在。如果 `old_text` 找不到，工具必须返回错误并保持文件不变。

```text
old_text found     -> replace once, return Edited
old_text not found -> do not modify, return not found
```

这比“让模型重写整个文件”安全得多。

### SearchTool

`search` 也有两种模式：

- `type="glob"`：按文件名模式找文件，例如 `*.py`
- `type="grep"`：按文件内容找文本，例如 `TODO`

grep 结果应该包含文件名、行号和匹配行：

```text
src/app.py:12: TODO: validate input
```

搜索结果也要限制数量，避免一次返回太多内容。

## 本章要实现什么

主要修改：

- [file_read.py](../../src/tiny_claude_code/tools/file_read.py)
- [file_write.py](../../src/tiny_claude_code/tools/file_write.py)
- [search.py](../../src/tiny_claude_code/tools/search.py)

每个工具都需要：

- 保存默认 workspace
- 实现 schema
- 实现 `safe_path`
- 执行核心动作
- 控制输出长度或结果数量

## 实现路线

### 第一步：统一 safe_path

三个工具都会用到路径检查。逻辑可以各自实现，也可以先写成相似形状：

```python
root = Path(workspace or self.workspace).resolve()
target = (root / path).resolve()
if root not in target.parents and target != root:
    return error
```

Windows 路径也要用 `Path.resolve()` 处理，不要手写字符串前缀判断。

### 第二步：先实现 read

read 的失败情况比较直观：

- 路径越界
- 文件不存在
- 文件太大需要截断
- 目录需要列目录而不是读文本

先让 read 测试通过，会让后续工具更容易验证。

### 第三步：实现 write 的模式判断

`content` 和 `old_text/new_text` 不能混用。

```text
content only                 -> write full file
old_text and new_text only   -> edit exact text
only old_text or only new_text -> reject
content plus edit args       -> reject
```

这一步比实际写文件更重要，因为它决定工具接口是否清晰。

### 第四步：实现 search

glob 可以用 `Path.rglob(pattern)`；grep 可以遍历文本文件并按行匹配。遇到无法按 UTF-8 读取的文件，可以跳过或返回可读错误，但不要让搜索崩溃。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 03
```

测试覆盖：

- 读取指定行窗口
- 读取目录时列出文件和子目录
- 路径越界会拒绝
- 写入新文件
- 精确替换文本
- 替换目标不存在时不修改文件
- 不完整编辑参数会拒绝
- 写入模式和编辑模式混用会拒绝
- glob 搜索文件
- grep 搜索内容并返回行号
- 大文件读取会截断
- 搜索结果数量会限制

## 验收任务

运行 agent：

```bash
python scripts/dev.py run
```

输入：

```text
阅读 README.md，并总结这个项目的用途
```

期望行为：模型调用 `read`，根据 README 内容回答，而不是只靠目录名猜测。

另一个验收：

```text
创建 hello.py，写入 print('hello')，然后运行它
```

这会同时用到 `write` 和 ch02 的 `bash`。

## 常见错误

### 用字符串判断路径前缀

`/project2` 也以 `/project` 开头。路径安全应使用 `Path.resolve()` 和父目录关系。

### 替换失败后仍然写文件

如果 `old_text` 不存在，必须保持文件原样。否则模型会在错误上下文里继续推理。

### grep 不返回行号

没有行号，模型很难定位下一步要读哪一段。

### 目录读取格式不稳定

目录名后加 `/`，文件名直接显示。稳定格式能减少模型误判。

## 思考题

1. 为什么读写文件要从 shell 中拆出来？
2. 精确替换比重写整个文件安全在哪里？
3. 文件工具应该返回结构化 JSON 还是可读文本？各有什么取舍？
4. grep 搜索二进制文件时应该怎么处理？

## Bonus Tasks

- 给 read 增加 `start_line` / `end_line` 的别名。
- 给 write 增加“创建父目录”的开关。
- 给 search 增加大小写敏感选项。
- 在 grep 结果里显示匹配行前后各一行上下文。

## 本章小结

现在 agent 不只会运行命令，还能用更精确的工具观察和修改项目：

```text
read   -> 理解代码
write  -> 修改代码
search -> 定位线索
```

ch04 会把这些工具从“散落的对象”收进统一注册表，让 agent loop 不再关心每个工具的具体来源。

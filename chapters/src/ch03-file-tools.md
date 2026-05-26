# ch03: File Tools

> coding agent 必须能看代码，也必须能改代码。

## 本章目标

Shell 能做很多事，但让模型通过 `cat`、`echo > file`、`sed` 来读写文件并不可靠。本章实现更结构化的文件工具：

- `read`：读文件或列目录
- `write`：写新文件或做精确文本替换
- `search`：glob 文件搜索和 grep 内容搜索

这些工具把常见开发动作变成明确 API，减少 shell 字符串拼接带来的脆弱性。

## 为什么不用 Shell 解决所有事

让模型用 shell 读写文件有几个问题：

- Windows、macOS、Linux 命令差异大
- 引号和转义容易出错
- 写文件时容易覆盖错误路径
- 文本替换可能误伤多处内容
- 很难统一做路径安全检查

文件工具的价值在于把动作语义化：

```text
read(path="README.md")
write(path="hello.py", content="print('hello')")
search(type="grep", pattern="TODO")
```

模型不用猜命令，harness 也更容易验证输入。

## 路径安全是文件工具的底线

工具默认只能访问 workspace 内部。路径必须先 resolve，再检查目标是否仍在 workspace 下面：

```python
root = Path(workspace or Path.cwd()).resolve()
target = (root / path).resolve()
if target != root and root not in target.parents:
    raise ValueError("path escapes workspace")
```

这能拦住 `../secret.txt` 这类越界访问。ch05 会把权限做成独立系统；本章先把文件工具自己的边界立住。

## ReadTool

`read` 同时处理文件和目录：

- path 是文件：返回文本内容
- path 是目录：返回目录项列表
- 支持 `offset` 和 `limit`，用于只读部分行

读取大文件时，行窗口很重要。agent 不应该一口气把几万行日志塞进上下文。

## WriteTool

`write` 支持两种模式。

写入新内容：

```python
write(path="hello.py", content="print('hello')\n")
```

精确替换：

```python
write(path="hello.py", old_text="helo", new_text="hello")
```

如果 `old_text` 不存在，必须返回错误且不修改文件。这个约束很重要：agent 编辑代码时，宁可失败并重新观察，也不要静默写错。

参数组合也必须明确：

- 写文件：必须提供 `path + content`
- 编辑文件：必须提供 `path + old_text + new_text`
- 不能同时提供 `content` 和 `old_text/new_text`

这可以避免模型只传 `old_text` 时把匹配内容误删。

## SearchTool

`search` 有两种模式：

- `type="glob"`：按文件名模式搜索，例如 `*.py`
- `type="grep"`：按文本内容搜索，例如 `TODO`

它不是为了替代 ripgrep，而是提供一个跨平台、可测试的最小搜索接口。后续可以把底层实现替换成 `rg`，外部 schema 不必变。

`read` 和 `search` 都会限制输出大小。这个限制不是完整上下文管理，真正的上下文预算会在 ch08 实现；本章先避免工具一次返回过多文本。

## 需要修改的文件

- `src/tiny_claude_code/tools/file_read.py`
- `src/tiny_claude_code/tools/file_write.py`
- `src/tiny_claude_code/tools/search.py`

## 运行测试

```bash
python scripts/dev.py test --ch 03
```

测试覆盖：

- 安全路径通过和越界拒绝
- 读取文件并支持行窗口
- 列目录
- 写新文件
- 精确替换
- 替换失败时不修改文件
- 不完整编辑参数被拒绝
- glob 搜索
- grep 搜索
- 读文件和搜索输出会截断

## 验收任务

运行：

```bash
python scripts/dev.py run
```

输入：

```text
阅读 README.md 并总结项目用途
```

期望行为：模型调用 `read`，读取 README，然后总结。

## 思考题

1. 为什么 `old_text` 不匹配时不能直接写入 `new_text`？
2. 文件工具应该返回纯文本，还是结构化 JSON？
3. 搜索结果太多时应该怎样限制？
4. 路径安全检查应该在每个工具里做，还是统一放到权限系统里？

## 本章小结

现在 agent 有了读代码、写代码、找代码的能力。Shell 仍然重要，但文件操作应该优先走结构化工具，因为结构化工具更稳定、更容易测试，也更容易加权限。

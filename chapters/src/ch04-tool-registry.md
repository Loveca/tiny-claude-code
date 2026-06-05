# ch04: Tool Registry

> 工具越来越多以后，agent loop 不应该继续手工分发每一个工具。

## 本章目标

ch02 和 ch03 已经有了 `bash`、`read`、`write`、`search`。如果每加一个工具都要修改 agent loop，核心循环会越来越臃肿。

本章实现 `ToolRegistry`，把工具管理从 agent loop 里抽出来：

```text
agent_loop
   |
   +-- get_schemas()  -> 给模型看的工具列表
   |
   +-- dispatch(name, input) -> 本地执行对应工具
```

完成后，agent loop 只关心两件事：

1. 把所有 schema 交给模型。
2. 当模型请求工具时，把工具名和参数交给 registry。

## 先建立心智模型

### Registry 是工具路由器

没有 registry 时，代码容易长成这样：

```python
if name == "bash":
    return shell.execute(...)
if name == "read":
    return reader.execute(...)
if name == "write":
    return writer.execute(...)
```

这不是 agent loop 应该承担的职责。agent loop 负责协议，registry 负责工具集合。

```text
ToolRegistry
  |
  +-- "bash"   -> ShellTool
  +-- "read"   -> ReadTool
  +-- "write"  -> WriteTool
  +-- "search" -> SearchTool
```

模型请求 `name="read"` 时，registry 找到 `ReadTool` 并调用它。

### Tool 抽象统一两个接口

每个工具都应该同时提供：

- `schema`：给模型看的描述
- `execute(...)`：本地执行入口

所以本章引入 `Tool` 基类：

```python
class Tool:
    name: str

    @property
    def schema(self) -> dict:
        ...

    def execute(self, **kwargs) -> str:
        ...
```

这不是为了复杂抽象，而是为了让 registry 能用同一方式管理所有工具。

## 工作流程

```text
启动 CLI
  |
  v
create_default_registry()
  |
  +-- register(ShellTool)
  +-- register(ReadTool)
  +-- register(WriteTool)
  +-- register(SearchTool)
  |
  v
agent_loop(messages, tool_handlers=registry)
  |
  +-- registry.get_schemas() 给 LLM
  |
  +-- registry.dispatch(tool_name, input) 执行工具
```

后续章节会继续往默认注册表里加权限、todo、subagent、background、cron、plugin 等能力。agent loop 不需要为每个新工具改一次。

## 本章要实现什么

主要修改：

- [base.py](../../src/tiny_claude_code/tools/base.py)
- [tools/__init__.py](../../src/tiny_claude_code/tools/__init__.py)
- [agent.py](../../src/tiny_claude_code/agent.py)
- ch02/ch03 的工具类，让它们继承 `Tool`

`ToolRegistry` 至少需要：

- `register(tool)`：按 `tool.name` 保存工具。
- `get_schemas()`：返回所有工具的 schema 列表。
- `dispatch(name, input)`：找到工具并调用 `execute(**input)`。
- `create_default_registry()`：注册默认工具。

## 实现路线

### 第一步：实现 Tool 基类

基类可以只定义接口，不做实际工作：

```python
class Tool:
    name: str

    @property
    def schema(self):
        raise NotImplementedError

    def execute(self, **kwargs):
        raise NotImplementedError
```

测试不会要求它能直接执行；它只是约束子类形状。

### 第二步：实现注册表

内部用 dict 保存工具：

```python
self.tools: dict[str, Tool] = {}
```

重复注册同名工具时，后注册的覆盖旧工具。这让测试工具、插件工具和用户自定义工具更容易替换默认行为。

### 第三步：统一 dispatch

dispatch 要处理未知工具：

```text
name exists     -> tool.execute(**input)
name not exists -> "unknown tool: ..."
```

未知工具不应该抛异常终止 loop。它应该变成 `tool_result`，让模型知道自己调用错了工具。

### 第四步：让 agent loop 支持 registry

ch01 的 `tool_handlers` 可能是 dict；本章开始也可能是 `ToolRegistry`。可以写辅助函数：

```text
_get_tool_schemas(tool_handlers)
_dispatch_tool(tool_handlers, name, input)
```

这样 agent loop 主体保持干净。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 04
```

测试覆盖：

- 注册一个工具后 schema 可见
- 默认注册表包含 `bash`、`read`、`write`、`search`
- dispatch 能调用已注册工具
- 未知工具返回错误文本
- 重复注册会覆盖旧工具
- agent loop 能通过 registry 执行工具

## 验收任务

运行：

```bash
python scripts/dev.py run
```

输入：

```text
创建 hello.py 写入 print('hello')，然后运行它
```

期望行为：模型先调用 `write`，再调用 `bash`。agent loop 不需要知道这两个工具具体怎么实现，只通过 registry 分发。

## 常见错误

### get_schemas 返回工具对象

模型只能看 schema，不能看 Python 对象。返回值应该是 `list[dict]`。

### dispatch 不展开参数

如果工具定义是 `execute(text: str)`，registry 应该调用 `execute(**{"text": "hello"})`，而不是把整个 dict 当成一个位置参数。

### 未知工具直接抛异常

模型可能生成错误工具名。返回错误文本比崩溃更适合 agent loop。

### agent loop 仍然硬编码工具

本章的核心就是移除硬编码分发。后续扩展依赖这个边界。

## 思考题

1. ToolRegistry 和 agent loop 的职责边界是什么？
2. 为什么重复注册同名工具时允许覆盖？
3. 如果一个工具执行时抛异常，registry 应该捕获还是交给 agent loop？
4. schema 顺序是否重要？为什么？

## Bonus Tasks

- 给 registry 增加 `unregister(name)`。
- 在 dispatch 结果里记录工具耗时。
- 为工具增加 `enabled` 开关。
- 给 `create_default_registry` 增加只读模式，只注册 `read` 和 `search`。

## 本章小结

你把工具系统从“手工 if-else”升级成了可扩展注册表：

```text
工具提供 schema 和 execute
Registry 管理工具集合
Agent loop 只处理协议
```

到这里，Part 1 的最小 coding agent 已经成形。下一步的 checkpoint 会让你用自己写的 agent 去修一个真实小 bug。

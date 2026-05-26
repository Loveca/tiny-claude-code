# ch04: Tool Registry

> 循环不应该知道每个工具的细节。

## 本章目标

ch02 和 ch03 已经实现了多个工具。如果每加一个工具都要改 `agent_loop`，主循环会越来越臃肿。本章把工具管理抽象成 `ToolRegistry`：

- 工具自己提供 schema
- registry 负责注册工具
- agent loop 只问 registry 两件事：有哪些 schema，如何 dispatch

完成后，新增工具只需要实现 `Tool` 接口并注册进去，不需要改主循环。

## 为什么需要注册表

最早的工具分发可以是硬编码 dict：

```python
TOOL_HANDLERS = {
    "bash": {"schema": ..., "handler": ...},
}
```

这能跑，但扩展性差：

- schema 和 handler 容易分散
- 重复注册无法统一处理
- 未知工具错误逻辑到处复制
- 插件系统无法自然接入

注册表把工具变成对象：

```python
registry.register(ShellTool())
registry.register(ReadTool())
registry.register(WriteTool())
registry.register(SearchTool())
```

agent loop 不关心具体工具类。

## Tool 接口

所有工具共享最小接口：

```python
class Tool:
    name: str

    @property
    def schema(self) -> dict:
        ...

    def execute(self, **kwargs) -> str:
        ...
```

`schema` 是给模型看的；`execute` 是 harness 本地执行的。

## Registry 的职责

`ToolRegistry` 只做三件事：

```python
register(tool)
get_schemas()
dispatch(name, input)
```

`dispatch` 的行为要稳定：

- 找到工具：调用 `tool.execute(**input)`
- 找不到工具：返回 `"Error: unknown tool ..."`
- 输入参数不匹配：返回错误文本
- 工具执行异常：返回错误文本

这样模型可以看到错误并尝试修正，而不是整个 CLI 崩溃。

## Agent Loop 如何变简单

主循环只需要：

```python
tools = registry.get_schemas()
response = client.chat(messages, tools=tools)
...
output = registry.dispatch(block.name, block.input)
```

这就是一个稳定扩展点。后续 ch15 的插件系统也会依赖这个模式。

## 需要修改的文件

- `src/tiny_claude_code/tools/base.py`
- `src/tiny_claude_code/tools/__init__.py`
- `src/tiny_claude_code/agent.py`
- `src/tiny_claude_code/cli.py`

## 运行测试

```bash
python scripts/dev.py test --ch 04
```

测试覆盖：

- 注册一个工具后 schema 可见
- 默认注册表包含 bash/read/write/search
- dispatch 已注册工具
- dispatch 未知工具返回错误
- 同名工具重复注册时新工具覆盖旧工具
- agent loop 能直接使用 registry
- registry 可以绑定默认工具的 workspace

## 验收任务

运行：

```bash
python scripts/dev.py run
```

输入：

```text
创建 hello.py 写入 print('hello')，然后运行它
```

期望行为：模型可以组合 `write` 和 `bash` 完成任务。内部不再依赖硬编码工具表，而是通过 registry 分发。

## 思考题

1. 为什么工具应该同时携带 schema 和 execute？
2. 重复注册同名工具应该报错还是覆盖？
3. registry 应该吞掉工具异常，还是让异常抛出？
4. 插件系统为什么天然需要 registry？

## 本章小结

到这里，Part 1 的核心结构完成了：agent loop 负责循环，tools 负责动作，registry 负责扩展。这个边界会让后续权限、hooks、插件都更容易接入。

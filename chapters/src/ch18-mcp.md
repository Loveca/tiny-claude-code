# ch18: MCP 客户端

> 工具不必都自己写——用标准协议把外部工具接进来。

## 本章目标

ch15 的插件机制解决的是“仓库内自己写工具”。但社区里已经有大量现成的工具服务，它们跑在独立进程里，用一套标准协议描述自己能做什么。为每个服务写一个 Python 插件，等于把协议重新发明一遍。

本章实现一个最小的 MCP（Model Context Protocol）客户端：

```text
tiny-claude-code                       MCP server (另一个进程)
     │  initialize ────────────────────>│
     │<──────────────── serverInfo      │
     │  notifications/initialized ─────>│
     │  tools/list ────────────────────>│
     │<──────────────── [tool, tool...] │
     │  tools/call {name, arguments} ──>│
     │<──────────────── content blocks  │
```

客户端负责握手、发现工具、转发调用；每个远程工具都会被包装成本地的 `Tool`，放进同一个注册表。对模型来说，它和在仓库里写的 `bash`、`read` 没有任何区别。

## 先建立心智模型

### 插件 vs MCP

| | Python 插件（ch15） | MCP（本章） |
|---|---|---|
| 工具住在哪 | 当前进程 | 独立子进程 |
| 怎么描述能力 | Python 类 + schema 属性 | `tools/list` 返回 JSON |
| 怎么调用 | 直接调用 `execute()` | JSON-RPC `tools/call` |
| 语言限制 | 必须是 Python | 任何语言，只要能读写 stdio |
| 权限检查 | `PreToolUse` hook | 同样经过 `PreToolUse` hook |
| 生命周期 | 随主进程 | 需要显式启动和关闭 |

一句话：插件是“自己写”，MCP 是“按协议接”。

### 为什么用 stdio

MCP 支持多种传输方式。本章选 stdio，因为它是教学成本最低、也最容易观察的一种：

- 一行一个 JSON 对象，直接可读；
- 服务端进程的 stdin/stdout 就是通道，不需要端口、网络和鉴权；
- 进程自然隔离，服务崩溃不会拖垮 agent；
- 测试里可以起一个真实子进程，端到端验证协议。

代价是 stdout 只能走协议。服务端打印任何调试信息到 stdout，都会污染 JSON 流——这类错误在“常见错误”里会再出现一次。

### 为什么把 transport 抽象出来

`MCPClient` 只处理协议语义（握手、工具列表、调用结果），不负责启动进程。启动、写请求、读响应、超时、关闭都在 transport 里：

```python
class MCPClient:
    def __init__(self, transport=None, command=None, ...):
        self.transport = transport or StdioTransport(command, ...)
```

好处是测试可以换成内存里的 fake transport，精确断言发出去的请求；同时又保留一个真实子进程的端到端测试，覆盖 fake 覆盖不到的行缓冲和进程退出。

### 为什么读响应要用线程

请求发出后，需要等待 `id` 匹配的那条响应。Linux 上可以用 `select` 等管道可读，但 Windows 的 `select` 只支持 socket。用一个 daemon 线程持续读 stdout、把行塞进队列，主线程带超时地从队列取，就能同时满足跨平台和超时两个要求。

服务端退出时，线程往队列里放一个 `None` 作为哨兵；请求看到哨兵就知道连接断了。错误信息会附上 stderr 的最后几行——只有 “server closed the connection” 是没法调试的。

## 工具如何进入注册表

`MCPTool` 是一个很薄的适配器：

```python
class MCPTool(Tool):
    def __init__(self, client, definition):
        self.name = definition["name"]
        self.description = definition.get("description", "")
        self.input_schema = definition.get("inputSchema") or {...}

    def execute(self, **kwargs):
        return self.client.call_tool(self.name, kwargs)
```

`tools/list` 返回的 `inputSchema` 本来就是 JSON Schema，可以直接作为 Anthropic 工具的 `input_schema`。这是 MCP 和现有 `Tool` 接口能无缝衔接的关键。

远程调用的错误分两层：

- JSON-RPC 层错误（方法不存在、参数不合法）会抛 `MCPError`，注册表把它包装成 `Error: ...` 返回给模型；
- 工具执行结果里的 `isError: true` 不是传输错误，`call_tool` 会把它格式化成 `Error: <文本>`，让模型知道调用失败但仍能继续对话。

返回内容只取 text block，并用换行拼接。没有 text block 时回退成 JSON 字符串——先保证信息不丢，图片等富内容留作扩展。

## 本章要实现什么

- [mcp.py](../../src/tiny_claude_code_ref/mcp.py)：`MCPClient`、`StdioTransport`、`MCPError`
- [tools/mcp.py](../../src/tiny_claude_code_ref/tools/mcp.py)：`MCPTool` 与 `load_mcp_tools`
- [tools/\_\_init\_\_.py](../../src/tiny_claude_code_ref/tools/__init__.py)：`create_default_registry(..., mcp_client=...)`
- [cli.py](../../src/tiny_claude_code_ref/cli.py)：`--mcp "<command>"`
- [examples/mcp/echo_server.py](../../examples/mcp/echo_server.py)：一个可运行的示例服务

注册表只负责发现和注册，不拥有进程。启动和关闭由调用方管理，CLI 通过 `atexit` 关闭客户端，避免交互会话退出后留下孤儿子进程。

## 实现路线

### 第一步：stdio transport

启动子进程时要注意四点：

```python
subprocess.Popen(
    [command, *args],
    stdin=PIPE, stdout=PIPE, stderr=PIPE,
    text=True, encoding="utf-8", bufsize=1,
)
```

- 文本模式 + UTF-8，避免中文和 emoji 乱码；
- `bufsize=1` 让写入按行刷新；
- 两个 daemon 线程分别读 stdout 和 stderr；
- `close()` 先关 stdin，再 terminate，超时后 kill。

### 第二步：握手

`initialize` 是第一个请求，带上客户端信息：

```json
{
  "protocolVersion": "2025-06-18",
  "capabilities": {},
  "clientInfo": {"name": "tiny-claude-code", "version": "0.1"}
}
```

服务端返回它支持的版本、能力和 `serverInfo`。然后客户端发一条 `notifications/initialized`——注意它是通知，没有 `id`，也不需要响应。

### 第三步：请求与响应

每个请求分配递增的 `id`，然后循环读消息：

```python
while True:
    message = self._next_message()
    if message.get("id") != request_id:
        continue          # 服务端通知或过期的响应
    if "error" in message:
        raise MCPError(...)
    return message.get("result", {})
```

要处理三种异常：超时（队列取不到）、连接断开（哨兵）、非法 JSON。三种都带上 stderr 尾部。

### 第四步：工具适配与接线

`load_mcp_tools(client)` 把 `tools/list` 的每一项变成 `MCPTool`。注册表在有 `mcp_client` 时逐个注册：

```python
if mcp_client is not None:
    for tool in load_mcp_tools(mcp_client):
        registry.register(tool)
```

同名工具会覆盖先注册的（和 `register` 的既有语义一致）。多服务端时的命名前缀留作 Bonus。

### 第五步：CLI

`--mcp "python examples/mcp/echo_server.py"` 解析成 command + args，启动并握手。启动失败只打印到 stderr，不阻断本地工具的使用。注册表同时拿到本地工具和远程工具，普通对话和 `/goal` 都能用。

## 试一下

先跑测试（不需要任何外部服务）：

```bash
python scripts/dev.py test --ch 18 --ref
```

测试覆盖 fake transport 上的协议语义，以及一个真实子进程服务的完整回合。

直接观察协议：

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"demo","version":"0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"text":"hello mcp"}}}' \
  | python examples/mcp/echo_server.py
```

你会看到四行 JSON：`serverInfo`、工具列表、以及 `hello mcp` 的调用结果。

让 agent 用起来：

```bash
python scripts/dev.py run --ref --mcp "python examples/mcp/echo_server.py"
```

```text
> use the echo tool to repeat "hello MCP", then tell me what it returned
```

观察点是：模型看到的工具 schema 来自服务端；`PreToolUse` 权限检查照常执行；服务端进程随会话退出而结束。

## 测试覆盖

- 握手：`initialize` 参数、`notifications/initialized`、幂等启动；
- 请求：递增 `id`、忽略不匹配的响应、错误对象转 `MCPError`；
- 结果：text block 拼接、`isError` 前缀、无 text 时回退 JSON；
- transport：未启动时拒绝请求、不存在的命令给出可读错误、关闭幂等；
- 真实 stdio：启动、发现、调用、关闭，并确认子进程退出；
- 适配器：schema 映射、参数原样转发、缺失字段的默认值；
- 注册表：有 client 时注册远程工具，无 client 时不出现；
- 集成：`agent_loop` 和 `/goal` 都能调用远程工具。

## 验收任务

1. 用 `--mcp` 接上示例服务，让 agent 调用 `word_count` 统计一段文字；
2. 故意把示例服务的调试输出改成 `print()` 到 stdout，观察客户端如何报错，再改回 stderr；
3. 让服务端在 `tools/call` 里返回 `isError: true`，确认模型收到 `Error: ...` 后还能继续对话；
4. 在 `/goal` 里使用一个 MCP 工具完成任务，确认 goal 的完成信号和工具调用互不干扰。

## 常见错误

| 现象 | 原因 |
|---|---|
| 客户端卡住直到超时 | 服务端没有按行 flush；必须 `print(..., flush=True)` |
| 收到非法 JSON | 服务端把日志打到了 stdout；日志应写 stderr |
| 握手后立刻失败 | 只回了 `initialize`，没发 `notifications/initialized` |
| Windows 上 select 不可用 | 不要等管道可读，用读线程 + 队列 |
| 退出后进程残留 | 忘记 `close()`；CLI 用 `atexit` 兜底，嵌入式调用要自己关 |
| 工具名冲突 | 两个服务端同名工具后注册的覆盖先注册的 |

## 思考题

1. 如果同时接多个 MCP server，工具重名应该怎么处理？前缀、命名空间，还是启动时拒绝？
2. 服务端发来的通知（例如“工具列表变了”）现在被跳过。要支持动态刷新，客户端需要改哪几处？
3. `tools/call` 超时后，远程操作可能已经执行了一半。重试安全吗？需要什么信息才能判断？
4. 现在每个工具调用都是一次同步往返。流式输出或长任务应该怎样映射到 MCP 的通知机制？

## Bonus Tasks

- 支持多个 `--mcp`，并用 `server__tool` 前缀避免冲突；
- 把 MCP 的 `resources/list` 和 `prompts/list` 也接进来；
- 加一个基于 HTTP/SSE 的 transport，复用同一个 `MCPClient`；
- 在 `PostToolUse` 里记录每个远程工具的来源 server，方便审计；
- 为 MCP 工具增加独立的权限策略（例如只读服务端不要求审批）。

## 小结

MCP 的复杂度不在协议，而在边界：进程生命周期、stdout 纪律、超时与断连。把这些收进 transport，协议本身只有四个方法，适配器也只有几十行。工具来源从此可以来自仓库外，而 agent 的工具循环一行都不用改。

下一章 ch19 会把 goal loop、subagent、background/cron 编排成可重复执行的 workflow runtime。
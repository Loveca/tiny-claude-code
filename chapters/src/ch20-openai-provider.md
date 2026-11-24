# ch20: OpenAI 兼容适配层

> 让同一套 harness 既能说 Anthropic 的话，也能说 chat completions 的话。

## 本章目标

ch01 把 harness 钉在 Anthropic Messages API 上：`LLMClient.chat()` 返回一个 `Message`，`content` 是 text/tool_use 块列表，`stop_reason` 告诉循环要不要继续。此后所有章节——agent loop、hooks、上下文预算、压缩、会话、记忆、任务、子 agent、团队、goal、MCP、workflow——都只读这两个属性，没有一个字依赖 Anthropic SDK 本身。

这个"只读属性"的事实就是本章的入口。市面上大量模型服务只提供 OpenAI 风格的 chat completions：字段名不同、消息角色不同、工具调用的载体不同，但概念完全对应。本章在边界处加一层转换：

```text
agent_loop  ⇄  Anthropic 形状（harness 内部通用语言）
                 │
                 ├── LLMClient                 → Messages API（ch01）
                 └── OpenAICompatibleClient    → chat completions（本章）
                        ├─ anthropic_messages_to_openai
                        ├─ anthropic_tools_to_openai
                        └─ openai_response_to_anthropic
```

完成后，改一个环境变量就能把 agent 指到 OpenAI、DeepSeek、Kimi、GLM、MiniMax、Ollama、vLLM 等任何兼容 chat completions 的服务，而 agent loop 的代码一行都不用动。

## 先建立心智模型

### 为什么在 wire 层转换，而不是在 SDK 层

最省事的写法是引入 `openai` 包，让两个 SDK 各自跑。但那样本章要教的东西——消息格式怎么对应——被 SDK 藏起来了；而且为了学机制，项目已经刻意只依赖一个 SDK。

本章直接用标准库 `urllib.request` 发一次 JSON POST。代价是要自己处理 HTTP 错误，收益是：`requirements.txt` 不变、请求体长什么样一目了然、测试里注入一个假 transport 就能覆盖全链路。

### 两套 API 的对应关系

harness 内部永远保持 Anthropic 形状：出去时转成 chat completions，回来时转回块结构。一张表说完：

| Anthropic Messages | chat completions |
|---|---|
| `system` 参数 | 数组最前面的 `{"role": "system"}` 消息 |
| user 文本块 / 纯字符串 | `{"role": "user", "content": text}` |
| assistant 文本块 | `{"role": "assistant", "content": text}` |
| assistant `tool_use` 块 | `assistant.tool_calls[]`，`function.arguments` 是 **JSON 字符串** |
| user 里的 `tool_result` 块 | 独立的 `{"role": "tool", "tool_call_id": ..., "content": ...}` 消息 |
| 工具 `{name, description, input_schema}` | `{type: "function", function: {name, description, parameters}}` |
| `stop_reason: tool_use / end_turn / max_tokens` | `finish_reason: tool_calls / stop / length` |

因为内部形状没变，agent loop、hooks、上下文管理、压缩、session、memory 全都零改动——而且会话记录在两种 provider 之间是可以续的：`--resume` 一个 Anthropic 跑出来的会话，换 provider 继续。

### 为什么 tool 消息必须排在文本前面

Anthropic 允许一条 user 消息里同时装 `tool_result` 块和文本块。chat completions 不行：`role: tool` 的消息必须紧跟在发起 tool_calls 的那条 assistant 消息后面，中间插入别的角色就会被严格的 server 拒掉。

所以 `_user_messages` 的输出顺序是固定的：先所有 `tool` 消息，再把文本拼成一条 user 消息追加；没有文本就不产生空的 user 消息。这一条顺序决定了适配层能不能跑在第二圈——工具结果发不出去，模型就永远看不到观察。

### 为什么失败要带 status_code

ch07 的 `ErrorHandler` 认两个属性：`exc.status_code` 和 `exc.headers`（读 `Retry-After`）。它并不关心异常来自哪个 SDK。

所以本章的 `OpenAIError` 把 HTTP 状态码和响应头挂在异常上：429 走退避重试、529 等 `Retry-After`、连接错误不带状态码因而不重试。适配层没有新增任何重试机制，只是接上了已有的那条契约。

### 坏参数降级，而不是崩

有些服务会在 `arguments` 里返回不合法的 JSON。适配层把它转成 `input=None` 的 `tool_use` 块——`agent_loop`（ch07 加的守卫）看到非 dict 的 input，会正常回一条 `"Error: malformed tool_use block"` 的工具结果。模型下一轮自己会改。一次坏调用不该杀掉整轮对话。

## 需要修改的文件

| 文件 | 要实现的东西 |
|---|---|
| `llm.py` | `OpenAIError`、`TextBlock`、`ToolUseBlock`、`ChatResponse`、`anthropic_messages_to_openai`、`anthropic_tools_to_openai`、`openai_response_to_anthropic`、`OpenAICompatibleClient`、`create_client` |
| `cli.py` | `LLMClient()` 换成 `create_client()`（一行） |
| `.env.example` | 增加 `LLM_PROVIDER` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` 示例 |

### 环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` 或 `openai` | `anthropic` |
| `OPENAI_API_KEY` | chat completions 的 Bearer token | 空 |
| `OPENAI_BASE_URL` | 服务根地址，endpoint 由它拼 `/chat/completions` | `https://api.openai.com/v1` |
| `MODEL_ID` | 两种 provider 共用 | `claude-sonnet-4-6` / `gpt-4o-mini` |

## 实现提示

分四步，每步都能单独测。

**1）纯函数先行。** 三个转换函数不碰网络，是整个适配层最好测的部分。取块属性用一个 helper 兼容对象与 dict 两种形态：

```text
_field(block, name): isinstance(block, dict) ? block.get(name) : getattr(block, name)
```

消息转换的骨架：

```text
converted = []
if system: converted.append({"role": "system", "content": system})
for message in messages:
    if isinstance(content, str):        直接透传
    elif role == "assistant":           文本拼成 content，tool_use 变 tool_calls
    else:                              tool_result 变 tool 消息，文本变收尾 user 消息
```

**2）响应转回来。** 只造 loop 会读的字段：

```text
blocks = [TextBlock(text)] + [ToolUseBlock(id, name, input) for tool_calls]
stop_reason = "tool_use" if tool_calls else ("max_tokens" if finish_reason == "length" else "end_turn")
```

`arguments` 用 `json.loads`，失败给 `None`。`choices` 为空说明响应根本不是 chat completions——抛 `OpenAIError`，别猜。

**3）客户端组装 payload 并注入 transport。** 构造函数不发消息，测试才能替掉传输：

```text
OpenAICompatibleClient(model=..., api_key=..., base_url=..., transport=fake)
chat(messages, tools, max_tokens, system)
    payload = {model, max_tokens, messages: 转换(messages, system)}
    if tools: payload["tools"] = 转换(tools)
    data = transport(endpoint, {"Authorization": f"Bearer {api_key}", ...}, payload)
    return openai_response_to_anthropic(data)
```

`_http_transport` 负责真实请求：`HTTPError` 读一段 body 拼成可读信息，连同 `status_code` 和响应头包成 `OpenAIError`。

**4）选型接上 CLI。**

```text
create_client():
    provider = env("LLM_PROVIDER", "anthropic").lower()
    return OpenAICompatibleClient() if provider == "openai" else LLMClient()
```

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 20
```

测试覆盖（全部离线，不发一个网络请求）：

- 消息转换：system 前置、纯字符串 user、assistant 文本 + `tool_calls` 往返、`tool_result` 排在尾部文本之前、无文本时不产生空 user 消息、工具 schema 转 function
- 响应适配：纯文本、tool_calls 与参数解析、非法 JSON → `input=None`、`finish_reason=length` → `max_tokens`、空 `choices` 抛 `OpenAIError`
- 客户端：注入 fake transport，断言 endpoint、Bearer 头、model、payload 形状
- 端到端：两轮 `agent_loop`（先工具调用再收尾文本）跑在 fake transport 上，检查第二次请求里确实带着 assistant `tool_calls` 和对应 `tool` 消息
- 错误路径：`ErrorHandler` 对 429 `OpenAIError` 退避后成功（3 次调用），以及耗尽重试后原样抛出（4 次调用）
- 选型：`LLM_PROVIDER=openai` 走适配层，其余与未设置时回到 Anthropic 客户端

## 验收任务

最小验证不需要任何付费 key——本地起一个 Ollama 即可：

```bash
cp .env.example .env
# 编辑 .env：
#   LLM_PROVIDER=openai
#   OPENAI_BASE_URL=http://localhost:11434/v1
#   OPENAI_API_KEY=ollama
#   MODEL_ID=qwen3:8b
python scripts/dev.py run --ref
> 列出当前目录的文件，告诉我这是什么项目
```

或者用任何兼容服务（DeepSeek 的 openai 端点、Kimi、GLM、vLLM…）：

```bash
LLM_PROVIDER=openai OPENAI_API_KEY=... OPENAI_BASE_URL=https://api.deepseek.com MODEL_ID=deepseek-chat \
  python scripts/dev.py run --ref -- "阅读 README 并总结项目用途"
```

然后做一件只有"转换层写对了"才成立的事：先用 Anthropic 端点聊两轮，退出，再用 `--resume` 换到 openai 端点继续。会话历史是从盘上读回来的 Anthropic 形状，能接着聊说明转换是双向自洽的。

## 常见错误

### 把 tool 结果和文本混在一条 user 消息里发出去

chat completions 会直接 400。`tool` 角色必须紧跟 assistant 的 tool_calls，文本另起一条放在后面。

### 以为 `arguments` 是对象

Anthropic 的 `input` 是 dict，OpenAI 的 `function.arguments` 是 JSON **字符串**。出去时 `json.dumps`，回来时 `json.loads`，方向搞反就全线失败。

### 直接把 `finish_reason` 透传

`agent_loop` 判的是 `stop_reason == "tool_use"`。透传 `"tool_calls"` 或 `"stop"` 会让循环在拿到工具调用时以为模型说完了，工具永远不执行。

### 用 `content: ""` 表达"只有工具调用"

有些服务接受空串，有些严格要求 null。规则：有文本就拼字符串，没文本就是 `None`。

### 错误对象不带 status_code

适配层抛裸 `RuntimeError` 的话，ch07 的 429/529 重试会静默失效——表现为"一限流就死"，但看不出是没重试。`OpenAIError` 存在的意义就是接上这条契约。

### 顺手引入 openai 包

能跑，但本章要练的正是格式转换本身；引了 SDK，练习就没了。

## 思考题

1. 流式输出：chat completions 的 SSE 增量里，`tool_calls` 是按 `index` 分片到达的。要把它拼回完整参数，适配层和 CLI 渲染各需要改什么？
2. 如果再加第三种 provider（比如 Google 的 generateContent），是继续两两转换，还是先定义一个 harness 内部的中立消息 IR、让每个 provider 只写一次进出转换？代价和收益怎么算？
3. 上下文预算（ch08）按字符数 / 4 估 token。两种 provider 的 tokenizer 不同、且 `max_tokens` 语义（只算输出）一致，跨 provider 复用同一份压缩阈值安全吗？
4. 本章测试全靠注入 transport。如果要用标准库 `http.server` 起一个假的 chat completions 服务做真 HTTP 集成测试，哪些断言能新增、哪些坑（端口、超时、线程）要先想到？

## Bonus Tasks

- 给 `OpenAICompatibleClient` 加 `extra_headers`，方便接企业网关。
- 支持 `LLM_PROVIDER=responses` 走 OpenAI Responses API（消息结构又是一次映射）。
- 加一个 `--provider` CLI 参数覆盖环境变量，并在启动横幅打印当前 provider 与 model。
- 把 `MODEL_ID` 的默认值按 provider 分开（`ANTHROPIC_MODEL_ID` / `OPENAI_MODEL_ID`），减少来回切 provider 时的误配。

## 本章小结

适配层就三件事：

```text
出去转   -> 消息、工具、system 各自换名字和位置
回来转   -> 块结构与 stop_reason 还原成 harness 的通用语言
错误对齐 -> 状态码挂到异常上，接上 ch07 已有的重试契约
```

harness 的其余部分完全没动——这正是 ch01 把 LLM 调用包成一个 `chat()` 方法的意义：边界越窄，能换的东西越多。剩下的可选项见 `docs/ROADMAP.md`。
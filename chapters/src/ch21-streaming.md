# ch21: 流式输出

> 让回答一个字一个字地出现，而不是等整段生成完。

## 本章目标

到 ch20 为止，harness 每一轮都是同一个节奏：发请求 → 等到模型写完 → 拿到完整的 `Message` → 再决定做什么。回答短的时候无所谓，一旦模型要写几百字，用户面对的就是一个不动的光标。

真实产品的做法是流式：服务端边生成边推送，客户端边收到边显示。本章给 agent 接上这条通路，而且要守住一条底线——**循环的其余部分一行都不用改**。

```text
                 ┌──────────── ch21 新增 ────────────┐
provider  ──▶  事件流  ──▶  agent_loop  ──▶  on_text  ──▶  终端
 (SSE)      4 种事件      │
                         └──▶ StreamAccumulator ──▶ ChatResponse ──▶ 和以前完全一样
```

完成后：

- `--stream` 启动时，助手文本到达即打印；
- 不加 `--stream`，行为与 ch20 逐字节一致；
- 会话仍然照常落盘，`--resume` 照常续聊。

## 先建立心智模型

### 流式改变的是"到达方式"，不是"内容"

非流式调用返回一个 `Message`：`content` 是块列表，`stop_reason` 说明为什么结束。循环只读这两样东西。

流式调用返回的是一串**增量**：半句话、一个工具名的开头、一段还没闭合的 JSON。它不是一个 `Message`，也没法直接交给循环。所以需要三步：

```text
wire 事件  ──translate──▶  harness 事件  ──accumulate──▶  Message 形状
 (各家不同)                (只有 4 种)                     (循环认识)
```

翻译在客户端里做，累加在一个独立的类里做。循环看到的结果与非流式别无二致，自然不用改。

### 四种事件就是全部词汇

| 事件 | 含义 | 携带 |
|---|---|---|
| `TextDelta` | 一段助手文本 | `text` |
| `ToolUseStart` | 一次工具调用开始 | `id`、`name` |
| `ToolUseArgsDelta` | 参数 JSON 的一块碎片 | `partial_json` |
| `MessageStop` | 本轮结束 | `stop_reason` |

两家 API 的原生事件长得完全不同，但都能落到这张表上：

| | Anthropic Messages | chat completions |
|---|---|---|
| 文本增量 | `content_block_delta` → `delta.type == "text_delta"` | `choices[0].delta.content` |
| 工具开始 | `content_block_start` → `content_block.type == "tool_use"` | `delta.tool_calls[i]` 首次带上 `id` 或 `function.name` |
| 参数增量 | `delta.type == "input_json_delta"` → `partial_json` | `function.arguments` |
| 结束原因 | `message_delta` → `delta.stop_reason` | `finish_reason` |
| 流终止 | `message_stop` 事件 | `data: [DONE]` 行 |

表里已经藏着两家最大的差别：**Anthropic 用事件边界表达"一个工具调用开始了"，chat completions 只给你带 `index` 的碎片**。同一个 `index` 的碎片属于同一次调用，第一个碎片负责开局，后面的只往参数上追加。

### 参数是字符串，而且是断开的

`ToolUseArgsDelta.partial_json` 单独看几乎一定是非法 JSON：`{"comm` 不是，`and": "ls"}` 也不是。只有拼起来才能 `json.loads`。

所以累加器要记住"当前正在填充哪个工具调用"，收到下一次 `ToolUseStart` 或 `MessageStop` 时才把攒下的文本解析成 `input`。解析规则沿用 ch20：空文本表示无参数（`{}`），解析失败给 `None`，交给循环的 malformed-tool_use 分支回一条错误结果。

### 结束必须发生且只发生一次

循环靠 `stop_reason` 判断"是执行工具还是收工"。如果流被掐断、没有收到任何结束事件，而累加器也不补一个，循环会拿到一个永远停在默认值上的响应。

因此约定：**`MessageStop` 一定出现，且是最后一个事件**。连接中途断掉时由客户端补发；工具块已经出现却没有结束事件时，累加器自己把 `stop_reason` 推断为 `tool_use`。

### 回调只送文本，并在每轮末尾换行

循环对外的接口是一个回调：

```text
on_text: (str) -> None
```

规则只有两条：

1. 文本一到就调用，不缓存、不合并；
2. 每一轮**产生过文本**的结尾补一个 `"\n"`，之后打印的东西（工具日志、下一轮的第一段文字）才能另起一行。

只产生工具调用、没有文字的那一轮不回调任何东西。

没有 `chat_stream` 的 client（比如测试里的 mock）也能配这个回调：退回 `chat()`，把整段文本一次性交出去。回调的契约对每种 client 都成立，调用方不用判断。

### 流式这一轮不走 ErrorHandler

ch07 的重试是"失败后重来一次"。流式里失败可能发生在**已经打印了一半之后**，重来会把那半段再打一遍。本章不解决这个问题，只是明确地绕开：`on_text` 给出时直接调用 client。代价写在 `--help` 里，由使用者决定要不要开。

## 需要修改的文件

| 文件 | 要实现的东西 |
|---|---|
| `llm.py` | 四个事件 dataclass、`StreamAccumulator`、`LLMClient.chat_stream`、`OpenAICompatibleClient.chat_stream`、`_http_stream_transport`、`_stream_stop_reason` |
| `agent.py` | `agent_loop` 增加 `on_text` 参数；新增 `_chat_stream` |
| `cli.py` | `--stream` 开关；一个边收边打印、且记得自己打印过什么的渲染器 |
| `session.py` | 保存时把 dataclass 块转成普通字典 |

最后一行容易漏：ch20 的适配层和本章的累加器返回的块都是 dataclass，而 `SessionManager.save` 直接 `json.dumps(messages)`。不处理的话，第一次流式对话结束后保存会话时就会抛 `TypeError`。

## 实现提示

分五步，前两步不碰网络。

**1）事件与累加器。** 四个事件是只有类型字段和载荷字段的 dataclass。累加器维护三样东西：块列表、`stop_reason`、以及"正在填充的工具块"的引用。

```text
feed(event):
    text_delta         -> 追加到最后一个块（若它也是文本块），否则新开一个文本块
    tool_use_start     -> 同 id 的重复出现只更新 name；否则关掉上一个，新开工具块
    tool_use_args_delta-> 往当前工具块的碎片缓冲里 append
    message_stop       -> 记下 stop_reason，关掉当前工具块
    其他                -> 忽略

response():
    关掉还没关的工具块（此时才 json.loads 碎片）
    如果仍是 end_turn 而块里有工具调用  -> stop_reason = "tool_use"
```

**2）Anthropic 流。** 在请求参数里加 `"stream": True`，SDK 返回的就成了可迭代的原生事件。按上面的对照表逐类翻译即可，注意 `content_block_delta` 里还有一层 `delta.type` 要判断。循环结束后如果没有发过 `MessageStop`，补发一个。

**3）chat completions 流。** 传输层改成生成器：逐行读响应，只认 `data:` 开头的行，遇到 `[DONE]` 就停，其余行 `json.loads` 后 yield。请求头加 `Accept: text/event-stream`。

翻译时用一个 `{index: 是否已开局}` 的字典跟踪工具调用：

```text
for call in delta.tool_calls:
    if 该 index 未开局 且 (有 id 或 有 name):  yield ToolUseStart(id 或 f"call_{index}", name)
    if 有 arguments:                           yield ToolUseArgsDelta(arguments)
```

`finish_reason` 出现时记下映射结果，流结束后 yield 唯一的 `MessageStop`。

**4）循环接回调。** `agent_loop` 多一个默认为 `None` 的 `on_text`。为 `None` 时走原来的 `_chat`；否则走 `_chat_stream`：

```text
_chat_stream(client, messages, tools, system, on_text):
    if client 没有 chat_stream:   response = client.chat(...); 把整段文本和 "\n" 交给 on_text; 返回 response
    accumulator = StreamAccumulator()
    for event in client.chat_stream(...):
        if 是 text_delta 且非空:   on_text(event.text)
        accumulator.feed(event)
    if 本轮回调过文本:            on_text("\n")
    return accumulator.response()
```

返回值与非流式路径是同一种对象，所以 `messages.append(...)` 及其后的全部逻辑保持不变。

**5）CLI 渲染。** 真正的差别只在"最后还打不打 `response`"：流式模式下答案已经在屏幕上了，再打一遍就是重复。让渲染器记住自己最近输出过的内容，并提供一个判断：

```text
shown_finally(response) =  最近输出以 response + "\n" 结尾
```

为真时只补一个空行，为假（比如循环以 "maximum number of turns" 文本收尾，而这段并没有被流式输出）时照常打印。`print` 时用 `end=""` 和 `flush=True`，否则输出会被缓冲到结束才一次出现，流式就成了假的。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 21
```

六个测试文件，42 个用例，全部离线：

- **累加器**（11）：文本合并、空增量忽略、工具调用之后再来的文本另起一块、跨碎片解析参数、无参数 → `{}`、坏 JSON → `None`、重复 start 更新 name、两个工具调用互不混淆、结束原因来源、无结束事件时推断 `tool_use`、未知事件忽略
- **两个客户端**（11）：用假的 SDK 流和假的 `stream_transport` 喂原生事件，断言翻译出的事件序列、请求里带了 `stream: True`、Anthropic 流被截断时仍会补 `MessageStop`、chat completions 的碎片合并、缺 `id` 时合成、`length` → `max_tokens`
- **会话**（3）：流式得到的块能存成 JSON、读回来是 API 认的字典形状、并且能被 ch20 的转换函数处理
- **循环**（8）：增量按到达顺序送达、工具轮先出文字再执行工具且第二次请求携带重建后的块、无文字的轮不回调、tools 与 system 照常传递、没有 `chat_stream` 的 client 整段回调、流式不经过 `ErrorHandler`、不给 `on_text` 时绝不调用 `chat_stream`、在 chat completions 碎片上的端到端
- **渲染器**（5）：立即写出、增量之间不插入换行、能认出已显示的最终回答、未流式输出的收尾信息不算已显示
- **CLI**（4）：真实跑一遍 `main(["--stream", ...])`，断言第二个增量出现之前第一个已经在输出里；答案不会被打印两次；不加开关时照旧；流式对话被保存成会话

其中"第二个增量出现前第一个已可见"这条是这样测的：在假 client 生成第二个增量之前调用一次 `capsys.readouterr()`，记下那一刻屏幕上的内容。

## 验收任务

```bash
python scripts/dev.py run --ref -- --stream "用三句话解释什么是 agent loop"
```

观察文字是否逐段出现，而不是最后一次性出现。再对比一次：

```bash
python scripts/dev.py run --ref -- "用三句话解释什么是 agent loop"
```

然后让它调用工具：

```bash
python scripts/dev.py run --ref -- --stream "列出当前目录的文件，并告诉我这是什么项目"
```

要检查三件事：工具执行前的那句话是否先流式出现；工具日志是否另起一行；最终回答是否只出现一次。最后退出后用 `--resume` 接着聊，确认上一轮流式产生的消息能被正确读回。

## 常见错误

### 攒够了一整段再交给回调

把所有 `TextDelta` 先收进列表、循环结束再统一 `on_text`，功能上没错，但那就不是流式了。回调必须在每个增量到达时立刻调用。

### 忘了 `flush=True`

`print(text, end="")` 在管道或某些终端下会被缓冲，用户看到的仍然是"等很久，然后一次全出来"。测试能过、验收却不对，多半是这个原因。

### 把 `partial_json` 当成完整的 JSON 去解析

每收到一个 `ToolUseArgsDelta` 就 `json.loads` 一次，第一个碎片就会抛异常。解析只发生在工具调用关闭的时候。

### 流结束后把 `response` 又打印了一遍

答案在屏幕上出现两次。渲染器必须能回答"这段文字是不是我已经显示过的"。

### 每一轮无条件补换行

只含工具调用的那一轮会在工具日志前多出一个空行。换行只跟在真正输出过文本的轮次后面。

### 没有给 `MessageStop`

连接中断时流提前结束，循环拿到默认的 `end_turn`，把一次未完成的工具调用当成最终回答直接返回。

### 会话保存时抛 `TypeError`

非流式路径下块来自 SDK，流式路径下块来自累加器，后者是 dataclass。`json.dumps` 不认识它——给 `save` 加一个 `default`。

### 默认开启流式

流式这一轮没有重试。把它做成需要显式选择的开关，默认路径才能继续享受 ch07 的退避重试。

## 思考题

1. 本章为了不重复输出而放弃了流式重试。如果服务端在已经输出 100 个字之后返回 429，有没有办法既重试又不让用户看到重复的文字？（提示：有些客户端会用回退控制符覆盖掉上一段。）
2. `StreamAccumulator` 假设同一个工具调用的碎片是连续到达的。如果服务端交错发送两个 `index` 的参数碎片，现在的实现会怎样？要支持交错，"当前工具块"这一个引用需要变成什么？
3. 上下文压缩（ch08）和 `max_tokens` 都发生在请求之前。流式会让"模型写到一半被 `max_tokens` 截断"这件事更早被用户看到，循环的处理需要跟着变吗？
4. 如果要给工具参数的解析失败做一次"修复尝试"（比如补全被截断的 JSON），应该放在累加器里，还是放在循环的 malformed 分支里？各自的代价是什么？

## Bonus Tasks

- 支持 `Ctrl+C` 中断当前这一轮流式输出，保留已经生成的部分文字，并且不让会话损坏。
- 在 REPL 里加 `/stream on|off`，不用重启就能切换。
- 给流式路径接上重试：失败时清掉本轮回调过的输出再重发（终端里用 `\r` 加清行实现）。
- 统计首字延迟（从发请求到第一个 `TextDelta` 的时间）和生成速度，在 `Stop` hook 里打印出来。

## 本章小结

流式输出就是三件事：

```text
翻译   -> 各家原生事件收敛成 4 种 harness 事件，MessageStop 必达且唯一
累加   -> 碎片拼回 ChatResponse，循环看到的和非流式一模一样
回调   -> 文本即到即送，每轮结尾换行；渲染器记得自己显示过什么
```

`agent_loop` 只多了一个默认关闭的参数，默认路径没有变化——和 ch20 一样，能这么轻地接入，靠的还是 ch01 留下的那条窄边界。剩下的可选项见 `docs/ROADMAP.md`。

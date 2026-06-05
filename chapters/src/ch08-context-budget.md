# ch08: Context Budget

> 上下文窗口是有限资源，agent 必须学会在耗尽前回收。

## 本章目标

到目前为止，`messages` 会不断增长。每次工具调用都会追加 assistant 的 `tool_use` 和 user 的 `tool_result`。长任务跑久以后，上下文会变得很大。

本章实现 `ContextManager`，在每次 LLM 调用前估算 token，并在超出预算时压缩消息：

- 截断过长工具输出
- 裁掉中间旧消息
- 保留开头的任务背景和结尾的最新上下文

```text
messages
  |
  v
estimate_tokens
  |
  +-- within budget -> 直接传给 LLM
  |
  +-- too large -> trim tool output -> snip old messages -> retry
```

ch09 会加入 LLM 总结式 compact。本章先做不依赖模型的机械压缩。

## 先建立心智模型

### messages 是短期记忆，也是成本

ch01 说过，LLM API 是无状态的，harness 必须每次传入完整 `messages`。这让模型能记住历史，但也带来成本：

```text
更多历史 -> 更多上下文 -> 更高成本 -> 更接近窗口上限
```

工具输出尤其危险。一次测试失败、一次目录递归、一次大文件读取，都可能产生几千到几万字符。

### 压缩不是随便删除

删除消息会丢信息。压缩策略要尽量保留对当前任务最有用的部分：

```text
开头：用户最初目标、system 背景
中间：较旧的工具细节，可裁剪
结尾：最近几轮对话和工具结果
```

```text
[head][old details old details old details][tail]
   |              remove/snip              |
   v
[head][... earlier messages omitted ...][tail]
```

## 三个核心能力

### estimate_tokens

教学项目使用粗略估算即可：

```text
tokens ~= characters / 4
```

它不精确，但足够判断“是否明显太长”。真实系统可以接入 tokenizer。

### trim_tool_output

工具输出可以局部截断，而不用删除整条消息。

```text
tool_result content 太长
  |
  v
保留前 max_chars 字符 + "[truncated]"
```

这样模型至少知道工具执行过，并且结果被截断了。

### snip_old_messages

当单条输出截断还不够，就裁掉中间旧消息：

```text
保留 keep_head 条
保留 keep_tail 条
中间替换成一条说明消息
```

保留 head 是为了不丢初始目标；保留 tail 是为了保留最近状态。

## 本章要实现什么

主要修改：

- [context.py](../../src/tiny_claude_code/context.py)
- [agent.py](../../src/tiny_claude_code/agent.py)

需要实现：

- `ContextManager.__init__`
- `estimate_tokens`
- `trim_tool_output`
- `snip_old_messages`
- `compact`
- `_content_to_text`
- agent loop 在调用 LLM 前触发 context compact

## 实现路线

### 第一步：把 content 转成文本

message 的 content 可能是字符串，也可能是 block 列表。估算 token 前要能统一取文本。

```text
str content -> 直接使用
list content -> 拼接其中 text/content 字段
unknown -> str(...)
```

### 第二步：估算总 token

遍历 messages，把 role 和 content 都算进去即可。粗略估算比完全不估算好。

### 第三步：截断工具输出

只处理 `type == "tool_result"` 的 block。不要截断普通用户请求或模型最终回答。

### 第四步：裁剪旧消息

如果截断后仍超预算，保留头尾，中间插入一条说明：

```text
[Earlier conversation omitted to fit context budget.]
```

这条说明让模型知道历史被裁掉了。

### 第五步：接入 agent loop

每次 LLM 调用前：

```python
if context_manager:
    messages[:] = context_manager.compact(messages)
```

如果修改的是同一个 list，注意保持调用方看到更新后的 messages。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 08
```

测试覆盖：

- token 估算随字符数增加
- 工具输出截断会加 `[truncated]`
- 裁剪旧消息会保留头尾
- compact 后 token 数下降
- 空消息不会崩溃
- agent loop 会在 LLM 调用前压缩

## 验收任务

让 agent 做一个会产生多次工具调用的任务：

```text
搜索项目中所有 Python 文件，并总结每个文件大概负责什么
```

观察 agent 是否能持续工作，而不是因为上下文过长失败。

## 常见错误

### 直接删除最早消息

最早消息通常包含用户目标。全部删掉会让模型忘记任务。

### 截断所有 content

普通用户请求和模型推理文本不应该被无差别截断。优先处理工具输出。

### compact 返回新 list 但调用方没接住

agent loop 中如果需要原地更新，使用 `messages[:] = ...`。

### token 估算追求过度精确

本章目标是预算意识，不是实现 tokenizer。粗略估算足够通过教学测试。

## 思考题

1. 为什么工具输出是上下文膨胀的主要来源？
2. 保留 head 和 tail 分别保护了什么信息？
3. 机械裁剪和 LLM 总结各有什么优缺点？
4. 如果裁掉的历史里有关键事实，agent 应该如何恢复？

## Bonus Tasks

- 给不同工具设置不同输出预算。
- 在截断文本里保留开头和结尾。
- 统计每轮压缩前后的 token 数。
- 支持按消息重要性裁剪。

## 本章小结

你让 agent 开始主动管理上下文：

```text
估算预算
截断长工具输出
裁掉旧消息
保留任务头部和最近状态
```

下一章会在机械压缩不够时，引入 `/compact`：让模型把长历史总结成更短的记忆。

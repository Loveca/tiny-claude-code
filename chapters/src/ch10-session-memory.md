# ch10: Session and Memory

> session 让 agent 记住这次对话，memory 让 agent 记住这个项目。

## 本章目标

前两章解决了“当前对话太长”的问题。本章解决两个更长期的问题：

- 退出 CLI 后，下一次还能恢复会话。
- 项目经验可以被保存成长期记忆，之后启动时注入 system prompt。

## 知识串讲：Session 和 Memory 的边界

Session 是一次任务的运行轨迹，Memory 是跨任务复用的稳定事实。前者像工作日志，记录用户输入、模型回复、工具调用和结果；后者像项目偏好或长期知识，例如“这个仓库用 pytest 验证”“不要自动格式化某些生成文件”。

把二者混在一起会带来两个问题。第一，session 太细，全部长期保存会污染未来任务；第二，memory 太粗，如果塞进当前 transcript，会让模型误以为所有偏好都和当前任务有关。好的 agent 会在需要时检索相关 memory，而不是每轮无差别注入全部记忆。

本章实现的 session/memory 是最小版本，但边界要先立住：session 解决“这次对话怎么恢复”，memory 解决“下次任务应该继承什么稳定知识”。

## Session

`SessionManager` 把消息保存到：

```text
.tiny-claude-code/sessions/
```

它提供：

- `save(session_id, messages, metadata)`
- `load(session_id)`
- `list_sessions()`
- `latest_session_id()`

CLI 支持：

```bash
python scripts/dev.py run -- --resume
```

或者直接运行模块时：

```bash
tiny-claude-code --resume
```

`--resume` 不带参数时恢复最近一次 session；带参数时恢复指定 session id。

## Memory

`MemoryManager` 把长期记忆保存到：

```text
.tiny-claude-code/memory/
```

每条记忆是一个带 frontmatter 的 Markdown 文件：

```markdown
---
category: project
title: Uses pytest
created_at: ...
---

Run tests with pytest -q
```

CLI 支持：

```text
/memory add "Testing" "Run tests with pytest -q"
/memory list
```

启动时，相关 memory 会被注入 system prompt，帮助 agent 继承项目经验。

## 运行测试

```bash
python scripts/dev.py test --ch 10
```

测试覆盖：

- session 保存和加载
- session 按更新时间排序
- memory frontmatter 格式
- memory 关键词检索
- `MEMORY.md` 索引生成
- system prompt 注入 memory
- `/memory add` 命令

## 验收任务

1. 启动 agent，进行几轮对话后退出。
2. 使用 `--resume` 启动，确认上一轮消息被恢复。
3. 输入 `/memory add "Testing" "Run tests with pytest -q"`。
4. 再次启动，确认 agent 的 system prompt 会包含这条项目记忆。

## 思考题

1. session 和 memory 的边界是什么？
2. 哪些信息适合长期保存，哪些只应该留在当前会话？
3. memory 关键词检索有什么局限？

## 本章小结

ch10 让 agent 从一次性脚本变成可恢复的工作伙伴。session 保存短期上下文，memory 保存跨会话经验，二者共同支撑更长周期的项目开发。

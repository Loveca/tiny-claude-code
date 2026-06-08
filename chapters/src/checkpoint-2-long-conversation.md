# Checkpoint 2: 长对话与会话恢复

> 用一个有三处错误的小项目，完整验证 ch08-10 给 agent 新增的三项能力：上下文控制、对话压缩、会话恢复。

## 本关目标

ch08-10 给 agent 加上了三块基础设施：

| 章节 | 能力 | 本关如何验证 |
|---|---|---|
| ch08 | 上下文预算：自动截断和压缩超长消息 | 多轮修 bug 之后，messages 变长，观察 agent 是否平稳运行 |
| ch09 | `/compact` 手动压缩 | 修完 bug 后，主动调用 `/compact` 把长历史压成摘要 |
| ch10 | session 保存与 `--resume` 恢复 | 退出后重启，确认对话历史和项目记忆都在 |

这三项能力单独测试时意义有限，组合在一个真实工作流里才能看出价值：agent 能否在跨越多个工具调用的长任务里保持稳定，任务完成后能否恢复现场继续工作。

## 项目里有什么

本关使用 [examples/buggy-python-project](../../examples/buggy-python-project)。

```text
examples/buggy-python-project/
  shopping_cart.py
  test_shopping_cart.py
```

`shopping_cart.py` 里有三处故意写错的实现，测试一开始会全部失败。

先自己运行一次，确认失败形状：

```bash
cd examples/buggy-python-project
python -m pytest -q
```

期望看到 3 个测试全部失败：

```text
FAILED test_shopping_cart.py::test_apply_discount_uses_percentage
FAILED test_shopping_cart.py::test_cart_total_uses_quantity
FAILED test_shopping_cart.py::test_free_shipping_threshold_is_inclusive
3 failed in ...s
```

回到项目根目录：

```bash
cd ../..
```

如果你之前已经让 agent 修过这个文件，先还原：

```bash
git checkout examples/buggy-python-project/shopping_cart.py
```

## 第一阶段：修复三处 Bug（制造长对话）

启动 agent：

```bash
python scripts/dev.py run
```

输入：

```text
运行 examples/buggy-python-project 的测试，根据失败信息修复所有 bug，然后重新运行测试确认全部通过
```

agent 理想上会执行这样的动作序列：

```text
bash: python -m pytest examples/buggy-python-project -q
  |
  v (看到 3 个失败)
read: examples/buggy-python-project/test_shopping_cart.py
read: examples/buggy-python-project/shopping_cart.py
  |
  v (分析每个失败的原因)
write: 修复第一处 bug
bash: python -m pytest examples/buggy-python-project -q
  |
  v (还剩 2 个失败)
write: 修复第二处 bug
bash: python -m pytest examples/buggy-python-project -q
  |
  v (还剩 1 个失败)
write: 修复第三处 bug
bash: python -m pytest examples/buggy-python-project -q
  |
  v (全部通过)
```

这个过程产生的消息轮数明显多于 Checkpoint 1。这是有意的，目的是让 messages 累积到足够长，再进入第二阶段。

等 agent 回复"测试全部通过"后，**不要退出**，留在同一个会话里继续。

## 第二阶段：压缩历史

此时 messages 里已经积累了十几轮工具调用和结果。输入：

```text
/compact
```

期望输出类似：

```text
Compacted conversation to N messages.
```

其中 N 远小于修 bug 过程中的消息总数，说明 LLM 已经把长历史压成了摘要。

压缩后，向 agent 确认它仍然记得刚才做的事：

```text
你刚才修了哪些 bug？
```

期望 agent 能描述三处修复内容，说明 `/compact` 保留了关键信息，没有丢失工作记录。

## 第三阶段：保存记忆并退出

在退出前，把这次发现的项目规律记入长期记忆：

```text
/memory add "buggy-python-project" "shopping_cart.py 有三处 bug：apply_discount 未用百分比计算、cart_total 未乘 quantity、is_free_shipping 阈值应为 >= 50"
```

期望输出：

```text
Saved memory: ...buggy-python-project.md
```

用 `/exit` 正常退出，让 session 保存到磁盘：

```text
/exit
```

## 第四阶段：恢复会话

重启 agent，加载最新 session：

```bash
python scripts/dev.py run -- --resume
```

询问 agent 上次做了什么：

```text
上次我们修了什么项目，结果怎样？
```

期望 agent 能描述修复 buggy-python-project 的过程，说明 session 历史（或压缩摘要）已经恢复。

再询问项目记忆是否注入：

```text
shopping_cart.py 里有哪些已知 bug？
```

期望 agent 能直接列出三处 bug，说明第三阶段保存的 memory 已通过 system prompt 注入。

## 观察重点

这个 checkpoint 不是为了考 bug 推理能力，而是为了检查三项基础设施是否协同工作：

**上下文控制（ch08）**
- 多轮修 bug 过程中 agent 是否平稳运行，没有因为 messages 变长而崩溃或截断关键信息

**压缩（ch09）**
- `/compact` 后消息数量是否显著减少
- 压缩后 agent 是否仍然知道刚才的工作内容

**会话与记忆（ch10）**
- `--resume` 之后 agent 是否恢复了正确的上下文
- memory 是否出现在 agent 的回答中

如果任何一步出了问题，不要急着改 prompt。先看：
- session 文件是否存在：`ls .tiny-claude-code/sessions/`
- memory 文件是否存在：`ls .tiny-claude-code/memory/`
- compact 后消息数量是否合理

## 常见问题

### /compact 之后 agent 说不知道刚才做了什么

LLM 摘要丢失了细节。可以在 compact 之前先用 `/memory add` 保存关键结论，摘要作为短期记录，memory 作为长期备份。

### --resume 启动后 agent 回答"我没有上下文"

检查 `/exit` 是否正常执行（Ctrl+C 中断不会保存 session）。重新运行，用 `/exit` 退出而不是强制关闭终端。

### 第四阶段 agent 不知道 bug 详情

如果 `/compact` 把细节压掉了，memory 是补充来源。确认 `/memory add` 已经执行，再确认 memory 文件存在：

```bash
cat .tiny-claude-code/memory/*.md
```

### 修完 bug 后再次运行测试 agent 找不到文件

确认 agent 使用了从项目根目录出发的相对路径，例如 `examples/buggy-python-project`，而不是进入了子目录后使用 `./test_shopping_cart.py`。

## 验收标准

完成以下四步，checkpoint 通过：

**1. Bug 全部修复**

```bash
python -m pytest examples/buggy-python-project -q
```

期望：

```text
3 passed in ...s
```

**2. Compact 生效**

agent 对 `/compact` 的回复中，压缩后消息数 N < 修 bug 时的消息总数。

**3. Session 保存**

```bash
ls .tiny-claude-code/sessions/
```

期望看到至少一个 `.json` 文件。

**4. Resume 可用**

`python scripts/dev.py run -- --resume` 启动后，询问上次工作内容，agent 能描述出 buggy-python-project 的修复过程。

## 思考题

1. `/compact` 和 ch08 的自动 snip 有什么本质区别？什么情况下应该主动压缩而不是等自动触发？
2. session 保存的是完整 messages，memory 保存的是提炼后的知识。如果两者信息冲突，agent 应该相信哪个？
3. 如果 agent 在修第二处 bug 时上下文被自动 snip，第三处 bug 的修复会受到什么影响？
4. 本关的三处 bug 逻辑上相互独立。如果改成依赖关系复杂的多处 bug，会给 session 管理带来什么新挑战？

## 本关小结

ch08-10 的三项能力合在一起，让 agent 从"一次性进程"变成了"可持续工作的系统"：

```text
上下文控制  -> agent 不怕长任务
压缩历史    -> agent 能在有限 token 内保留关键信息
会话恢复    -> agent 能在任务中断后继续
```

后续章节会在这个基础上进一步扩展：ch11 用 todo 系统管理多步骤任务，ch12 用 subagent 把任务分解给独立子进程。任务越复杂，这三项基础设施就越重要。

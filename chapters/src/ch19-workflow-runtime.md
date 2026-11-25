# ch19: Workflow Runtime

> 从"模型决定下一步"到"引擎决定下一步"。

## 本章目标

ch17 的 goal loop 让模型自治：每一轮做什么，由模型看着办。这对开放式任务是对的，但对可重复的流程是错的——写发布说明、跑修复流水线、生成周报，这些事应该每次都按同样的顺序执行、在同一个点停下来等人、留下同样格式的记录。

本章在 harness 上补最后一层：workflow runtime。

```text
release-notes.json          WorkflowManager                registry
┌────────────────┐  run()  ┌──────────────────┐  dispatch  ┌──────────┐
│ collect (tool) │────────>│ 校验 DAG → 调度   │───────────>│ shell    │
│ draft  (agent) │         │ 重试 → 审批 → 落盘 │  agent_loop│ write    │
│ signoff(approval)        └──────────────────┘            │ search   │
│ publish(tool)  │                                          └──────────┘
└────────────────┘
```

完成后，`/workflow release-notes` 会跑 shell 步骤收集提交、agent 步骤起草、在审批节点暂停，等你 approve 之后把 NOTES.md 写进主工作区。

## 先建立心智模型

### workflow 和 agent 的区别

| | agent loop（ch01-ch17） | workflow（本章） |
|---|---|---|
| 控制流 | 模型每轮自己决定 | 引擎按声明的步骤图执行 |
| 节点 | 任意工具调用 | 三种：tool / agent / approval |
| 可重复性 | 两次运行可能走两条路 | 同一输入走同一顺序 |
| 失败处理 | 错误进入对话继续聊 | 重试 → failed，记录在案 |
| 人在回路 | 无 | approval 节点暂停、approve/deny 恢复 |

一句话：agent 是"让它自己干"，workflow 是"把干法写下来，每次照着干"。

### 为什么控制流不该交给模型

goal loop 的每一步都是模型的选择，跑两次可能走两条路。可重复流程的核心诉求是确定性：同样的输入产生同样的步骤顺序。所以把控制流从模型手里拿回引擎——调度、重试、失败判定全部是代码，模型只在 `agent` 步骤里干活。这也让整章测试不需要真实模型：引擎的行为不依赖模型发挥。

### 为什么失败是字符串约定

`ToolRegistry.dispatch` 早就把工具异常包成 `"Error: ..."`（ch04）。tool 步骤直接复用这个约定：结果以 `Error:` 开头就是失败，重试 `max_retries` 次，耗尽则整个 run 标记 `failed`。agent 步骤天然共享约定——`agent_loop` 超出轮次预算时返回的正是 `"Error: maximum number of turns reached."`。不需要新的异常通道，也不需要单独的结果类型。

### 为什么审批是暂停而不是阻塞

引擎从不等待输入。到达 approval 节点时：步骤记为 `waiting`，run 记为 `waiting_approval`，运行记录落盘，然后返回调用方。恢复靠 `approve()`：approve 则继续调度，deny 则把剩余步骤全部 `skipped`、run 标记 `denied`。

"暂停返回"而不是"阻塞等待"，让同一份引擎代码同时服务 REPL、agent 工具和未来的消息队列；审批甚至可以发生在另一个进程——因为记录在磁盘上，新的 `WorkflowManager` 实例能从盘上接手。

### 运行记录

每次状态变化都写 `.tiny-claude-code/workflows/runs/<run_id>.json`：run 状态、每个步骤的 status/attempts/output/error。它是这一章的"session 持久化"（ch10）：同一次执行可查、可续、可追责。

run_id 是 `<name>-<hex8>`。name、step id、run_id 都必须匹配 `[A-Za-z0-9][A-Za-z0-9._-]*`——定义文件永远逃不出 runs 目录，和 ch16 限制成员名是同一个思路。

## 工作流模型

### 步骤 schema

```json
{
  "name": "release-notes",
  "description": "Draft release notes and require sign-off before publishing",
  "steps": [
    {"id": "collect", "type": "tool", "tool": "shell", "input": {"command": "git log --oneline -5"}},
    {"id": "draft", "type": "agent", "prompt": "Draft notes from:\n{outputs.collect}", "depends_on": ["collect"]},
    {"id": "signoff", "type": "approval", "message": "Publish?", "depends_on": ["draft"]},
    {"id": "publish", "type": "tool", "tool": "write", "input": {"path": "NOTES.md", "content": "{outputs.draft}"}, "depends_on": ["signoff"], "max_retries": 1}
  ]
}
```

| 字段 | 适用节点 | 说明 |
|---|---|---|
| `id` | 全部 | 步骤标识，也是输出引用的键 |
| `type` | 全部 | `tool` / `agent` / `approval` |
| `tool`、`input` | tool | registry 分发；input 的字符串值可含 `{outputs.<id>}` |
| `prompt` | agent | 交给 `agent_loop`；可含 `{outputs.<id>}` |
| `message` | approval | 给审批人看的一句话 |
| `depends_on` | 全部 | 依赖的步骤 id 列表 |
| `max_retries` | 全部 | 失败后的额外重试次数，默认 0 |

数据流只有一条规则：任何已完成步骤的输出都可以用 `{outputs.<id>}` 引用，执行时做纯字符串替换。没有表达式语言——定义是用户写的 JSON，别让它有机会变成代码注入。

### 状态机

| 级别 | 值 |
|---|---|
| run | `running` → `waiting_approval` → `done` / `failed` / `denied` |
| step | `pending` → `running` → `done` / `failed` / `skipped` / `waiting` |

失败的 run 会把没跑到的步骤留在 `pending`：记录展示的是"停在哪里"，不是重写过的历史。

### 调度：声明顺序不是执行顺序

每一轮按声明顺序扫描 `pending` 步骤：依赖全部 `done` → 执行；依赖里有 `skipped` → 连带 `skipped`；否则跳过。整轮没有进展 → run `done`。外层循环不断重复，所以步骤声明顺序不必是拓扑序——但图必须是 DAG，`run()` 启动时校验：id 唯一、依赖存在、无环（Kahn 算法）、类型特定字段齐全。

## 本章要实现什么

新增两个文件，接线两处：

- [workflow.py](../../src/tiny_claude_code_ref/workflow.py)：定义解析校验、调度器、重试、审批、运行记录
- [tools/workflow.py](../../src/tiny_claude_code_ref/tools/workflow.py)：三个工作流工具
- [tools/\_\_init\_\_.py](../../src/tiny_claude_code_ref/tools/__init__.py)：`create_default_registry(..., workflow_manager=...)` 接线
- [cli.py](../../src/tiny_claude_code_ref/cli.py)：`/workflow` 命令与 `--workflows` 目录
- [examples/workflows/release_notes.json](../../examples/workflows/release_notes.json)：示例定义

与 ch17 相同的解法：registry 按 run 传入（`WorkflowRunTool(manager, registry)`），避免"registry 需要 manager 建工具、manager 需要 registry 跑步骤"的构造循环。

## 实现路线

### 第一步：定义与校验

```python
definition = parse_definition(json.loads(path.read_text()))
manager.validate(definition)   # 重复 id / 未知依赖 / 环 / 缺字段，启动即报错
```

校验失败在启动时，不在跑到一半时。名字和 id 的字符集检查也在这一步。

### 第二步：调度器与重试

```text
while run is running:
    按声明顺序扫描 pending 步骤
    依赖 skipped -> 连带 skipped
    依赖全 done  -> 执行（attempts = 1 + max_retries，异常转 "Error: ...")
    一轮无进展   -> done
```

### 第三步：agent 步骤

每次尝试用全新的 messages 跑一次 `agent_loop`（`max_turns=4`），hooks 照传——agent 步骤里的工具调用同样过 PreToolUse 权限检查。最终文本就是步骤输出，供下游 `{outputs.<id>}` 引用。

### 第四步：审批与恢复

`run()` 遇到 approval 节点 → `waiting` + 落盘 + 返回。`approve(run_id, approved=...)` 分两条路：approve 把步骤记 `done`（comment 是输出），继续调度；deny 把步骤和所有 `pending` 步骤记 `skipped`，run 记 `denied`。`resume(run_id)` 接手一个停在 `running` 状态的记录——进程中断后从磁盘恢复。

### 第五步：工具与 CLI

用户视角的三个工具：

| 工具 | 作用 |
|---|---|
| `WorkflowRun` | 按名字启动 workflow |
| `WorkflowStatus` | 查看运行记录（默认最近一次） |
| `WorkflowApprove` | approve/deny 等待中的 run |

CLI：`/workflow <name>`、`/workflow status [run_id]`、`/workflow approve <run_id> approve|deny [comment]`、`/workflow resume <run_id>`；`--workflows` 指定定义目录（默认 `.tiny-claude-code/workflows`）。不传 `workflow_manager` 时，默认工具集与以前完全一致。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 19
```

测试覆盖：

- 线性流程与乱序声明的 DAG 调度
- 校验：未知 workflow、重复 id、未知依赖、环、缺 tool/prompt、坏名字、坏 input
- 重试：失败一次后恢复（`attempts=2`）；耗尽 → run `failed`，剩余步骤留在 `pending`
- agent 步骤：mock 客户端驱动有界循环；超轮返回 `Error:` 触发失败路径；`{outputs}` 进入 prompt
- 审批：暂停 → approve → `done`；deny → `denied` + 连带 skipped；重复审批被拒
- 持久化：记录落盘；新 manager 实例从盘上接管审批；`resume` 接手中断的 run
- 工具 schema/execute 与默认 registry 接线（不传 manager 时工具不出现）
- CLI：run/status/approve/deny、用法与错误文本
- 端到端：JSON 定义 → 默认 registry → 审批后把 agent 草稿写入真实文件

## 验收任务

先试一个不需要模型的最小流程（只有 tool 步骤也能跑）：

```bash
mkdir -p .tiny-claude-code/workflows
# 把 examples/workflows/release_notes.json 复制进去，或删掉 draft 步骤自造一个
python scripts/dev.py run --ref
> /workflow release-notes
```

再跑完整示例：

```bash
python scripts/dev.py run --ref --workflows examples/workflows
```

输入：

```text
/workflow release-notes
```

预期行为：`collect`（shell）与 `draft`（agent）完成后，run 停在 `waiting_approval`；`/workflow status` 能看到每步状态和 run_id；`/workflow approve <run_id> approve` 之后 NOTES.md 出现在主工作区。再跑一次试 deny 路径，确认剩余步骤是 `skipped`。

## 常见错误

### 把控制流塞回 prompt

在 agent 步骤的 prompt 里写"如果上一步失败就跳到 X"不会生效——模型不是调度器。需要条件分支，要么拆成不同 workflow，要么扩展引擎（见思考题）。

### 以为声明顺序决定执行顺序

调度只看 `depends_on`。想表达先后关系，写依赖，别靠把步骤排在前面的巧合——乱序声明照样能跑对。

### 无上限的重试

`attempts = 1 + max_retries`。给一个必败工具配 `max_retries: 999`，run 就会烧在这一个步骤上。

### 手改运行记录

runs 目录下的 JSON 是引擎的输出，不是输入。手工编辑后 `resume`/`approve` 会因为结构或状态机不合法直接报错——想改变走向，走工具和 CLI。

### 让 approval 成为终点站

approval 是闸门不是出口。审批节点后面没有步骤的流程，approve 之后什么都不会发生——把最终动作写进依赖它的 publish 步骤。

### 忘记 run 还在等审批

`waiting_approval` 不会自动超时恢复。任何时候 `/workflow status` 都能找回 run_id 和等待中的步骤。

## 思考题

1. 触发器：怎么用已有的 CronScheduler 定时启动 workflow？cron 的 prompt 里如何拿到并传递 run_id？
2. 并行调度：两个互不依赖的步骤现在按声明顺序串行执行。改成线程池时，`_drive` 和 `_save` 哪些位置需要加锁？run 记录的写竞争怎么避免？
3. 条件分支：加一个 `when` 字段（比如"上一步输出包含 FAIL 时跳过"），校验和调度各自要承担什么？
4. 审批升级：多审批人、超时自动 deny、审批意见审计——运行记录的数据结构要怎么扩展？

## Bonus Tasks

- 给 `/workflow status` 加 verbose 输出，展示每步 output 的前几行。
- 支持 `WorkflowRun` 传入 `inputs`，模板里用 `{inputs.<key>}` 引用。
- 给重试加真实退避（间隔参数注入，测试仍可零延迟）。
- 定义文件支持引用公共步骤库，避免多个 workflow 重复同一段。

## 本章小结

workflow runtime 是三件事的组合：

```text
声明图   -> 控制流回到引擎手里，可重复
审批暂停 -> 人在回路，但不阻塞进程
运行记录 -> 同一次执行可查、可续、可追责
```

至此 Part 1-6 的 19 章全部完成：Part 1-5 把一个 agent 从循环搭到长会话，Part 6 把它装上多人协作（ch16）、自治目标（ch17）、外部工具（ch18）和确定编排（ch19）。ch20 再补一层可移植性：换模型服务不用动 harness；ch21 让回答边生成边到达。接下来去哪，见 `docs/ROADMAP.md` 的"后续可选方向"。

# ch16: 多 Agent 团队与 Worktree 隔离

> 从“把活派出去”升级到“和队友持续协作”。

## 本章目标

ch12 的 subagent 是一次性委派：给一个任务，拿一个结果。够用，但它不支持三件事：

- 任务做到一半还想追加要求；
- 多个成员共享一张任务板，而不是各自为战；
- 两个成员同时改同一个仓库而不互相覆盖。

本章在现有 harness 上补一个最小的团队层：

```text
lead ── TeamSpawn ──> alice（独立 transcript + 工具集 + 可选 worktree）
  │                     │
  ├── TeamSend ────────>│  邮箱：任务、追问、进度
  │<──── TeamInbox ─────┤
  ├── TeamWait           │
  └── WorktreeMerge <────┘  把成员的改动合回主工作区
```

完成后，主 agent 可以派两个成员并行修两个 bug，等它们各自完成后把改动合并回来。

## 先建立心智模型

### subagent 和 team 的区别

| | SubAgent（ch12） | Team（本章） |
|---|---|---|
| 交互方式 | 函数调用：传入任务，返回字符串 | 消息驱动：发任务、追问、等结果 |
| 生命周期 | 一次调用内结束 | idle → running → done，可被多次唤醒 |
| 上下文 | 独立 messages，调用完丢弃 | 每个成员持久保存自己的 messages |
| 并发编辑 | 无隔离 | worktree 隔离 |
| 结果传递 | 返回值 | 以 `result` 消息进入 lead 的收件箱 |

一句话：subagent 是“帮我做这件事”，team 是“这个人我留着继续用”。

### 为什么用邮箱而不是返回值

如果成员只能通过返回值沟通，lead 就必须在调用点等着，也没法在成员做到一半时补充信息。邮箱把这个约束解开了：

```text
lead  -> alice: 先修购物车数量
alice -> lead:  找到问题了，但需要确认期望行为
lead  -> alice: 期望是四舍五入到两位小数
alice -> lead:  已修复，result: 修改了 cart.py:42
```

邮箱也是团队协议的最小单位：消息有发送者、接收者、序号和类型。持久化、已读标记、附件都可以在此基础上扩展。

### 为什么需要 worktree

两个成员同时修改同一个文件时，共享 workspace 会发生写覆盖：后写的赢，先写的改动消失。git worktree 让每个成员拥有同一仓库的另一个工作目录和分支：

```text
repo/                          <- lead，主工作区
.tiny-claude-code/worktrees/
  alice/   (branch tiny/team/alice)
  bob/     (branch tiny/team/bob)
```

成员的文件工具和 shell 都绑定到自己的 worktree，lead 在主工作区用 `WorktreeMerge` 决定什么时候合并。worktree 是运行时状态，所以放在已被忽略的 `.tiny-claude-code/` 目录下。

## 团队协议设计

### 成员生命周期

| 状态 | 含义 | 何时进入 |
|---|---|---|
| `idle` | 有活但当前没有被调度 | spawn 完成、工具批次执行完 |
| `running` | 正在执行一轮模型调用 | `step()` 内部，单轮内瞬时 |
| `done` | 给出了最终文本 | 一轮以非 tool_use 结束，文本自动作为 result 发回 lead |
| `error` | 模型调用抛异常 | 异常被捕获并通知 lead |

成员的最终文本会自动以 `result` 消息发回 lead，所以 lead 不应该“等返回值”，而是读收件箱。

### 消息类型

| kind | 用途 |
|---|---|
| `task` | spawn 时排入的初始任务 |
| `message` | 普通追问或进度同步 |
| `result` | 成员的最终答复（自动发送） |

### 调度为什么是同步的

真实的多 agent 系统是异步的：成员在后台运行，消息随时到达。但异步会让测试依赖线程时序，mock 响应顺序不可复现。

本章用确定性调度换取可测试性：

- `step(name)`：为一个成员跑一轮——取走邮箱、调用一次模型、执行这一轮请求的工具；
- `run_round()`：按 spawn 顺序给每个未完成成员各跑一轮；
- `wait(max_rounds)`：重复轮次，直到全部完成或触到硬上限。

这与真实系统的消息协议一致，区别只在“谁来触发下一轮”。升级到线程或队列时，邮箱 API 不需要变。

## 本章要实现什么

新增三个文件，并接线一处：

- [worktree.py](../../src/tiny_claude_code_ref/worktree.py)：git worktree 的创建、列出、删除、合并、清理
- [team.py](../../src/tiny_claude_code_ref/team.py)：消息、成员、邮箱、确定性调度
- [tools/team.py](../../src/tiny_claude_code_ref/tools/team.py)：七个团队工具
- [tools/\_\_init\_\_.py](../../src/tiny_claude_code_ref/tools/__init__.py)：`create_default_registry(..., team_manager=...)` 接线

成员的注册表只有四个文件/shell 工具加 `TeamSend`、`TeamInbox`，**不包含** `TeamSpawn` 和 `SubAgent`——和 ch12 的 depth 守卫同一个思路，防止无限递归。

## 实现路线

### 第一步：worktree 管理器

对 git 命令做一层薄封装：

```python
manager = WorktreeManager(repo)
path = manager.create("alice")   # git worktree add -b tiny/team/alice <root>/alice HEAD
manager.list()                   # 只返回 root 下的工作树
manager.merge("alice")           # 冲突时 git merge --abort，返回错误文本
manager.cleanup()                # 删除全部工作树和分支
```

非 git 仓库时 `create` 必须报错，而不是悄悄共享目录。

### 第二步：成员与邮箱

```python
member = team.spawn("alice", "bug fixer", task="fix the cart", isolate=True)
team.send("lead", "alice", "expected two decimals")
team.inbox("alice")   # 读取并清空
```

`lead` 是保留名；成员名只允许字母、数字和 `._-`，避免路径逃逸。

### 第三步：成员 registry

每个成员有独立的 `ToolRegistry`：

```text
bash, read, write, search  -> 全部绑定到 member.workspace
TeamSend, TeamInbox        -> 绑定到 member.name
```

`isolate=True` 时，`member.workspace` 指向 worktree；否则指向主工作区。

### 第四步：确定性调度

`step()` 是本章的核心。它把 agent loop 的一轮拆开，以便在轮次之间注入邮箱消息：

```text
取走邮箱 -> 追加 user 消息 -> 调一次模型 -> 有 tool_use 就跑工具
        -> 无 tool_use 则标记 done 并把文本发给 lead
```

注意 keep role alternation：如果最后一条已经是 user 消息，新邮件要合并进去，而不是再追加一条 user。

### 第五步：团队工具与接线

lead 视角的七个工具：

| 工具 | 作用 |
|---|---|
| `TeamSpawn` | 创建成员并排入任务 |
| `TeamSend` | 发消息（支持 `to="all"` 广播） |
| `TeamInbox` | 读收件箱 |
| `TeamStatus` | 查看状态和未读数 |
| `TeamWait` | 推进轮次直到完成或触顶 |
| `TeamShutdown` | 结束成员并清理 worktree |
| `WorktreeMerge` | 合并成员分支，冲突即中止 |

不传 `team_manager` 时，默认工具集与以前完全一致。

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 16
```

测试覆盖：

- 创建 worktree、列出、删除、合并，以及冲突时中止
- 非 git 仓库或非法成员名被拒绝
- 邮箱：发送、读取并清空、广播、未知收件人、空消息
- 成员生命周期：最终文本自动以 `result` 进入 lead 收件箱
- 工具批次执行后成员保持 `idle`，下一轮继续
- `wait` 的轮次上限，以及无任务成员不调用模型
- 成员看不到 `TeamSpawn` 和 `SubAgent`
- registry 只在传入 `team_manager` 时注册团队工具
- 端到端：lead 依次调用 `TeamSpawn` → `TeamWait`，两个成员在独立 worktree 写入不同内容

## 验收任务

用真实模型跑一次：

```bash
python scripts/dev.py run --ref
```

输入：

```text
创建一个两人团队，alice 和 bob，各自在独立 worktree 里分别给 README 加一行英文简介和一行中文简介，等他们都完成后合并两个分支。
```

预期行为：`TeamSpawn(isolate=true)` 两次 → `TeamWait` → `WorktreeMerge` 两次 → `TeamShutdown`，主工作区出现两行新增内容。

## 常见错误

### 成员死循环

成员每一轮都可能继续请求工具。没有轮次上限时，`wait` 永远不会返回。始终保留硬上限。

### 收件箱不 drain

`inbox()` 默认读取即清空。如果只读不清，成员每轮都会看到同一条任务，重复执行。

### worktree 泄漏

成员结束但没有删除 worktree，`git worktree list` 会持续增长。`shutdown` 和 `cleanup` 必须幂等。

### 让成员也能 spawn

成员如果能 `TeamSpawn`，团队会指数膨胀。成员 registry 只保留文件工具和邮箱工具。

### 用返回值代替结果消息

lead 不应该依赖成员调用的返回值；团队的结果约定是收件箱里的 `result` 消息。

## 思考题

1. 如果要把同步调度换成真正的异步执行，邮箱 API 需要改什么？
2. 成员之间的消息是否应该允许？如果允许，如何避免死锁？
3. worktree 合并冲突时，应该由 lead 自动解决，还是升级为人工审批？
4. 团队状态如何持久化到 session，使重启后可以继续？

## Bonus Tasks

- 给 `TeamStatus` 增加最近一条消息的摘要。
- 支持 `TeamSend` 的 `to` 使用通配符，定向广播给某一角色的成员。
- 为 `wait` 增加进度回调，把每轮结果实时打印到 CLI。
- 让成员在完成前必须显式调用一次 `TeamSend(to="lead")`，否则视为 error。

## 本章小结

团队能力不是“多开几个模型”，而是三件事的组合：

```text
邮箱    -> 让协作可以持续
调度    -> 让协作可复现、可测试
worktree -> 让并行编辑互不覆盖
```

下一章会把注意力从“多个人”转到“很长时间”：让一个 agent 围绕持久目标跨会话持续推进。

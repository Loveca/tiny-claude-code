# tiny-claude-code 课程大纲 v2

## 设计原则

1. **骨架代码 + 参考实现物理分离**（`tiny_claude_code/` vs `tiny_claude_code_ref/`），不用 git 分支
2. **两层验证**：单元测试（mock LLM，自动）+ 验收任务（真实 LLM，手动）
3. **函数级 TODO**：签名完整、类型注解完整、函数体 `raise NotImplementedError`
4. **时间线注释**：骨架代码中标注"ch09 你还要回来改这个函数"
5. **测试按章节释放**：`python scripts/dev.py test --ch 01`

## 目录结构

```
tiny-claude-code/
├── src/
│   ├── tiny_claude_code/           # 学生骨架代码
│   │   ├── __init__.py
│   │   ├── agent.py                # ch01: agent_loop
│   │   ├── cli.py                  # ch01: REPL 入口
│   │   ├── llm.py                  # ch01: Anthropic client 封装
│   │   ├── tools/
│   │   │   ├── __init__.py         # ch04: ToolRegistry
│   │   │   ├── base.py             # ch04: Tool 抽象基类
│   │   │   ├── shell.py            # ch02: bash tool
│   │   │   ├── file_read.py        # ch03: read / list
│   │   │   ├── file_write.py       # ch03: write / edit
│   │   │   └── search.py           # ch03: glob / grep
│   │   ├── permissions.py          # ch05: 三层权限闸门
│   │   ├── hooks.py                # ch06: Hook 事件系统
│   │   ├── error_recovery.py       # ch07: 重试与降级
│   │   ├── context.py              # ch08: 上下文预算
│   │   ├── compact.py              # ch09: /compact 压缩
│   │   ├── session.py              # ch10: 会话持久化
│   │   ├── memory.py               # ch10: 长期记忆
│   │   ├── tasks.py                # ch11: Todo + Task
│   │   ├── subagent.py             # ch12: 子 Agent
│   │   ├── background.py           # ch13: 后台任务
│   │   ├── cron.py                 # ch13: 定时调度
│   │   └── skills.py               # ch15: Skill 加载
│   └── tiny_claude_code_ref/       # 参考实现（同结构，完整代码）
├── tests_all/                      # 全部章节测试（仓库持有）
│   ├── test_ch01.py
│   ├── test_ch02.py
│   └── ...
├── tests/                          # 当前已释放的测试（学生工作区）
├── conftest.py                     # mock LLM client + 公共 fixture
├── chapters/                       # 教材（mdbook 源码）
│   └── src/
│       ├── SUMMARY.md              # 目录
│       ├── ch01-agent-loop.md
│       ├── ch02-shell-tool.md
│       └── ...
├── book.toml
├── examples/                       # 供 Agent 操作的示例项目
│   ├── buggy-python-project/       # ch14 验收用
│   └── tiny-web-app/              # ch15 验收用
├── scripts/
│   └── dev.py                      # test --ch N, run, check
├── pyproject.toml
├── requirements.txt                # anthropic, python-dotenv, pyyaml, pytest, mdbook
├── .env.example
└── README.md
```

## 章节大纲

### Part 1: 最小可用 Agent（ch01-04）

完成 Part 1 后，学生拥有一个能对话、能执行命令、能读写文件的 coding agent。

---

#### ch01: Agent Loop + CLI

**概念**：Agent 的本质是一个 while 循环 — 模型要么回复文字（结束），要么调用工具（继续）。

**学生实现**：
- `llm.py`: `LLMClient` 类 — 封装 Anthropic SDK，`chat(messages, tools)` 方法
- `agent.py`: `agent_loop(messages, tools, client)` — while True 循环
  - 调用 LLM → 追加 assistant message
  - `stop_reason != "tool_use"` → break，返回文本
  - 执行工具调用 → 追加 tool_result → 继续循环
- `cli.py`: `main()` — REPL：读取用户输入 → 调用 agent_loop → 打印回复

**单元测试**（mock LLM）：
- mock 返回纯文本 → 循环立即结束
- mock 返回 tool_use → 执行 handler → mock 返回文本 → 循环结束
- mock 连续返回 2 次 tool_use → 循环执行 2 次工具后结束
- 空消息列表 → 正确处理

**验收**：`tiny-claude-code "用一句话解释什么是 Agent"`

---

#### ch02: Shell Tool

**概念**：第一个工具让 Agent 从"只会说话"变成"能动手"。

**学生实现**：
- `tools/shell.py`: `ShellTool` 类
  - `schema` 属性 — 返回 Anthropic tool schema
  - `execute(command, timeout=30)` — subprocess.run + stdout/stderr 捕获
  - `validate_command(command)` — 基础安全检查（空命令、超长命令）
- `agent.py` 中集成：hardcoded `TOOL_HANDLERS = {"bash": ShellTool()}`

**单元测试**（mock LLM）：
- 执行 `echo hello` → 输出包含 "hello"
- 执行不存在的命令 → 返回非零退出码 + stderr
- 空命令 → validate 拒绝
- 超时命令 → 被截断

**验收**：`tiny-claude-code "列出当前目录文件，告诉我这是什么项目"`

---

#### ch03: File Tools

**概念**：Agent 能读代码才能理解项目，能写代码才能修改项目。

**学生实现**：
- `tools/file_read.py`: `ReadTool`
  - `execute(path, offset, limit)` — 读取文件内容，支持行号范围
  - `safe_path(path, workspace)` — 路径安全检查（禁止 `../` 越界）
- `tools/file_write.py`: `WriteTool`
  - `execute(path, content)` — 写入新文件
  - `execute(path, old_text, new_text)` — 精确替换编辑
- `tools/search.py`: `SearchTool`
  - `execute(pattern, path, type)` — glob 文件搜索 + grep 内容搜索

**单元测试**（mock LLM）：
- safe_path 正常路径 → 通过
- safe_path `../../etc/passwd` → 拒绝
- read 存在文件 → 返回内容
- read 不存在文件 → 返回错误
- write 新文件 → 文件创建成功
- edit 精确替换 → 内容正确更新
- edit old_text 不匹配 → 返回错误不修改文件
- glob `*.py` → 返回匹配文件列表

**验收**：`tiny-claude-code "阅读 README.md 并总结项目用途"`

---

#### ch04: Tool Registry 重构

**概念**：从硬编码分发升级为可扩展注册表，为后续加工具做准备。

**学生实现**：
- `tools/base.py`: `Tool` 抽象基类 — `schema` 属性 + `execute()` 方法
- `tools/__init__.py`: `ToolRegistry` 类
  - `register(tool)` — 注册工具实例
  - `get_schemas()` — 返回所有工具的 Anthropic schema 列表
  - `dispatch(name, input)` — 根据 name 查找 handler 并执行
- 重构 `agent.py`：用 `registry` 替代 hardcoded `TOOL_HANDLERS`
- 重构已有工具：`ShellTool`、`ReadTool`、`WriteTool`、`SearchTool` 继承 `Tool`

**单元测试**（mock LLM）：
- register 一个工具 → get_schemas 包含它
- register 3 个工具 → get_schemas 返回 3 项
- dispatch 已注册工具 → 执行成功
- dispatch 未注册工具 → 返回错误信息
- 重复注册同名工具 → 覆盖旧工具

**验收**：`tiny-claude-code "创建 hello.py 写入 print('hello')，然后运行它"` （与 ch03 行为相同，但内部架构更干净）

---

### ⚡ Checkpoint 1: 你的 Agent 第一次修 Bug

**位置**：Part 1 和 Part 2 之间
**性质**：不引入新代码，纯体验 — 用前 4 章构建的 Agent 修一个真实 bug

**内容**：
- 提供 `examples/simple-bug/` — 一个 Python 文件，包含一个 off-by-one 错误
- 有对应的 pytest 测试，运行会失败
- 教材引导：`tiny-claude-code "运行 examples/simple-bug/ 的测试，根据报错修复代码"`
- 3 分钟搞定，成功率接近 100%

**目的**：爽感 — 让学生第一次体验到"我自己写的 Agent 真的修了一个 bug"

---

### Part 2: 安全与健壮（ch05-07）

完成 Part 2 后，Agent 有了安全边界，不会误操作，遇到 API 错误能自动恢复。

---

#### ch05: Permission System

**概念**：Agent 有能力不代表有权限 — 危险操作必须经过审批。

**学生实现**：
- `permissions.py`: `PermissionManager` 类
  - Gate1 `_check_deny_list(tool, input)` — 硬拒绝列表（rm -rf /, :(){:|:&}, 等）
  - Gate2 `_check_rules(tool, input)` — 规则匹配（路径白名单/黑名单）
  - Gate3 `_prompt_user(tool, input)` — 交互式用户审批（y/n/always）
  - `check(tool_use_block)` → 串联三道闸门，任一拒绝则返回拒绝理由
  - `always` 记忆 — 同参数不再询问
- 集成到 `agent.py`：工具执行前调用 `permission.check()`

**单元测试**（mock LLM + mock 用户输入）：
- 黑名单命令 → Gate1 直接拒绝
- 路径越界 → Gate2 拒绝
- 正常操作 → Gate3 询问 → mock "y" → 通过
- always 选择 → 下次同参数自动通过
- 三道闸门短路：Gate1 拒绝 → Gate2/3 不执行

**验收**：`tiny-claude-code "读取 ../secret.txt"` → 被拒绝

---

#### ch06: Hook System

**概念**：把权限检查从循环硬编码中解耦 — 挂在循环上，不写进循环里。

**学生实现**：
- `hooks.py`: `HookSystem` 类
  - `register(event, callback, priority=0)` — 注册 Hook 回调
  - `trigger(event, *args)` → 按优先级执行，任一返回非 None 则短路
  - 4 个事件：`UserPromptSubmit` / `PreToolUse` / `PostToolUse` / `Stop`
- 重构 `permissions.py` 为 `PreToolUse` Hook
- 新增日志 Hook：`PostToolUse` 记录工具调用，`Stop` 记录会话摘要
- 重构 `agent.py`：用 `hooks.trigger("PreToolUse", ...)` 替代硬编码权限检查

**单元测试**（mock LLM）：
- 注册 2 个 Hook → trigger 按优先级执行
- PreToolUse Hook 返回 "denied" → 工具不执行，后续 Hook 跳过
- PostToolUse Hook 收到正确的 tool name 和 result
- Stop Hook 在循环结束时触发
- 无 Hook 注册 → trigger 返回 None，正常执行

**验收**：行为与 ch05 相同，但代码结构更干净 — 权限是 Hook 而非硬编码

---

#### ch07: Error Recovery

**概念**：Agent 面对错误不能崩溃 — 重试、降级、保底。

**学生实现**：
- `error_recovery.py`: `ErrorHandler` 类
  - 429 Rate Limit → 指数退避重试（2s, 4s, 8s，最多 3 次）
  - 529 Overload → 等待 Retry-After 后重试
  - Token 超限 → 自动升级 max_tokens（8K → 16K → 32K → 64K）
  - Fallback 模型链 → 主模型失败切换备用模型
  - 最大轮次保护 → agent_loop 超过 50 轮强制停止
- 集成到 `agent.py`：LLM 调用被 ErrorHandler 包裹

**单元测试**（mock LLM 返回错误）：
- 连续 429 → 重试 3 次后返回错误
- 429 → 429 → 200 → 重试 2 次后成功
- 529 带 Retry-After: 5 → 等待 5 秒后重试
- token 超限 → max_tokens 自动升级
- 超过 50 轮 → 强制停止并提示
- malformed tool_use（缺少 tool_use_id）→ 返回错误不崩溃

**验收**：手动触发 429（用低 rate limit key），观察自动重试

---

### Part 3: 上下文与记忆（ch08-10）

完成 Part 3 后，Agent 能长时间工作 — 上下文不会溢出，会话能恢复，有长期记忆。

---

#### ch08: Context Budget

**概念**：上下文窗口是有限资源 — 必须在耗尽前主动回收。

**学生实现**：
- `context.py`: `ContextManager` 类
  - `estimate_tokens(messages)` — 简易 token 估算（字符数 / 4）
  - `trim_tool_output(messages, max_chars)` — 截断过长的工具输出
  - `snip_old_messages(messages, keep_head, keep_tail)` — 裁掉中间旧消息
  - `compact(messages)` — 管线：trim → snip → 检查是否仍超限
- 集成到 `agent.py`：每次 LLM 调用前检查并压缩

**单元测试**（mock LLM）：
- estimate_tokens 与字符数成正比
- trim_tool_output → 超长输出被截断并附 "[truncated]"
- snip_old_messages → 中间消息被移除，首尾保留
- compact 管线 → 总 token 下降
- 空消息列表 → 不崩溃

**验收**：让 Agent 连续执行 20+ 次工具调用，不报 token 超限错误

---

#### ch09: /compact

**概念**：当裁剪不够用时，让 LLM 自己总结历史 — 用一次 API 调用换取大量上下文空间。

**学生实现**：
- `compact.py`: `CompactManager` 类
  - `summarize(messages, client)` — 调用 LLM 生成对话摘要
  - `build_compact_messages(summary, recent_messages)` — 摘要 + 最近消息
  - `/compact` 命令处理 — 在 REPL 中触发手动压缩
- 集成到 `context.py`：snip 后仍超限 → 自动触发 compact

**单元测试**（mock LLM 返回摘要）：
- summarize → 调用 LLM 并返回摘要文本
- build_compact_messages → 新消息列表包含摘要 + 最近 N 条
- /compact → 消息数量显著减少
- 自动触发 → token 超限时自动调用 compact

**验收**：长对话中输入 `/compact`，Agent 能继续正常工作

---

#### ch10: Session & Memory

**概念**：会话让 Agent 跨退出恢复，记忆让 Agent 跨项目积累经验。

**学生实现**：
- `session.py`: `SessionManager` 类
  - `save(session_id, messages, metadata)` — 保存到 `.tiny-claude-code/sessions/`
  - `load(session_id)` → 恢复 messages
  - `list_sessions()` → 列出所有会话
  - `--resume` CLI 参数 → 自动加载最近会话
- `memory.py`: `MemoryManager` 类
  - `save(category, title, content)` — 写入 `.tiny-claude-code/memory/`（YAML frontmatter + Markdown）
  - `load_relevant(query)` → 关键词匹配加载相关记忆
  - `build_index()` → 重建 `MEMORY.md` 索引
  - 启动时加载 → 记忆注入 system prompt

**单元测试**（文件系统 mock）：
- save → 文件存在且内容正确
- load → 恢复完整的 messages 列表
- list_sessions → 返回按时间排序的会话列表
- memory save → YAML frontmatter 格式正确
- memory load_relevant → 关键词匹配返回正确记忆
- build_index → MEMORY.md 包含所有记忆条目

**验收**：
- 退出 tiny-claude-code → `tiny-claude-code --resume` → 继续上次对话
- `/memory add "这个项目用 pytest"` → 下次启动 Agent 知道用 pytest

---

### ⚡ Checkpoint 2: 长对话 + 会话恢复

**位置**：Part 3 和 Part 4 之间
**性质**：不引入新代码，纯体验 — 验证上下文管理和会话恢复的实战效果

**内容**：
- 让 Agent 执行一个需要 10+ 次工具调用的任务（如"分析这个项目的所有 Python 文件，列出每个文件的函数名"）
- 中途输入 `/compact` 观察压缩效果
- 退出后 `tiny-claude-code --resume` 恢复会话继续工作
- 对比：有 /compact 和没 /compact 的上下文消耗差异

**目的**：验证 Part 3 的机制真的有用 — 不只是测试通过，而是实际改善了 Agent 的工作能力

---

### Part 4: 任务与协作（ch11-13）

完成 Part 4 后，Agent 能管理复杂任务、委派子任务、异步执行。

---

#### ch11: Todo & Task System

**概念**：没有计划的 Agent 走哪算哪 — 任务系统让 Agent 有目标、有进度。

**学生实现**：
- `tasks.py`: `TaskManager` 类
  - `TodoWrite` 工具 — 创建/更新 todo 项
  - todo 状态机：`pending` → `in_progress` → `completed`
  - 同一时间只能有一个 `in_progress`
  - `blockedBy` 依赖 — 被阻塞的任务不能启动
  - 任务提醒 — 连续 3 轮无 todo 更新 → 注入 prompt 提醒
  - 持久化 — `.tiny-claude-code/tasks/{id}.json`

**单元测试**（mock LLM）：
- create → 状态为 pending
- 同一时间只能一个 in_progress → 第二个自动 pending
- blockedBy → 依赖未完成时 blocked
- 依赖完成 → 自动 unblocked
- 连续 3 轮无更新 → 提醒注入消息

**验收**：`tiny-claude-code "给这个项目添加一个 .gitignore 文件"` — Agent 自动创建 todo 并逐步完成

---

#### ch12: Subagent

**概念**：大任务拆小 — 子 Agent 有干净的上下文，完成后只回传摘要。

**学生实现**：
- `subagent.py`: `SubAgent` 类
  - `spawn(task_description, client, tools)` → 创建独立 messages[]
  - 轮次上限 30 轮 → 防止失控
  - 禁止递归 → 最多 1 层子 Agent
  - 完成后只返回摘要文本 → 主 Agent 上下文不被污染
  - `SubAgent` 工具 — 供 LLM 调用触发子任务

**单元测试**（mock LLM）：
- spawn → 子 Agent 返回摘要
- 超 30 轮 → 强制截断返回
- 递归检测 → 拒绝第二层派生
- 子 Agent 工具调用 → handler 正确执行

**验收**：`tiny-claude-code "搜索项目中所有 TODO 注释并汇总"` — Agent 派生子 Agent 搜索，主 Agent 汇总

---

#### ch13: Background & Cron

**概念**：慢操作不阻塞思考，定时任务不需要人推。

**学生实现**：
- `background.py`: `BackgroundManager` 类
  - `submit(command)` → 后台线程执行，返回 task_id
  - `poll(task_id)` → 查询状态
  - `get_result(task_id)` → 获取完成结果
  - 完成通知 → 注入下一轮消息
- `cron.py`: `CronScheduler` 类
  - `schedule(expression, prompt)` → 注册 cron 任务
  - 简易 cron 解析 — 5 字段（分 时 日 月 周）
  - 轮询线程 — 每分钟检查
  - durable 持久化 → `.tiny-claude-code/scheduled_tasks.json`

**单元测试**（mock 时间）：
- submit → 立即返回 task_id，主线程不阻塞
- 后台完成 → poll 返回 completed + 结果
- cron 解析 `"*/5 * * * *"` → 正确匹配
- durable → 文件存在且可恢复
- 多任务并发 → 通知按完成顺序到达

**验收**：`tiny-claude-code "在后台运行 pytest -q"` → 主 Agent 继续对话，测试结果稍后到达

---

### Part 5: 实战与扩展（ch14-15）

完成 Part 5 后，学生用自己写的 Agent 解决真实问题，并学会扩展它。

---

#### ch14: 真实项目挑战

**概念**：用自己造的工具解决真实问题 — 这才是最终验收。

**内容**：
- 不引入新代码，提供 3 个挑战场景：
  1. `examples/buggy-python-project/` — 有 3 个测试失败，用 tiny-claude-code 修复
  2. `examples/tiny-web-app/` — 有一个简单 Flask 应用，用 tiny-claude-code 添加路由
  3. 自己项目的真实任务 — 用 tiny-claude-code 完成一次代码审查
- 教材中给出引导提示和诊断方法
- 学生发现 Agent 的不足 → 引出 ch15 的扩展需求

**验收**：至少修复 `buggy-python-project` 的所有测试

---

#### ch15: Skill & 插件扩展

**概念**：能力不够？按需加载技能，插上外部工具。

**学生实现**：
- `skills.py`: `SkillLoader` 类
  - `list_skills()` → 扫描 `.tiny-claude-code/skills/` 目录
  - `load(skill_name)` → 读取 SKILL.md，注入 system prompt
  - 两层加载：目录摘要（100 token）+ 完整内容（按需）
- 插件系统：
  - `tools/plugin.py`: `PluginLoader` 类
  - `load_plugins(plugin_dir)` → 动态导入 Python 模块
  - 插件接口：`def register_tools(registry: ToolRegistry)`
  - 示例插件：`examples/plugins/weather.py`

**单元测试**（文件系统 mock）：
- list_skills → 返回可用技能列表
- load → SKILL.md 内容正确注入
- 插件注册 → registry 包含新工具
- 插件调用 → 正确执行
- 无效插件 → 不崩溃，跳过并警告

**验收**：`tiny-claude-code "使用 python-debugging skill 帮我调试"` — Agent 加载技能后给出更好的调试建议

---

## 每章标准结构

```
chapters/src/chXX-name.md
  1. 本章目标（一段话）
  2. 核心概念（配流程图）
  3. 需要修改的文件 + 函数清单
  4. 实现提示（伪代码级别，不给答案）
  5. 运行测试：python scripts/dev.py test --ch XX
  6. 验收任务（用真实 LLM 手动验证）
  7. 思考题（无标准答案）
  8. Bonus Tasks（可选挑战）
```

## 学生工作流

```bash
git clone https://github.com/xxx/tiny-claude-code
cd tiny-claude-code
pip install -r requirements.txt
cp .env.example .env        # 填入 ANTHROPIC_API_KEY

# 学习 ch01
cat chapters/src/ch01-agent-loop.md    # 阅读教材
# 编辑 src/tiny_claude_code/agent.py ...       # 实现 TODO
python scripts/dev.py test --ch 01     # 跑单元测试
python scripts/dev.py run              # 跑验收任务

# 卡住了？
diff src/tiny_claude_code/agent.py src/tiny_claude_code_ref/agent.py  # 看参考实现差异
```

## 工具链命令

```bash
python scripts/dev.py test --ch 01        # 跑指定章节测试
python scripts/dev.py test --all          # 跑全部测试
python scripts/dev.py run                 # 运行 tiny-claude-code（真实 LLM）
python scripts/dev.py run --ref           # 用参考实现运行
python scripts/dev.py check               # 检查还有哪些 TODO 未完成
```

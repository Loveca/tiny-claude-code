# ch15: Skills and Plugins

> 当 agent 不够懂某类任务时，不要把所有知识写死到核心里。

## 本章目标

最后一章实现两个扩展点：

- `SkillLoader`：从本地 `SKILL.md` 加载任务知识。
- `PluginLoader`：从 Python 文件动态注册新工具。

这让 agent 的核心保持小，但可以按项目需要扩展能力。

## 问题：核心 agent 不可能内置所有知识和能力

一个固定 agent 可以完成通用任务，但真实使用时会遇到大量场景差异：Python 调试、前端构建、数据库迁移、浏览器操作、公司内部系统、特定代码规范。把所有知识写进核心 prompt 会让上下文膨胀；把所有能力写进核心代码会让工具边界失控。

需要分清两件事：

- 有些扩展只是“告诉 agent 怎么做”，例如调试流程、代码审查清单。
- 有些扩展是“让 agent 能做新事情”，例如调用浏览器、访问 GitHub、查询外部 API。

前者更适合 Skill，后者更适合 Plugin。

## 解决方案：知识按需加载，能力显式注册

```text
Skill
  SKILL.md
  references/
  scripts/
  -> injected into prompt when relevant

Plugin
  Python module / connector
  register_tools(registry)
  -> adds executable tools
```

Skill 的重点是渐进披露：先读短说明，需要时再打开模板或脚本。Plugin 的重点是明确能力边界：注册了哪些工具、需要哪些权限、失败时如何报告。

## 为什么要区分 Skills 和 Plugins

走到 ch15，agent 已经有了固定的一组工具和运行时能力。下一步问题是扩展：不同项目、团队和任务需要不同知识，不可能全部写进核心代码，也不应该全部塞进 system prompt。

Skill 更像可加载的知识包。它告诉 agent 在某类任务里应该遵循什么流程、参考哪些文件、怎样渐进读取上下文。好的 Skill 会控制信息量：先读入口说明，需要时再打开模板、脚本或参考资料，而不是一开始把所有内容注入上下文。

Plugin 更像能力边界清晰的外部系统。它可能提供 MCP 工具、连接器、浏览器能力或第三方服务访问。和 Skill 相比，Plugin 不只是“告诉模型怎么做”，还会把新的可执行能力接入 harness，因此更需要权限、审计和配置边界。

这一区分很重要：知识可以指导模型，能力必须由本地运行时控制。把二者分开，agent 才能既容易扩展，又不把安全边界交给提示词。

## 工作原理

SkillLoader 可以先扫描目录，读取每个 skill 的名称和简介。只有当用户请求或模型需要时，才加载完整 `SKILL.md`：

```python
skills = skill_loader.list_skills()
selected = skill_loader.load("python-debugging")
system_prompt += selected.instructions
```

PluginLoader 则走工具注册路径：

```python
module = import_plugin(path)
module.register_tools(registry)
```

这两个入口都能扩展 agent，但风险级别不同。Skill 主要消耗上下文并影响模型行为；Plugin 会增加真实可执行动作，所以必须经过工具 schema、权限系统和 Hook 事件。

## 相对 ch14 的变化

| 组件 | ch14 | ch15 |
| --- | --- | --- |
| 目标 | 用现有 agent 做真实挑战 | 让 agent 可扩展 |
| 知识来源 | 固定教材和 prompt | 按需加载 Skills |
| 能力来源 | 内置工具 | Plugins 注册新工具 |
| 安全重点 | 挑战中观察边界 | 扩展也必须走权限和工具协议 |

## Skills

Skill 目录格式：

```text
.tiny-claude-code/skills/python-debugging/SKILL.md
```

`SkillLoader` 提供：

- `list_skills()`：扫描所有 skill。
- `load(skill_name)`：读取完整 `SKILL.md`。
- `build_system_context(skill_names)`：生成 system prompt 片段。

CLI 支持：

```bash
python scripts/dev.py run -- --skill python-debugging
```

REPL 支持：

```text
/skill list
/skill show python-debugging
```

仓库还提供了示例 skill：

```text
examples/skills/python-debugging/SKILL.md
```

## Plugins

插件是普通 Python 文件，暴露一个函数：

```python
def register_tools(registry):
    registry.register(MyTool())
```

默认插件目录：

```text
.tiny-claude-code/plugins/
```

也可以用 CLI 指定：

```bash
python scripts/dev.py run -- --plugins examples/plugins
```

示例插件：

```text
examples/plugins/weather.py
```

它注册了一个 deterministic `weather` 工具，方便本地测试插件机制。

## 实现路线

### 第一步：扫描 skill 目录

先只读取 skill 名称和摘要，不要一开始加载所有内容。这样才能做到渐进披露。

### 第二步：加载 SKILL.md

当用户明确要求或 agent 判断相关时，再把完整 skill 注入 system prompt 或上下文。

### 第三步：定义 plugin 接口

Plugin 不应该随便修改全局状态。最小接口是 `register_tools(registry)`，让插件通过工具注册表暴露能力。

### 第四步：失败时跳过无效插件

插件加载失败不应该让整个 agent 崩溃。记录错误、跳过插件、继续启动。

## 测试讲解

Skill 测试要区分“发现 skill”和“加载完整 skill”。这能保证目录扫描不会把大量知识一次性塞进上下文。

Plugin 测试要验证工具真的注册进 registry，并且无效插件会被跳过。插件系统的重点是可扩展，但不能牺牲启动稳定性。

## 常见错误

### 把 Skill 当成工具

Skill 是知识，不是可执行动作。它指导模型，但不能直接产生副作用。

### 插件绕过工具协议

Plugin 增加能力时仍然应该注册成 Tool，走 schema、dispatch、权限和 hook。

### 一次性加载所有 Skill

这会迅速污染上下文。Skill 的价值在于按需加载，而不是把资料库全塞给模型。

## 运行测试

```bash
python scripts/dev.py test --ch 15
```

测试覆盖：

- skill 列表和完整加载
- skill summary 和 system prompt 注入
- `/skill list` 与 `/skill show`
- plugin 注册工具
- 无效 plugin 不崩溃
- 默认 registry 加载 plugin

## 设计边界

Skill 是知识，Plugin 是能力。

- Skill 适合写流程、约束、项目约定、调试方法。
- Plugin 适合接入新的工具、API、计算逻辑。

不要把一次性任务写成插件，也不要把需要执行代码的能力伪装成 skill。

## 本章小结

ch15 给 tiny-claude-code 留下了扩展出口。核心 agent 仍然很小，但它现在可以通过 skill 学习任务流程，通过 plugin 获得新工具。

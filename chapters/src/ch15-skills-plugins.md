# ch15: Skills and Plugins

> 当 agent 不够懂某类任务时，不要把所有知识写死到核心里。

## 本章目标

最后一章实现两个扩展点：

- `SkillLoader`：从本地 `SKILL.md` 加载任务知识。
- `PluginLoader`：从 Python 文件动态注册新工具。

这让 agent 的核心保持小，但可以按项目需要扩展能力。

## 为什么要区分 Skills 和 Plugins

走到 ch15，agent 已经有了固定的一组工具和运行时能力。下一步问题是扩展：不同项目、团队和任务需要不同知识，不可能全部写进核心代码，也不应该全部塞进 system prompt。

Skill 更像可加载的知识包。它告诉 agent 在某类任务里应该遵循什么流程、参考哪些文件、怎样渐进读取上下文。好的 Skill 会控制信息量：先读入口说明，需要时再打开模板、脚本或参考资料，而不是一开始把所有内容注入上下文。

Plugin 更像能力边界清晰的外部系统。它可能提供 MCP 工具、连接器、浏览器能力或第三方服务访问。和 Skill 相比，Plugin 不只是“告诉模型怎么做”，还会把新的可执行能力接入 harness，因此更需要权限、审计和配置边界。

这一区分很重要：知识可以指导模型，能力必须由本地运行时控制。把二者分开，agent 才能既容易扩展，又不把安全边界交给提示词。

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

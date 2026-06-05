# ch15: Skills and Plugins

> Skill 给 agent 加知识，plugin 给 agent 加工具。

## 本章目标

ch14 的真实项目挑战会暴露一个问题：agent 的基础机制已经有了，但它不一定懂某个领域的最佳实践，也不一定拥有某个外部能力。

本章实现两种扩展：

- `SkillLoader`：从 `SKILL.md` 加载领域指导，注入 system prompt
- `PluginLoader`：从 Python 插件动态注册新工具

```text
Skill  -> 改变模型知道什么、如何做
Plugin -> 改变模型能调用什么工具
```

二者互补。调试 Python 项目可能需要 skill；查询天气、调用内部 API、操作数据库可能需要 plugin。

## 先建立心智模型

### Skill 是文本能力

Skill 本质上是一份 Markdown 指南：

```text
.tiny-claude-code/skills/python-debugging/SKILL.md
```

里面可以写：

- 什么时候使用这个 skill
- 推荐调试流程
- 常用命令
- 项目约定
- 注意事项

加载后，内容会进入 system prompt，影响模型决策。

```text
system prompt
  |
  +-- base instructions
  +-- memory context
  +-- skill summaries
  +-- selected full skill text
```

### Plugin 是代码能力

Plugin 是 Python 文件，暴露 `register_tools(registry)`：

```python
def register_tools(registry):
    registry.register(MyTool())
```

Plugin 不只是提示模型“你可以查天气”，而是真的给 registry 加了一个可调用工具。

```text
plugins/weather.py
  |
  v
PluginLoader.load_plugins(registry)
  |
  v
registry now has "weather"
```

## Skill 的两层加载

如果把所有 skill 全文都塞进 system prompt，上下文会很快变大。所以本章使用两层策略：

```text
默认：只注入 skill 名称和摘要
需要时：注入指定 skill 全文
```

例如：

```text
/skill list
/skill show python-debugging
```

`build_system_context()` 默认输出摘要；`build_system_context(["python-debugging"])` 输出该 skill 全文。

## Plugin 的加载规则

PluginLoader 扫描插件目录下的 `.py` 文件：

```text
examples/plugins/
  weather.py
```

每个插件必须有：

```python
def register_tools(registry):
    ...
```

如果缺少这个函数，loader 应该跳过并返回清楚的错误结果，而不是让整个 CLI 崩溃。

## 本章要实现什么

主要修改：

- [skills.py](../../src/tiny_claude_code/skills.py)
- [tools/plugin.py](../../src/tiny_claude_code/tools/plugin.py)
- [cli.py](../../src/tiny_claude_code/cli.py)
- [tools/__init__.py](../../src/tiny_claude_code/tools/__init__.py)

需要实现：

- `SkillLoader.__init__`
- `list_skills`
- `load`
- `build_system_context`
- `_summary`
- `/skill list`
- `/skill show <name>`
- `PluginLoader.__init__`
- `load_plugins`
- `_load_one`
- `_import_module`
- 默认注册表加载插件

## 实现路线

### 第一步：扫描 skills

Skill 目录约定：

```text
.tiny-claude-code/skills/<skill-name>/SKILL.md
```

`list_skills()` 读取每个 SKILL.md，并生成摘要。摘要可以取标题后第一段或前若干字符。

### 第二步：加载指定 skill 全文

`load(name)` 找到对应文件并返回 Markdown 文本。找不到时返回可读错误或抛出明确异常，保持 CLI 可处理。

### 第三步：构建 system context

默认只列摘要：

```text
Available skills:
- python-debugging: Run tests first.
```

指定 skill 时附带全文：

```text
Loaded skills:
# Python Debugging
...
```

### 第四步：实现 skill 命令

CLI 支持：

```text
/skill list
/skill show python-debugging
```

list 用于发现；show 用于查看全文。

### 第五步：实现 plugin loader

动态导入每个 `.py` 文件，检查是否有 `register_tools`，调用它注册工具，并返回加载结果。

```text
loaded=True  message="loaded weather.py"
loaded=False message="missing register_tools"
```

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 15
```

测试覆盖：

- SkillLoader 能列出 skill
- load 能返回完整 SKILL.md
- system context 可以包含摘要或全文
- system prompt 能包含 skill context
- `/skill list` 和 `/skill show` 可用
- PluginLoader 能注册工具
- 无效插件会跳过
- 默认注册表会加载插件

## 验收任务

仓库已经有示例 skill：

```text
examples/skills/python-debugging/SKILL.md
```

你可以复制到工作区 skill 目录：

```text
.tiny-claude-code/skills/python-debugging/SKILL.md
```

然后运行：

```text
/skill list
/skill show python-debugging
```

再尝试：

```text
使用 python-debugging skill 帮我调试 examples/buggy-python-project
```

插件验收可以使用：

```text
examples/plugins/weather.py
```

把它作为 plugin_dir 传入默认注册表后，确认新工具能被 dispatch。

## 常见错误

### 把所有 skill 全文默认注入

skill 多了以后会浪费上下文。默认注入摘要，按需注入全文。

### plugin 导入失败导致整个程序退出

插件是扩展点，必须隔离失败。坏插件应该返回失败结果，其他插件继续加载。

### register_tools 没有接收 registry

插件接口要稳定：插件负责注册，registry 负责保存。

### skill 和 memory 混淆

memory 是项目事实；skill 是通用流程或能力说明。二者都进 system prompt，但来源和用途不同。

## 思考题

1. 什么内容适合写成 skill，什么内容适合写进 memory？
2. plugin 执行是否也要经过权限系统？
3. 动态导入插件有什么安全风险？
4. 如何避免 skill 太长导致上下文浪费？

## Bonus Tasks

- 给 skill 增加 frontmatter，例如 description、triggers。
- 支持 `/skill use <name>` 把全文注入当前会话。
- 给 plugin 增加 manifest。
- 在加载插件前做权限确认。

## 本章小结

你完成了 tiny-claude-code 的扩展层：

```text
Skills  -> 给模型更好的领域指导
Plugins -> 给 harness 更多真实工具
```

至此，课程从最小 agent loop 走到了一个可扩展 coding agent：

```text
loop + tools + permissions + hooks + recovery
+ context + session + memory + tasks
+ subagents + background + cron
+ skills + plugins
```

后续真正的工作，是在自己的项目里持续打磨这些边界：工具要可靠，权限要清楚，上下文要可控，扩展要可审计。

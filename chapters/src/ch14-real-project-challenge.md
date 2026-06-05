# ch14: Real Project Challenge

> 现在不再讲新机制，用你已经造好的 agent 解决更接近真实开发的任务。

## 本章目标

ch01 到 ch13 已经覆盖了 coding agent 的主要运行机制：循环、工具、权限、hooks、错误恢复、上下文、会话、任务、子 agent、后台任务。

本章的目标是验收这些能力。你会用自己的 agent 处理两个示例项目：

- [buggy-python-project](../../examples/buggy-python-project)：修复失败测试
- [tiny-web-app](../../examples/tiny-web-app)：给 Flask 应用补功能

```text
真实任务
  |
  v
运行测试
  |
  v
理解失败
  |
  v
修改代码
  |
  v
再次验证
```

## 先建立心智模型

### 真实项目不是单步题

前面的章节测试通常只验证一个函数行为。真实项目任务会混合多个能力：

```text
搜索文件 -> 读测试 -> 运行测试 -> 修改代码 -> 再运行测试 -> 总结
```

agent 的价值不在于一次工具调用，而在于能维持这个闭环。

### 验收任务要先观察再行动

不要让 agent 直接猜修复。可靠流程是：

1. 运行测试，确认失败。
2. 读取失败测试，理解期望。
3. 读取实现文件，定位原因。
4. 做最小修改。
5. 重新运行测试。

这也是你评价 agent 是否成熟的标准。

## 挑战一：buggy-python-project

目录：

```text
examples/buggy-python-project/
  shopping_cart.py
  test_shopping_cart.py
```

先手动看初始状态：

```bash
python -m pytest examples/buggy-python-project -q
```

然后让 agent 处理：

```text
运行 examples/buggy-python-project 的测试，修复所有失败，并重新运行测试确认通过。修改前先阅读相关测试和实现文件。
```

理想动作：

```text
bash pytest
read tests
read implementation
write precise edits
bash pytest
final summary
```

## 挑战二：tiny-web-app

目录：

```text
examples/tiny-web-app/
  app.py
  test_app.py
```

这个挑战要求 agent 理解 Flask 应用和测试期望。提示：

```text
运行 examples/tiny-web-app 的测试，补齐缺失路由，让测试通过。保持改动最小。
```

它会迫使 agent：

- 运行 web app 测试
- 读取 Flask 路由
- 根据测试新增行为
- 再次验证

## 本章要做什么

本章不要求修改 `src/tiny_claude_code/` 的新模块。你主要使用 agent，并观察它是否能完成任务。

可以使用：

- `bash` 跑测试
- `read` 读失败文件
- `search` 找函数或路由
- `write` 做精确修改
- `TodoWrite` 管理步骤
- `SubAgent` 做旁路搜索
- `/compact` 控制长上下文
- `--resume` 恢复中断任务

## 测试讲解

运行：

```bash
python scripts/dev.py test --ch 14
```

测试不会要求示例项目已经被修好。它检查的是挑战是否存在、初始状态是否按设计失败：

- buggy-python-project 包含挑战测试
- buggy-python-project 初始会失败
- tiny-web-app 有缺失 about route 的挑战
- tiny-web-app 初始会失败一个测试

所以 ch14 的“通过测试”不代表你完成挑战；真正验收是手工让 agent 修复示例项目。

## 验收标准

挑战一：

```bash
python -m pytest examples/buggy-python-project -q
```

应该通过。

挑战二：

```bash
python -m pytest examples/tiny-web-app -q
```

应该通过。

如果你想保留练习初始状态，可以在完成后撤销 examples 目录的改动，或者不要提交这些修复。

## 观察记录

建议记录 agent 的表现：

- 是否主动先跑测试
- 是否读了测试再改实现
- 是否做了最小修改
- 是否重新验证
- 是否在失败后能调整策略
- 是否需要你给很多额外提示

这些观察会引出 ch15：当 agent 在某类任务上表现不稳时，可以通过 skill 或 plugin 扩展它。

## 常见错误

### 只看实现不看测试

测试是需求说明。agent 不读测试就改代码，容易修错方向。

### 一次重写整个文件

真实项目里应优先做最小改动。精确替换更容易审查。

### 只修一个失败就停止

要求 agent 重新运行完整测试，直到全部通过。

### 没有总结验证命令

最终回答应该包含改了什么，以及运行了哪个命令验证。

## 思考题

1. 这个 agent 在真实任务中最容易失败在哪里？
2. TodoWrite 是否让任务更稳定？
3. 什么情况下需要 subagent？
4. 如果测试失败信息被截断，agent 应该如何补充观察？

## Bonus Tasks

- 让 agent 给示例项目添加一个新测试再实现功能。
- 用 `/compact` 中途压缩一次，再继续任务。
- 中途退出 CLI，再用 `--resume` 恢复任务。
- 让 agent 对自己的改动做一次代码审查。

## 本章小结

你开始用 agent 完成真实开发闭环：

```text
观察失败
理解需求
修改实现
验证通过
总结结果
```

最后一章会讲扩展机制：当 agent 缺少领域知识或外部能力时，用 skills 和 plugins 给它加能力。

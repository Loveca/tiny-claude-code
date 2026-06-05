# Checkpoint 1: 第一次修 Bug

> 不引入新机制，只验证前四章的 agent 是否真的能完成一个小型开发任务。

## 本关目标

到 ch04 为止，你已经实现了：

- agent loop
- shell 工具
- 文件读写工具
- 搜索工具
- 工具注册表

这些能力组合起来，应该足够让 agent 修一个很小但真实的 bug。本 checkpoint 使用 [examples/simple-bug](../../examples/simple-bug) 作为练习项目。

```text
运行测试 -> 读取失败 -> 定位代码 -> 修改文件 -> 再次测试
```

这就是 coding agent 的最小闭环。

## 项目里有什么

示例目录包含两个文件：

```text
examples/simple-bug/
  calculator.py
  test_calculator.py
```

测试一开始会失败。这不是仓库坏了，而是练习设计：你要让 agent 根据测试失败修复代码。

## 推荐流程

先自己运行一次测试，确认失败形状：

```bash
cd examples/simple-bug
python -m pytest -q
```

然后回到项目根目录，启动 agent：

```bash
python scripts/dev.py run
```

输入：

```text
运行 examples/simple-bug 的测试，根据失败信息修复代码，然后重新运行测试确认通过
```

agent 理想上会执行这样的动作：

```text
bash: python -m pytest examples/simple-bug -q
  |
  v
read: examples/simple-bug/test_calculator.py
  |
  v
read: examples/simple-bug/calculator.py
  |
  v
write: 精确替换错误代码
  |
  v
bash: python -m pytest examples/simple-bug -q
```

## 观察重点

这个 checkpoint 不是为了考复杂推理，而是为了检查工具链是否顺畅：

- 模型是否会先运行测试，而不是凭空改代码
- shell 结果是否包含足够的失败信息
- read 是否能读取目标文件
- write 是否能做精确替换
- 修改后是否会再次运行测试

如果 agent 卡住，不要急着改 prompt。先看工具结果是不是清楚、完整、可用。

## 常见问题

### agent 只解释失败，不修改文件

说明模型没有形成“下一步行动”的判断。可以明确要求“请直接修复文件并重新测试”。

### agent 找不到文件

检查工具是否绑定到项目根目录。相对路径应该从 tiny-claude-code 根目录开始。

### write 替换失败

通常是 `old_text` 和文件真实内容不完全一致。让 agent 重新读取相关文件，再做更小范围的精确替换。

### 测试通过但没有说明改了什么

这不是功能错误，但可以要求 agent 在最终回答里总结修改点和验证命令。

## 验收标准

在 `examples/simple-bug` 中运行：

```bash
python -m pytest -q
```

期望结果是测试通过。

如果你想保持练习初始状态，不要提交示例 bug 的修复；这个目录本来就是给 agent 练手用的。

## 思考题

1. agent 修 bug 时，为什么应该先跑测试？
2. 如果测试失败信息很长，ShellTool 的截断策略会带来什么影响？
3. 精确替换失败时，agent 应该下一步做什么？
4. 这个练习暴露了当前 agent 哪些不足？

## 本关小结

前四章的能力合在一起，已经构成了最小开发闭环：

```text
观察 -> 判断 -> 修改 -> 验证
```

后续章节会让这个闭环更安全、更稳定、更能处理长任务。下一章先解决最紧迫的问题：agent 有能力动手以后，必须有权限边界。

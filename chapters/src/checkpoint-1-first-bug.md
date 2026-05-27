# Checkpoint 1: 你的 Agent 第一次修 Bug

> 不加新机制，只用前四章的能力做一次真实任务。

## 目标

完成 ch01-ch04 后，你的 agent 已经能：

- 对话
- 运行 shell 命令
- 读文件
- 写文件
- 搜索代码
- 通过 registry 管理工具

Checkpoint 1 的目标是验证这些能力能组合起来解决一个真实但很小的问题：运行测试，阅读失败信息，定位 bug，修改代码，再重新跑测试。

## 知识串讲：Checkpoint 检验的是反馈闭环

Checkpoint 不是额外的一章功能，而是一次集成验收。到这里，agent 已经会对话、调用 shell、读写文件，并通过注册表管理工具。真正要验证的是：这些能力能不能组合成一个最小反馈闭环。

修 bug 的过程通常不是“一次生成正确补丁”。更真实的路径是：读取错误，定位文件，提出修改，运行测试，观察新结果，再决定是否继续。这个 red-green-refactor 式循环正是 coding agent 和普通聊天机器人的分界线。

如果 Checkpoint 失败，不要只看最终答案。要回放每一步：模型有没有请求正确工具，工具结果有没有回填，文件写入有没有落在工作区内，测试失败有没有变成下一轮观察。这样才能判断问题出在 loop、工具协议、文件安全还是模型提示。

## 示例项目

仓库提供了：

```text
examples/simple-bug/
  calculator.py
  test_calculator.py
```

其中 `calculator.py` 有一个 off-by-one 错误，测试会失败。

## 验收任务

运行 tiny-claude-code：

```bash
python scripts/dev.py run
```

输入：

```text
运行 examples/simple-bug/ 的测试，根据报错修复代码
```

期望 agent 的动作路径大致是：

1. 用 `bash` 运行 pytest
2. 看到失败断言
3. 用 `read` 查看相关文件
4. 找到 off-by-one 错误
5. 用 `write` 精确替换错误代码
6. 再次运行 pytest
7. 汇报测试通过

## 为什么这是一个 checkpoint

这里没有新 API。它检验的是 harness 的组合能力：

- shell 给 agent 观察测试失败的能力
- read/search 给 agent 理解代码的能力
- write 给 agent 修改代码的能力
- registry 让这些工具能被统一提供给模型
- agent loop 让模型能在“观察 -> 行动 -> 再观察”之间持续迭代

如果这个任务能跑通，你已经有了一个最小 coding agent。

## 手动对照

你也可以先手动运行：

```bash
python -m pytest examples/simple-bug -q
```

预期初始状态是失败。agent 修复后，再运行同一命令应该通过。

项目根目录的默认测试不会收集这个故意失败的示例：

```bash
python -m pytest
```

默认只运行 `tests/`，这是为了避免 checkpoint 的初始失败状态影响课程单元测试。

## 思考题

1. agent 是先读代码还是先跑测试更好？为什么？
2. 如果测试输出很长，当前工具输出会给上下文带来什么压力？
3. 这次修 bug 是否需要权限审批？哪些操作未来应该要求审批？
4. 如果 agent 改错了文件，当前系统有什么恢复手段？

## 下一步

Part 2 会开始处理安全和健壮性。你的 agent 已经能动手了，所以接下来必须回答一个新问题：它可以做，不代表它应该直接做。权限系统会成为下一章的核心。

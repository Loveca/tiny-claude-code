# ch14: Real Project Challenge

> 最终验收不是又写一个模块，而是用自己造的 agent 修真实问题。

## 本章目标

ch14 不引入新的 agent 机制。它提供几个真实感更强的挑战项目，让你验证前面十四章构建出来的能力：读代码、运行测试、定位错误、编辑文件、复跑验证、总结结果。

## 知识串讲：真实项目挑战检验反馈闭环

前面章节分别实现了 loop、工具、权限、上下文、Todo、Subagent 和后台任务。真实项目挑战的目的，是把这些能力放回同一个反馈闭环里：观察问题，定位原因，编辑文件，运行验证，根据结果继续迭代，最后给用户一个可复查的总结。

这和普通“让模型回答问题”不同。coding agent 的关键能力不是一次说对，而是能在外部环境里校正自己。测试失败、命令报错、文件不存在、用户插话，都是新的观察；agent 应该把它们纳入循环，而不是假装原计划仍然成立。

做挑战时要刻意缩小任务边界。先让 agent 修一个小 bug，再让它处理一个小 Web App，最后才尝试自己的项目。边界越清楚，越容易看出当前 agent 是缺工具、缺上下文管理，还是缺错误恢复。

## 挑战 1：Buggy Python Project

目录：

```text
examples/buggy-python-project/
```

运行：

```bash
python -m pytest examples/buggy-python-project
```

这个项目包含三个失败点：

- 折扣计算把百分比当成固定金额。
- 购物车总价忽略 `quantity`。
- 免运费门槛没有包含边界值。

让 agent 做的任务：

```text
运行 examples/buggy-python-project 的测试，根据失败修复实现，并复跑测试。
```

## 挑战 2：Tiny Web App

目录：

```text
examples/tiny-web-app/
```

运行：

```bash
python -m pytest examples/tiny-web-app
```

这个项目是一个无依赖 route table。测试要求新增 `/about` 路由。

让 agent 做的任务：

```text
修复 examples/tiny-web-app，让 /about 返回 about tiny app。
```

## 挑战 3：自己的项目

前两个挑战是受控练习。真正的验收是让 agent 在你自己的项目里完成一个小任务，例如：

- 修一个失败测试。
- 补一段 README。
- 搜索 TODO 并给出整理。
- 给一个函数补测试。

任务要足够小，方便你判断 agent 是否真的完成。

## 运行测试

```bash
python scripts/dev.py test --ch 14
```

测试覆盖：

- challenge 项目文件存在。
- `buggy-python-project` 初始状态会失败。
- `tiny-web-app` 初始状态会失败。
- 失败点和教材描述一致。

## 思考题

1. 为什么 ch14 不应该再引入新机制？
2. 真实项目挑战中，agent 最容易在哪一步犯错？
3. 什么时候应该让 agent 自己修，什么时候应该你先缩小问题？

## 本章小结

ch14 把前面的能力串起来做真实验收。agent 的价值不是 API 调通，而是能在真实反馈循环里把问题修到测试通过。

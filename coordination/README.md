# Coordination

本目录用于支撑“半自动多 agent 流水线”。

目标：

- 让任务可以按依赖逐轮推进
- 让 worker、coordinator、integrator 的职责清楚分开
- 让新开的 agent 不依赖聊天上下文，也能接手继续工作

## 文件说明

- `tasks.yaml`：任务源数据，包含状态、依赖、路径范围、建议执行角色
- `board.md`：面向人类的当前轮次看板
- `reviews.md`：审查结论、返工决定、合并建议
- `templates/`：各类 agent 的提示词模板

## 使用原则

- 长期有效的流程规则写在模板和项目文档里
- 本轮任务变化写在 `tasks.yaml`、`board.md`、`reviews.md`
- 不要求 agent 记住上一次聊天，要求它先读项目工件

## 最小工作流

1. 你给阶段目标
2. Coordinator 读取项目状态并更新 `tasks.yaml`
3. Coordinator 选出 `ready` 任务并分配给 worker
4. Worker 在 worktree 中执行，完成后提交并写 session
5. Integrator / Coordinator 审查结果并记录到 `reviews.md`
6. 合格任务合并；不合格任务生成 follow-up task

## 状态定义

- `todo`：尚未可执行
- `ready`：依赖已满足，可派发
- `in_progress`：已有 worker 在执行
- `blocked`：被外部问题或依赖阻塞
- `review`：待审查
- `merged`：已合并到主线
- `rework`：需要返工

# Git Worktrees

本文件只回答一个问题：本项目如何使用 `git worktree` 支撑多 agent 并行开发。

## 为什么使用

- 减少多个 agent 共用同一工作目录时的覆盖风险
- 让每个并行任务拥有独立工作区
- 保持单一仓库历史，不必为每个 agent 完整 clone 一份项目

## 本项目的使用方式

- 主目录：整合区
- worktree：执行区
- 每个 worktree 对应一个单一主题

推荐放置位置：

```text
../幻界2.0-worktrees/
  frontend-shell/
  backend-core/
  rules-research/
```

当前已创建的示范 worktree：

- `../幻界2.0-worktrees/frontend-shell`
- 分支：`wt/frontend-shell`

## 任务适配建议

适合独立 worktree 的任务：

- 前端页面骨架
- 后端服务骨架
- 规则资料提取脚本
- 独立研究文档
- 独立 session 记录

不适合直接并行共写的任务：

- `README.md`
- `AGENTS.md`
- `TASKS.md`
- `CHECKPOINTS.md`
- 同一份正式文档的最终整合

## 推荐流程

```bash
git switch main
git pull
git worktree add ../幻界2.0-worktrees/frontend-shell -b wt/frontend-shell
```

在对应 worktree 中完成工作后：

```bash
git status
git add .
git commit -m "Add frontend shell"
```

最后回到主目录进行审查和合并。

## 注意事项

- worktree 共享提交历史，但每个 worktree 有自己的检出状态。
- 被忽略的依赖和环境文件不会自动共享。
- 如果两个 worktree 修改同一文件，冲突会在合并时出现。
- 所以 worktree 不是“消除冲突”，而是“把冲突压缩到更清楚的边界里”。

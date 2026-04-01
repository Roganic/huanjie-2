# TASKS

使用方式：

- 每个任务尽量标注负责范围，方便多 agent 并行
- 如果某个共享文件正在被集中修改，可在任务后标记 `occupied`
- 任务描述保持短句，细节写入对应 `docs/sessions/`
- 如果一个任务将进入独立 worktree，建议在任务后加 `wt`

## Now (AI 实时叙事阶段)

- 接入 Kimi API 实现 AI 叙事生成 `backend`
- 设计叙事提示词模板与上下文管理 `backend`
- 前端展示 AI 生成的叙事文本 `frontend`

## Next

- 战斗系统完整闭环 `backend`
- 角色系统数据持久化 `backend`
- 记忆/RAG 初步探索 `backend`

## Later

- 增加结构化规则数据格式
- 增加提示词实验和模型对比
- 增加试玩流程和样例战役

## Blocked

- 暂无

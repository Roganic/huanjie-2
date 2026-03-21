# TASKS

使用方式：

- 每个任务尽量标注负责范围，方便多 agent 并行
- 如果某个共享文件正在被集中修改，可在任务后标记 `occupied`
- 任务描述保持短句，细节写入对应 `docs/sessions/`
- 如果一个任务将进入独立 worktree，建议在任务后加 `wt`

## Now

- 明确项目目录和协作规则 `coordination`
- 收敛第一版产品定义 `product`
- 明确第一版规则内核范围 `rules-core`
- 明确本地 Web 原型的技术栈 `tech`

## Next

- 建立 `app/frontend` 和 `app/backend` 的最小骨架 `app`
- 梳理 DND 5e、OSE、灵魂迷雾的可提炼规则点 `research`
- 定义 GM agent、规则引擎、记忆/RAG 的职责边界 `ai-architecture`
- 定义首批 worktree 任务切分方式 `coordination`

## Later

- 增加结构化规则数据格式
- 增加提示词实验和模型对比
- 增加试玩流程和样例战役

## Blocked

- 暂无

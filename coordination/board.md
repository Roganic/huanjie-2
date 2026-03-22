# Board

## Current Round

Integration complete:

- `frontend-shell` -> `merge`
- `backend-core` -> `merge`
- `dnd-rules-analysis` -> `merge`
- `ose-rules-analysis` -> `partial`
- `rules-core-integration-v1` -> `merge`

Ready next:

- `gm-loop-prototype`

Dispatch hold:

- `gm-loop-prototype` 依赖已满足，但按当前主线收口要求暂不派发

Blocked by review / integration:

- `frontend-backend-wireup`

No follow-up rework task opened in this round:

- `ose-rules-analysis` 的可用结论将由 `rules-core-integration-v1` 手动吸收，不再派单要求 worker 清理共享总纲改动
- `ose-rules-analysis` 分支不进入主线历史，只保留三份已批准吸收的研究产物

## Role Routing

- `claude_worker`：代码实现任务
- `codex_worker`：规则分析、研究、文档任务
- `codex_integrator`：审查、整合、共享文档回写

## Integrator-only Files

- `docs/rules-core.md`
- 其他共享总纲文档由 integrator 回写；普通 worker 只写自己任务范围内的实现文件与 session 记录

## Review Focus

- `gm-loop-prototype`：是否按统一判定 + 结构化裁定结果实现最小后端闭环
- `gm-loop-prototype`：是否避免直接把共享架构文档当成 worker 写入目标
- `frontend-backend-wireup`：继续等待 GM loop 原型完成

# Board

## Current Round

Integration complete:

- `frontend-shell` -> `merge`
- `backend-core` -> `merge`
- `dnd-rules-analysis` -> `merge`
- `ose-rules-analysis` -> `partial`
- `rules-core-integration-v1` -> `merge`
- `gm-loop-prototype` -> `merge`
- `gm-loop-prototype-fix` -> `merge`

Ready next:

- `frontend-backend-wireup`

Blocked by review / integration:
- None

Follow-up opened in this round:

- `ose-rules-analysis` 的可用结论将由 `rules-core-integration-v1` 手动吸收，不再派单要求 worker 清理共享总纲改动
- `ose-rules-analysis` 分支不进入主线历史，只保留三份已批准吸收的研究产物
- `gm-loop-prototype-fix` 已完成并吸收到主线

## Role Routing

- `claude_worker`：代码实现任务
- `codex_worker`：规则分析、研究、文档任务
- `codex_integrator`：审查、整合、共享文档回写

## Integrator-only Files

- `docs/rules-core.md`
- 其他共享总纲文档由 integrator 回写；普通 worker 只写自己任务范围内的实现文件与 session 记录

## Review Focus

- `frontend-backend-wireup`：是否只接现有 `/health` 与 `/action`，不擅自改后端协议
- `frontend-backend-wireup`：是否让前端展示结构化结果，而不是把逻辑重新写到前端

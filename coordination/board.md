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
- `frontend-backend-wireup` -> `merge`

Ready next:

- `backend-state-bootstrap`

Blocked by review / integration:
- None

Follow-up opened in this round:

- `ose-rules-analysis` 的可用结论将由 `rules-core-integration-v1` 手动吸收，不再派单要求 worker 清理共享总纲改动
- `ose-rules-analysis` 分支不进入主线历史，只保留三份已批准吸收的研究产物
- `gm-loop-prototype-fix` 已完成并吸收到主线
- 下一步优先移除前端固定 mock 对角色 / 场景状态的依赖

## Role Routing

- `claude_worker`：代码实现任务
- `codex_worker`：规则分析、研究、文档任务
- `codex_integrator`：审查、整合、共享文档回写

## Integrator-only Files

- `docs/rules-core.md`
- 其他共享总纲文档由 integrator 回写；普通 worker 只写自己任务范围内的实现文件与 session 记录

## Review Focus

- `backend-state-bootstrap`：是否以最小只读接口提供当前 actor / scene 状态
- `backend-state-bootstrap`：是否避免提前引入数据库、持久化或复杂会话系统

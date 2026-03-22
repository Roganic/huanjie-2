# Board

## Current Round

Integration complete:

- `frontend-shell` -> `merge`
- `backend-core` -> `merge`
- `dnd-rules-analysis` -> `merge`
- `ose-rules-analysis` -> `partial`
- `rules-core-integration-v1` -> `merge`
- `gm-loop-prototype` -> `partial`

Ready next:

- `gm-loop-prototype-fix`

Blocked by review / integration:

- `frontend-backend-wireup`

Follow-up opened in this round:

- `ose-rules-analysis` 的可用结论将由 `rules-core-integration-v1` 手动吸收，不再派单要求 worker 清理共享总纲改动
- `ose-rules-analysis` 分支不进入主线历史，只保留三份已批准吸收的研究产物
- `gm-loop-prototype-fix`：收紧 auto-success 规则，补 request 校验和回归测试

## Role Routing

- `claude_worker`：代码实现任务
- `codex_worker`：规则分析、研究、文档任务
- `codex_integrator`：审查、整合、共享文档回写

## Integrator-only Files

- `docs/rules-core.md`
- 其他共享总纲文档由 integrator 回写；普通 worker 只写自己任务范围内的实现文件与 session 记录

## Review Focus

- `gm-loop-prototype-fix`：是否修复 false auto-success 行为
- `gm-loop-prototype-fix`：是否对 `ability` 输入做明确约束并补回归测试
- `frontend-backend-wireup`：继续等待 GM loop 原型完成

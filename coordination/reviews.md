# Reviews

## 2026-03-22 Integration Review

### frontend-shell

- status: `merge`
- merged_commit: `d9c20cb`
- verification:
  - `npm run build` passed
  - `npm run lint` passed
- result: 可以合并
- notes:
  - 本地前端壳子已成型，任务目标成立
  - 改动范围在允许路径内
  - `docs/tech-choices.md` 的共享总结类内容后续只由 integrator 回写

### backend-core

- status: `merge`
- merged_commit: `80e3766`
- verification:
  - `python3 -m compileall src` passed
- result: 可以合并
- notes:
  - 最小 FastAPI 骨架清楚，可作为后续 GM loop 原型基础
  - 当前整合环境未安装 `fastapi`，因此没有直接执行 HTTP 健康检查
  - `docs/ai-architecture.md` 与 `docs/tech-choices.md` 的共享总结类内容后续只由 integrator 回写

### dnd-rules-analysis

- status: `merge`
- merged_commit: `ef951d3`
- result: 可以合并
- notes:
  - 提炼结果结构清楚，研究产物可直接支撑规则整合
  - 未发现越界修改共享总纲

### ose-rules-analysis

- status: `partial`
- result: 只吸收允许范围内的研究结果，不直接整分支合并
- accepted:
  - `research/notes/2026-03-22-ose-ai-stability-analysis.md`
  - `research/extracts/ose-mvp-rules-extract.md`
  - `docs/ose-rules-analysis.md`
- rejected:
  - `docs/rules-core.md`
- notes:
  - 分析内容质量良好，材料本身可用
  - 直接修改 `docs/rules-core.md` 超出原任务允许范围
  - OSE 结论由 `rules-core-integration-v1` 手动吸收到共享总纲
  - main 只吸收三份已批准文件，分支本身未 merge

## Dispatch Outcome

- 本轮最新 `ready` 任务：`gm-loop-prototype-fix`
- 本轮新增 1 个返工 worker 任务：`gm-loop-prototype-fix`
- 从本轮起，共享总纲文档默认仅由 `codex_integrator` 回写

### rules-core-integration-v1

- status: `merge`
- result: 已整合完成
- notes:
  - `docs/rules-core.md` 已回写为单一 V1 规则总纲
  - 明确采用“5e 判定语法 + OSE 流程结构”
  - 只吸收了 OSE 允许范围内的研究结论，没有直接采用其越界草稿
  - 下一批 `ready` 任务切换为 `gm-loop-prototype`

### gm-loop-prototype

- status: `partial`
- reviewed_branch_head: `eca17eb`
- result: 形状可保留，但不能直接 merge
- findings:
  - `app/backend/src/engine/resolver.py` 中的 auto-success 关键词过宽，`open`、`talk`、`say` 会把本应检定的动作直接跳过
  - `app/backend/src/models/action.py` 中 `ability` 只是自由字符串，非法值会静默落到 `0` 修正，而不是在 API 层报错
  - `app/backend/tests/test_action.py` 没覆盖上述关键回归路径
- follow_up:
  - 新建 `gm-loop-prototype-fix`
  - 修复 false auto-success
  - 收紧 request 校验
  - 补回归测试后再审查

## Follow-up Rules

- worker 完成后默认进入 `review`，而不是直接合并
- 共享总纲文档的最终回写由 integrator 负责
- 如果 worker 越界但内容可用，优先“部分吸收”，不是整分支放弃

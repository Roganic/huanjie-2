# 2026-03-22 rules-core-integration

## 目标

- 以 integrator 身份整合 DND 与 OSE 的已审查结论
- 回写共享总纲 `docs/rules-core.md`
- 明确哪些内容属于 V1 基础层，哪些延后为模块

## 输入

- `docs/rules-core.md`
- `wt/dnd-rules-` 中已通过审查的 DND 文档、extract、session
- `wt/ose-rules-` 中已通过审查的 OSE 文档、extract、session
- `coordination/reviews.md` 中对四个前置任务的 merge / partial 结论

## 结论

- 共享规则内核采用“5e 判定语法 + OSE 流程结构”
- V1 基础层只保留统一检定、优势 / 劣势、升序 AC 战斗、少量状态、资源与时间推进
- 5e 的职业 / 法术复杂度与 OSE 的旧式多口径表达都不进入基础层
- `ose-rules-analysis` 的越界 `docs/rules-core.md` 改动未直接吸收，只保留其允许范围内的研究结论

## 未决问题

- 技能标签是否做项目自定义压缩
- `0 HP` 的死亡 / 濒死缓冲形式
- 模板化法术角色是否进入 V1
- 资源压力与 Web 原型节奏如何平衡

## 下一步建议

- 让后端任务基于当前总纲实现统一判定与最小 GM loop
- 由 integrator 在后续阶段统一回写 `docs/ai-architecture.md` 与 `docs/tech-choices.md` 的共享结论
- 如需继续细化，优先补一份面向后端的数据结构草案，而不是继续扩写总纲

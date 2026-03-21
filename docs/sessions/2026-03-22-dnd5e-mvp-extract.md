# 2026-03-22 dnd5e-mvp-extract

## 目标

- 在不修改共享入口文件的前提下，为当前 `wt/dnd-rules-` worktree 产出一份可接手的 DND 5e 规则提炼结果
- 将 5e 中适合 AI 跑团 MVP 的部分从“大而全系统”中切出来

## 输入

- `README.md`
- `AGENTS.md`
- `TASKS.md`
- `CHECKPOINTS.md`
- `docs/git-worktrees.md`
- `docs/rules-core.md`
- 当前仓库中尚无 DND 5e 的正式研究文档或结构化提炼文件

## 做了什么

- 确认当前 worktree 是独立执行区，且不应主动修改 `README.md`、`AGENTS.md`、`TASKS.md`、`CHECKPOINTS.md`
- 读取现有规则总纲，确认项目当前只停留在“轻量 d20 + 吸收 5e 认知优势”的方向描述
- 新增正式文档 `docs/dnd5e-mvp-extract.md`
- 在正式文档中收敛了推荐保留、可压缩保留、暂不纳入、数据落点四组结论

## 结论

- DND 5e 对本项目最有价值的是判定语法，不是完整文本规则
- MVP 应优先保留六属性、熟练、统一 d20 检定、优势 / 劣势、基础战斗骨架
- 职业、法术、反应、战斗特例等内容应作为后续模块，而不是基础层
- 后端建模应优先围绕统一判定和最小战斗闭环，而不是职业或法术数据库

## 未决问题

- 是否要在下一轮直接把高频技能列表压缩成项目自己的标签集合
- 是否要给 `condition_tags` 先定义一版最小状态表
- 是否要继续做一份 OSE 对照文档，用来帮助确定最终规则内核裁剪边界
- 当前仓库还没有实际 5e 原始资料输入，后续是否要先补 `research/raw/dnd5e/` 或结构化摘录

## 下一步建议

- 基于本次结论，继续产出一份 `research/extracts/` 层的结构化样例
- 补一份 DND 5e 与 OSE 的并排对照，明确哪些复杂度来自 5e、哪些可被 OSE 替代
- 在 `app/backend/` 开始前，先用 JSON 或 YAML 草拟一次统一检定和战斗回合的数据模型

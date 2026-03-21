# Agent 协作说明

本项目默认由多个 agent 和多个 session 持续推进。所有参与者都应优先保证可接手性，而不是只完成当前局部任务。

## 基本原则

- 优先做最小可落地方案，遵循奥卡姆剃刀原则。
- 不提前拆分过多目录、服务或抽象层。
- 正式结论写入 `docs/`，临时过程写入 `docs/sessions/`。
- 修改方向应当服务于 AI 跑团主线，不做无关工程化。
- 允许并行协作，但必须优先降低文件冲突和上下文冲突。
- 文档默认采用渐进式披露，先写入口摘要，再按需向下拆分。
- 并行开发优先使用 `git worktree`，不要让多个 agent 长时间共用同一工作目录。

## 工作前检查

开始工作前，先读：

1. `README.md`
2. `TASKS.md`
3. `CHECKPOINTS.md`
4. 与当前任务最相关的 `docs/` 文档

如果当前任务涉及上下文较强的历史讨论，再补读相关 `docs/sessions/`。

开始动手前，还应确认两件事：

1. 当前任务的写入范围是什么
2. 是否已有其他 agent 正在处理同一范围

## 文件分工

- `README.md`：项目入口、目录说明、全局使用方式
- `AGENTS.md`：agent 协作规则和交接约定
- `TASKS.md`：当前待办、进行中、阻塞项
- `CHECKPOINTS.md`：关键决策和阶段状态
- `docs/`：正式文档
- `docs/sessions/`：过程记录
- `research/`：规则资料研究
- `app/`：代码实现

## 并行协作规则

- 每个 agent 开始前先认领一个明确范围，例如“规则内核文档”“前端原型”“5e 资料提取”。
- 尽量保证不同 agent 的主要写入路径不重叠。
- 推荐的分工单位：
  - 单个正式文档
  - 单个 `docs/sessions/` 记录文件
  - 单个代码子目录
  - 单个研究子目录
- `docs/sessions/` 天然适合并行，每个 agent 新建自己的 session 文件，不要共写。
- `TASKS.md` 和 `CHECKPOINTS.md` 属于共享文件，修改前先看最新状态，更新时只做必要改动。
- 如果任务不可避免会修改同一正式文档，先在 session 文件里完成草稿，再由一个 agent 负责回写整合。
- 当并行任务超过 2 个，或涉及代码实现时，默认切到独立 worktree。

## Worktree 工作流

推荐流程：

1. 在主工作目录更新到最新主线
2. 创建独立分支和 worktree
3. 在该 worktree 中完成单一主题工作
4. 将结果提交到该分支
5. 回到主工作目录统一审查并合并

推荐约定：

- worktree 路径：`../幻界2.0-worktrees/<topic>`
- 分支命名：`wt/<topic>`
- 一个 worktree 只做一个主题
- 不在两个 worktree 中同时编辑同一共享文件

建议命令：

```bash
git worktree add ../幻界2.0-worktrees/frontend-shell -b wt/frontend-shell
git worktree add ../幻界2.0-worktrees/rules-research -b wt/rules-research
git worktree list
git worktree remove ../幻界2.0-worktrees/frontend-shell
```

注意事项：

- worktree 共享 git 历史，但不共享未跟踪文件和本地依赖目录。
- 如需运行前端或后端，依赖可能要在各自 worktree 里单独安装。
- 主工作目录默认为整合区，不建议在主工作目录和 worktree 中同时改同一主题。

## 渐进式披露规则

- 根目录文件只回答“项目是什么、现在在哪、接下来做什么”。
- `docs/` 文件先写结论和范围，再写细节，不要一开始塞满长篇背景。
- 如果某个主题需要深入展开，再拆新文件，而不是在初期预建大量层级。
- `research/raw/` 存原始材料，`research/extracts/` 存结构化提炼，`research/notes/` 存分析笔记。
- 正式文档应尽量引用提炼结果，而不是要求后续 agent 重新阅读原始材料。

## 会话记录约定

如果一个 session 产生了值得保留的探索过程，新增一份记录到 `docs/sessions/`：

- 文件名格式：`YYYY-MM-DD-topic.md`
- 内容应包含：目标、输入、结论、未决问题、下一步建议

不要把长期有效的正式结论只留在 session 文件里。正式结论应同步回写到 `docs/` 或根目录协作文件。

## 任务管理约定

- 新任务先写入 `TASKS.md`
- 关键取舍和阶段完成情况写入 `CHECKPOINTS.md`
- 如果发现原有计划失效，应直接更新，而不是保留一堆过期状态
- 如需并行推进，可在任务条目后标记负责范围，例如 `frontend`、`rules-core`、`research-dnd5e`

## 规则研究约定

- 原始规则书、网页导出、截图统一放 `research/raw/`
- 结构化提炼结果放 `research/extracts/`
- 阅读理解和对比分析放 `research/notes/`
- 不要把原始资料和提炼结果混放

## 代码实现约定

- `app/frontend/`：本地 Web 前端
- `app/backend/`：API、规则引擎、agent 编排
- `app/scripts/`：实验脚本、数据处理、评测、小工具

实现时优先保证：

1. 规则边界清楚
2. 数据结构简单
3. 可调试
4. 便于后续扩展到更多规则模块

代码并行时的默认分工：

- `app/frontend/`：一个 agent
- `app/backend/`：一个 agent
- `app/scripts/`：一个 agent

如果需要同时改同一子目录，优先继续细分文件范围或拆成先后两步，而不是硬并行。

## 交接标准

完成一次重要工作后，至少更新以下其中两项：

- `TASKS.md`
- `CHECKPOINTS.md`
- 对应 `docs/` 文档
- 对应 `docs/sessions/` 记录

如果代码行为改变，必须同步更新相关文档，不要让文档滞后于实现。

交接时应保证下一位 agent 不需要重新通读全部材料，只需从入口文件逐层下钻即可继续工作。

# 幻界 2.0

AI 跑团项目工作区。这个目录承载产品设计、规则研究与产品前后端实现。

## 目标

- 开发本地 Web 原型
- 研究并提纯 TRPG 原版规则书
- 沉淀 AI 跑团的规则内核、系统架构和产品决策

## 目录结构

```text
幻界2.0/
├─ README.md
├─ AGENTS.md
├─ CHECKPOINTS.md
├─ TASKS.md
├─ docs/
│  ├─ product.md
│  ├─ rules-core.md
│  ├─ ai-architecture.md
│  ├─ tech-choices.md
│  └─ sessions/
├─ app/
│  ├─ README.md
│  ├─ frontend/
│  └─ backend/
├─ research/
│  ├─ raw/
│  │  ├─ dnd5e/
│  │  ├─ ose/
│  │  └─ soul_mist/
│  ├─ extracts/
│  └─ notes/
└─ archive/
```

## 使用规则

- 根目录放项目入口文件和协作文件，不放零散草稿。
- 文档组织采用渐进式披露：先给入口摘要，再按需进入更细的专题文件。
- `docs/` 放正式结论。这里的内容应当可以被后续实现直接引用。
- `docs/sessions/` 放按日期记录的工作过程、讨论、探索和中间结论。
- `app/` 放所有可运行代码和开发脚本。
- `research/raw/` 只放原始资料，不做编辑。
- `research/extracts/` 放从规则书提炼出的结构化内容。
- `research/notes/` 放阅读笔记、比较笔记和裁剪结论。
- `archive/` 放废弃方案、旧版本文档和不再活跃的材料。
- `.forgeflow/project.yaml` 是本项目接入 ForgeFlow 的最小配置。

## 协作入口

新 agent 或新 session 进入项目时，默认按这个顺序阅读：

1. `README.md`
2. `AGENTS.md`
3. `TASKS.md`
4. `CHECKPOINTS.md`
5. `.forgeflow/project.yaml`
6. 相关的 `docs/` 正式文档
7. 对应主题的 `docs/sessions/` 记录

## Git 与 Worktree

本项目使用独立 git 仓库管理，并推荐在进入并行开发阶段后使用 `git worktree`。

- 主工作目录保留为“整合区”，用于查看全局状态、做最终整合和提交。
- 每个并行 agent 使用一个独立 worktree，避免直接共用同一目录。
- worktree 建议放在仓库外的兄弟目录中，例如 `../幻界2.0-worktrees/`。
- 文档和代码都可以使用 worktree，但共享文件仍应尽量由单一 agent 整合回主线。
- ForgeFlow 会使用本仓库作为 workspace，但运行态状态不在本仓库保存。

推荐命名：

- worktree 路径：`../幻界2.0-worktrees/<topic>`
- 分支名：`wt/<topic>`

## 并行协作原则

- 允许多个 agent 同时工作，但每个 agent 应当先认领明确的主题或写入范围。
- 正式文档优先按主题分工，避免多个 agent 同时改同一文件。
- `docs/sessions/` 默认允许并行追加，每个 session 使用独立文件。
- 代码目录按子目录分工：`app/frontend/`、`app/backend/`、`app/scripts/`。
- 如果必须改动共享文件，应先在 `TASKS.md` 标记占用，再开始修改。
- 如果进入高并行阶段，优先使用独立 worktree，而不是多个 agent 共用当前目录。

## 渐进式披露约定

- 根目录文件只保留高层导航、当前状态和协作规则。
- `docs/` 中的单个文件应先写摘要、范围、当前共识，再写待细化项。
- 研究资料先分为 `raw`、`extracts`、`notes` 三层，避免把原文和结论混在一起。
- 当一个主题开始膨胀时，再从总文档拆出专题文档，而不是提前细分。

## Worktree 适用范围

- 适合：前端、后端、脚本、独立研究任务、独立 session 记录
- 谨慎并行：`README.md`、`AGENTS.md`、`TASKS.md`、`CHECKPOINTS.md`
- 最好单点整合：正式文档的最终回写和跨模块结构调整

## ForgeFlow

ForgeFlow 目录：

- `/Users/roganic/Documents/ObsidianVault/20-Projects/Incubating/ForgeFlow`

它负责：

- Supervisor / Coordinator / Worker / Integrator 调度
- 运行态任务状态与日志
- admin dashboard
- 项目 worktree 管理

## 快速开始

### 本地开发

```bash
# 后端
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn src.main:app --reload

# 前端 (新终端)
cd app/frontend
npm install
npm run dev
```

### 部署

支持前后端分离部署：
- **前端**: GitHub Pages
- **后端**: Railway / Render

详见 [部署文档](docs/deployment.md)。

## 当前阶段建议

第一阶段优先完成：

1. 明确产品定义和 MVP 范围
2. 收敛第一版规则内核
3. 明确 GM agent、规则引擎、记忆/RAG 的系统边界
4. 建立本地 Web 原型的最小前后端骨架

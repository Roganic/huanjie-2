# CHECKPOINTS

## 2026-03-21

- 初始化项目目录
- 建立文档、代码、研究、归档四层结构
- 新增 `AGENTS.md` 作为多 agent / 多 session 的统一协作入口
- 决定采用“文档优先 + 本地 Web 原型 + 规则研究分层”的极简工作方式
- 明确后续协作需支持多 agent 并行和文档渐进式披露
- 决定将 `幻界2.0` 设为独立 git 仓库，并采用 `git worktree` 作为并行开发默认机制
- 初始化独立 git 仓库并完成基线提交
- 创建首个示范 worktree：`../幻界2.0-worktrees/frontend-shell` 对应分支 `wt/frontend-shell`

## 2026-03-22

- 完成 DND 与 OSE 研究结果的第一轮整合回写
- 将 `frontend-shell`、`backend-core`、`dnd-rules-analysis` 实际合并回 `main`
- 仅吸收 `ose-rules-analysis` 的批准研究产物，不合并其分支历史
- 完成后端最小 GM action -> structured resolution -> narration stub 闭环
- 修复 GM loop 中 auto-success 误判与 `ability` 输入校验问题
- 明确 V1 规则内核采用“5e 判定语法 + OSE 流程结构”
- 决定基础层只保留统一检定、优势 / 劣势、升序 AC 战斗、少量状态、资源与时间推进
- 决定不在 V1 基础层引入完整职业、完整法术、THAC0、多口径检定和高例外战斗规则
- 确认共享总纲文档默认仅由 integrator 回写

## 当前共识

- 前端先做本地 Web，不做 GitHub Pages，不急着做 App
- 规则设计可以参考原版规则书，但项目实现不应强依赖原版文本
- 项目目录遵循奥卡姆剃刀原则，优先保证清晰和可接手性
- 文档以摘要导航为入口，按需下钻，不预先铺开复杂层级
- 并行 agent 协作时优先分配写入范围，减少共享文件直接冲突
- 并行开发以 worktree 为主，主目录作为整合区使用
- 规则实现优先围绕“动作输入 -> 结构化裁定结果”建模，而不是围绕原版规则全文建模
- 当前前后端联调的后端依赖已具备，下一步应连接 `/health` 与 `/action`

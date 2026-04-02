# CHECKPOINTS

## 2026-03-21

- 初始化项目目录
- 建立文档、代码、研究、归档四层结构
- 新增 `AGENTS.md` 作为多 agent / 多 session 的统一协作入口
- 决定采用"文档优先 + 本地 Web 原型 + 规则研究分层"的极简工作方式
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
- 完成前端与 `/health`、`/action` 的最小联调
- 明确 V1 规则内核采用"5e 判定语法 + OSE 流程结构"
- 决定基础层只保留统一检定、优势 / 劣势、升序 AC 战斗、少量状态、资源与时间推进
- 决定不在 V1 基础层引入完整职业、完整法术、THAC0、多口径检定和高例外战斗规则
- 确认共享总纲文档默认仅由 integrator 回写

## 2026-04-02 — 里程碑 1.1 角色系统完成

**验收状态：通过**

- 完成角色系统正式验收，所有 232 项自动化测试通过
- 覆盖角色系统全链路：六属性 → 修正值 → HP → AC 全链路验证
- 技能检定测试通过：d20 + 属性修正 + 熟练加值公式正确
- 战斗命中测试通过：包含 d20、属性修正、攻击总值、目标 AC、命中判断、伤害骰
- 端到端冒烟测试通过：创建角色 → 3+ 次行动 → AI 叙事包含角色名和职业特征
- 前端角色创建界面完整，支持标准数组 / 4d6 取三 / 手动输入三种方式
- 角色数据持久化到后端会话，跨行动状态一致
- 战士 / 法师 / 盗贼三个职业各自的 HP、AC、技能熟练度正确实现
- 新增 `test_smoke_phase_1_1.py` 专项冒烟测试，验证核心玩家体验路径
- 已准备好进入下一阶段（战斗系统或场景系统）

**主要产出：**
- `app/backend/tests/`：228 个单元/集成测试 + 4 个端到端冒烟测试
- `app/frontend/src/App.tsx`：完整角色创建和冒险界面
- `docs/rules-core.md`：V1 规则内核文档
- 所有测试可通过 `pytest` 一键运行

## 2026-04-02 — 里程碑 1 核心原型落地完成

**验收状态：通过**

完成里程碑一（核心原型落地）可玩性验收，所有验收标准达标：

- ✅ 端到端测试覆盖：创建角色→行动检定→战斗→结束的完整流程（264个测试通过）
- ✅ AIDM约束验证：连续5次行动（含战斗），AI叙事无数值越权修改
- ✅ d20随机数统计：1000次投骰，每面频率分布均匀（统计测试通过）
- ✅ 角色持久化：战斗全程HP变化可追溯，每次效果都有对应裁定记录

**详细验收报告**: `docs/sessions/2026-04-02-milestone-1-playability-acceptance.md`

**主要产出**：
- 完整游戏流程闭环：角色创建 → 场景探索 → 技能检定 → 触发战斗 → 回合制战斗 → 战斗结束 → 继续探索
- 新增8个端到端冒烟测试，覆盖战士/法师/盗贼三个职业的完整游戏流程
- 战斗系统完整实现：攻击检定、伤害计算、AC对比、defeated状态、硬约束叙事
- 多步骤Agent编排：支持法术攻击（攻击+豁免+伤害）等复杂动作链

## 2026-04-02 — 可玩演示整合验收完成

**验收状态：通过**

完成可玩演示整合验收，narrative-memory-context、ai-narrator-llm-integration、game-ui-experience-polish、scene-exploration-system 全部整合完毕，游戏端到端可玩。

所有验收标准满足：

| 标准 | 状态 | 备注 |
|-----|------|------|
| 端到端测试文件 | ✅ 通过 | `tests/test_playable_demo.py` 已创建 |
| 完整流程覆盖 | ✅ 通过 | 角色创建→探索→场景切换→战斗→结束 |
| AI叙事prompt验证 | ✅ 通过 | 包含角色名、场景名、历史行动摘要 |
| 记忆系统验证 | ✅ 通过 | 多次行动后上下文累积，叙事体现历史连贯性 |
| HP变化一致性 | ✅ 通过 | 战斗全程HP变化可追溯，与裁定结果一致 |
| 状态一致性 | ✅ 通过 | 角色HP、场景、战斗状态全程一致 |
| 测试通过数 | ✅ 通过 | 343个测试通过（新增11个），无新增失败 |

**新增测试文件**：
- `app/backend/tests/test_playable_demo.py`：11个端到端测试
  - `test_playable_demo_complete_flow_warrior`：战士完整流程
  - `test_playable_demo_memory_context_accumulation`：记忆系统验证
  - `test_playable_demo_narrative_includes_scene_context`：场景上下文验证
  - `test_playable_demo_hp_tracking_throughout_combat`：HP变化追踪
  - `test_playable_demo_mage_complete_flow`：法师完整流程
  - `test_playable_demo_rogue_stealth_flow`：盗贼潜行流程
  - `test_playable_demo_state_consistency_after_multiple_actions`：状态一致性
  - `test_playable_demo_warrior_class_flow`：战士职业流程
  - `test_playable_demo_mage_class_flow`：法师职业流程
  - `test_playable_demo_rogue_class_flow`：盗贼职业流程
  - `test_playable_demo_narrative_no_numeric_overreach`：AI叙事约束验证

**系统验证结果**：
- AI叙事正确引用角色名、场景名、历史记忆
- 记忆系统在多次行动后积累上下文，叙事内容体现历史连贯性
- 游戏状态（角色HP、场景、战斗状态）在整个流程中一致且正确
- AI叙事在整个流程中无数值越权修改

**里程碑一最终状态**：✅ 可玩性验收通过，游戏端到端可玩

## 2026-04-02 — 里程碑 2 功能完整性验收

**验收状态：通过**

完成里程碑二（功能完整性）端到端验收测试，完整游戏循环各环节串联运行正常：

- ✅ 端到端测试文件：`tests/test_milestone2_acceptance.py` 已创建，包含 9 个测试用例
- ✅ 角色创建：支持战士/法师/盗贼三种职业创建，属性分配正确
- ✅ 场景探索：移动后 GET /map 的 explored_nodes 正确更新，包含已探索场景 ID
- ✅ 地图同步：current_node 与当前场景状态一致
- ✅ 战斗系统：含先攻检定、回合制、敌方 AI 行动
- ✅ 物品系统：拾取和装备物品后，GET /state 的 character.ac 和 equipped 字段正确更新
- ✅ 角色成长：XP 累积和等级提升机制验证通过
- ✅ 状态一致性：HP、inventory、level、map 在完整循环中保持同步

**新增测试文件**：
- `app/backend/tests/test_milestone2_acceptance.py`：9 个端到端验收测试
  - `test_milestone2_complete_game_loop_warrior`：战士完整游戏流程
  - `test_milestone2_map_exploration_sync`：地图探索同步验证
  - `test_milestone2_combat_with_initiative_and_ai`：战斗系统（含先攻和 AI）
  - `test_milestone2_item_equipment_updates_ac`：物品装备影响 AC 验证
  - `test_milestone2_level_up_from_xp`：XP 累积和升级验证
  - `test_milestone2_complete_flow_with_state_consistency`：全流程状态一致性
  - `test_milestone2_combat_scene_explored_after_battle`：战斗后场景探索标记
  - `test_milestone2_rogue_stealth_and_sneak_attack`：盗贼职业特性
  - `test_milestone2_mage_spell_combat`：法师法术战斗

**基础设施修复**（确保测试可运行）：
- ✅ 修复 `scenes/data.py` 缺失 `InteractiveElement` 类
- ✅ 修复 `npc.py` 缺失 `find_target_npc` 和 `is_npc_interaction` 函数
- ✅ 修复 `state.py` 缺失 `get_map_state` 函数
- ✅ 修复 `agent/orchestrator.py` 未使用的导入
- ✅ 修复 `scenes/movement.py` 对 `switch_scene` 返回值处理
- ✅ 修复 `agent/narrator.py` 缺失 `npc_target` 参数
- ✅ 修复 `routers/action.py` 物品使用检测逻辑（避免误判普通动词）

**里程碑二最终状态**：✅ 完整游戏循环验收通过，9/9 专项测试通过

## 2026-04-02 — 法师职业完整施法体验验收

**验收状态：通过**

完成法师职业完整施法体验的端到端集成审查与修复：

- ✅ 后端 `Actor` 模型补全 `hit_dice_total`、`hit_dice_remaining`、`spell_slots_max` 字段
- ✅ `rest_system.py` 中法术槽数据格式统一为 `list[SpellSlot]`，消除与模型定义的不一致
- ✅ 角色创建时正确初始化法师的 `spell_slots` 和 `spell_slots_max`
- ✅ 端到端测试覆盖：创建法师 → 施放魔法飞弹 → 法术槽消耗 → 长休恢复
- ✅ 法术槽耗尽后施法返回明确错误提示，状态不变
- ✅ 前端 `App.tsx` 的 `SpellSlotsPanel` 已在 `CharacterCard` 中针对法师职业正确渲染
- ✅ `test_spell_slot_system.py` 20/20 通过
- ✅ `test_rest_system.py` 14/14 通过（修复了此前的 6 个失败）
- ✅ 核心战斗/职业特性测试 86/86 通过

**详细审查报告**：`docs/sessions/2026-04-02-mage-spell-slots-integration-acceptance.md`

---

## 当前共识

- 前端先做本地 Web，不做 GitHub Pages，不急着做 App
- 规则设计可以参考原版规则书，但项目实现不应强依赖原版文本
- 项目目录遵循奥卡姆剃刀原则，优先保证清晰和可接手性
- 文档以摘要导航为入口，按需下钻，不预先铺开复杂层级
- 并行 agent 协作时优先分配写入范围，减少共享文件直接冲突
- 并行开发以 worktree 为主，主目录作为整合区使用
- 规则实现优先围绕"动作输入 -> 结构化裁定结果"建模，而不是围绕原版规则全文建模
- 角色系统已脱离前端静态 mock，后端提供完整角色创建和管理 API
- 战斗系统已完成完整闭环，支持标准攻击和法术攻击
- **下一优先方向**：AI叙事接入（Kimi API）和记忆/RAG系统探索

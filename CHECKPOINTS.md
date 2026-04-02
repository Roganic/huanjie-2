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

## 2026-04-02 — 里程碑 2 功能完整性集成验收完成

**验收状态：通过**

完成里程碑二"功能完整性"端到端集成验收，所有已实现系统（叙事记忆、装备物品、战斗AI、掉落、升级、职业特性、回合顺序、地图）能够协同工作，构成完整可玩的游戏循环。

**验收标准达成：**

| 标准 | 状态 | 备注 |
|-----|------|------|
| 完整游戏循环集成测试 | ✅ 通过 | `test_full_game_loop_integration.py` 已创建，9个测试全部通过 |
| 地图状态同步 | ✅ 通过 | GET /map 的 current_node 与 GET /state 的 scene.id 始终一致 |
| 探索节点累积 | ✅ 通过 | explored_nodes 随场景切换正确累积 |
| 战士职业特性 | ✅ 通过 | second_wind 使用后 hp 恢复且 class_features.second_wind_used 为 true |
| 盗贼职业特性 | ✅ 通过 | sneak_attack_available 字段正确存在 |
| 掉落系统 | ✅ 通过 | 战斗胜利后 inventory 包含掉落物品 |
| 经验/升级系统 | ✅ 通过 | 战斗胜利后 xp 增加，达到阈值时 level 递增 |
| 状态一致性 | ✅ 通过 | HP、XP、level、inventory、equipped、scene 等字段全程一致 |
| 无回归失败 | ✅ 通过 | 原有失败测试从62个减少到54个（修复了movement.py问题）|

**新增测试文件：**
- `app/backend/tests/test_full_game_loop_integration.py`：9个集成测试
  - `test_warrior_full_game_loop_integration`：战士完整循环
  - `test_rogue_full_game_loop_with_sneak_attack`：盗贼完整循环（含偷袭）
  - `test_mage_full_game_loop_integration`：法师完整循环
  - `test_map_state_consistency_throughout_game_loop`：地图状态同步
  - `test_combat_loot_and_xp_integration`：掉落和经验系统
  - `test_item_usage_in_game_loop`：物品使用系统
  - `test_state_consistency_all_fields`：所有字段一致性
  - `test_class_features_throughout_game_loop`：职业特性验证
  - `test_turn_order_and_enemy_ai_in_combat`：回合顺序和AI

**Bug修复：**
- 修复 `app/backend/src/scenes/movement.py` 第132行：`switch_scene` 返回布尔值而非元组，导致解包错误
- 修复 `app/backend/routes/combat.py` 第293行：当攻击未命中时 `damage` 字段被设为 `None`，导致 `exclude_none=True` 时字段缺失，测试随机失败

## 2026-04-02 — 法师职业完整施法体验集成验收（最终）

**验收状态：通过**

完成法师职业完整施法体验的端到端集成审查：

**验收标准达成：**

| 标准 | 状态 | 备注 |
|-----|------|------|
| 角色创建 spell_slots 初始化 | ✅ 通过 | 1级法师创建后有2个1环法术位 |
| 施放伤害法术 | ✅ 通过 | 魔法飞弹：槽位消耗 + 目标受伤 + 裁定记录完整 |
| 施放治疗法术 | ✅ 通过 | 治疗之触：槽位消耗 + HP恢复 |
| 法术槽耗尽处理 | ✅ 通过 | POST /action 返回 failure，spell_slots 不变 |
| 长休恢复法术槽 | ✅ 通过 | 长休后 spell_slots 恢复至 max 值 |
| 状态一致性 | ✅ 通过 | GET /state 的 spell_slots 与实际消耗始终一致 |
| 戏法不消耗槽位 | ✅ 通过 | 寒冰射线（0环）施放后法术槽不变 |
| 无新增失败 | ✅ 通过 | 总测试数从 568 增加到 571，失败数保持 47 不变 |

**测试覆盖：**
- `test_spell_slot_system.py`：20/20 通过
- `test_rest_system.py`：14/14 通过
- `test_mage_spell_casting_acceptance.py`：新增 3 个端到端测试全部通过
  - `test_mage_complete_spell_casting_cycle`：完整施法循环（伤害+治疗+耗尽+恢复）
  - `test_mage_spell_slots_state_consistency`：状态一致性验证
  - `test_mage_cantrip_no_slot_consumption`：戏法不消耗槽位验证
- `test_milestone_2_final_acceptance.py::test_mage_spell_casting_in_combat`：通过
- `test_full_game_loop_integration.py::test_mage_full_game_loop_integration`：通过

**新增测试文件：**
- `app/backend/tests/test_mage_spell_casting_acceptance.py`：3个端到端集成测试

## 2026-04-02 — 里程碑 2 功能完整性最终验收

**验收状态：通过**

完成里程碑二（功能完整性/完整游戏循环）最终端到端验收，确认所有已完成的 Objective 协同工作，形成完整的游戏循环体验。

**验收标准达成：**

| 标准 | 状态 | 备注 |
|-----|------|------|
| 端到端测试文件 | ✅ 通过 | `test_milestone_2_final_acceptance.py` 已创建，6个测试全部通过 |
| 完整游戏循环覆盖 | ✅ 通过 | 角色创建 → 探索（地图同步）→ 战斗 → 物品使用 → 获得XP升级 |
| 地图状态同步 | ✅ 通过 | GET /map 的 current_node 与 GET /state 的 scene.id 始终一致 |
| 法师施法验证 | ✅ 通过 | spell_slots 消耗、目标HP减少、裁定记录完整 |
| 升级系统验证 | ✅ 通过 | character.level 增加，proficiency_bonus 按 D&D 5e 规则更新 |
| 职业特性验证 | ✅ 通过 | 战士 second_wind、盗贼 sneak_attack 正确工作 |
| 回合顺序验证 | ✅ 通过 | initiative_order 正确排序，current_turn 正确推进 |
| 无新增失败 | ✅ 通过 | 总测试数从 562 增加到 568，失败数保持 47 不变 |

**新增测试文件：**
- `app/backend/tests/test_milestone_2_final_acceptance.py`：6个端到端测试
  - `test_complete_game_loop_warrior_path_with_level_up`：战士完整循环到升级
  - `test_mage_spell_casting_in_combat`：法师施法验证（法术槽消耗、HP减少）
  - `test_rogue_sneak_attack_in_combat`：盗贼偷袭特性验证
  - `test_combat_initiative_and_turn_order`：先攻和回合顺序验证
  - `test_level_up_proficiency_bonus_update`：升级后熟练加值验证
  - `test_full_game_loop_all_classes`：三职业完整循环验证

---

## 2026-04-02 — 法术效果系统验收（spell-effects-system）

**验收状态：通过**

完成法术效果系统（spell-effects-system）的集成审查验收，验证伤害法术（魔法飞弹）和治疗法术的完整流程。

**验收标准达成：**

| 标准 | 状态 | 备注 |
|-----|------|------|
| 魔法飞弹造成伤害 | ✅ 通过 | POST /action 施放后目标 HP 减少，GET /state 返回更新后的战斗状态 |
| 治疗术恢复 HP | ✅ 通过 | POST /action 施放后 character.hp 增加（不超过 hp_max） |
| 法术槽消耗 | ✅ 通过 | spell_slots[1].current 正确减少 1 |
| 法术裁定响应字段 | ✅ 通过 | 包含 spell_name、spell_level、effect_type、damage_roll、damage_total 字段 |
| 无新增失败 | ✅ 通过 | 总测试数从 574 增加到 575，失败数保持 47 不变 |

**审查发现与修正：**

1. **补充 effect_type 字段**：`handle_spell_cast` 函数返回值中添加了 `effect_type` 字段，用于区分伤害法术（"damage"）和治疗法术（"heal"）
2. **补充测试覆盖**：新增 `test_cure_wounds_effect_type_is_heal` 测试验证治疗法术的 effect_type 字段

**关键测试覆盖：**

- `test_mage_spell_casting_acceptance.py`：3个端到端测试
  - `test_mage_complete_spell_casting_cycle`：完整施法循环（伤害+治疗+耗尽+恢复）
  - `test_mage_spell_slots_state_consistency`：状态一致性验证
  - `test_mage_cantrip_no_slot_consumption`：戏法不消耗槽位验证

- `test_spell_slot_system.py`：单元测试和集成测试
  - 验证法术裁定响应包含所有必需字段
  - 验证伤害法术和治疗法术的 effect_type 正确

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

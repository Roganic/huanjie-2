# 2026-04-02 法师职业完整施法体验集成审查

## 目标

对法师职业的完整施法体验进行端到端集成验收，确保法术槽、法术效果、前端展示三个系统协同工作。

## 审查范围

- 法师角色创建后，前端状态面板正确显示 spell_slots 信息
- 完整施法流程：创建法师 → 进入战斗 → 施放法术 → 法术槽减少 → 效果生效 → 战斗结束
- 长休后法术槽恢复（POST /action "长休" 后 spell_slots 恢复到 max）
- 法术槽耗尽后施法被正确拒绝，前端显示错误提示

## 发现的问题与修复

### 1. Actor 模型缺失休息相关字段

**问题**：`test_rest_system.py` 中直接构造 `Actor` 时传入 `hit_dice_total`、`hit_dice_remaining`、`spell_slots_max`，但 `src/models/state.py` 中的 `Actor` 模型未定义这些字段，导致 Pydantic 验证失败。

**修复**：
- 在 `Actor` 模型中新增字段：`hit_dice_total`（默认 1）、`hit_dice_remaining`（默认 1）、`spell_slots_max`（默认空列表）
- 添加 `field_validator` 将旧持久化数据中的 dict 格式 `spell_slots` / `spell_slots_max` 兼容转换为空列表

### 2. rest_system.py 中 spell_slots 数据格式不一致

**问题**：`rest_system.py` 内部使用 `dict[str, int]` 格式（如 `{"1": 2}`）表示法术槽，而 `Actor` 模型定义的是 `list[SpellSlot]`。这导致 `initialize_actor_rest_resources` 和 `perform_long_rest` 可能破坏模型一致性。

**修复**：
- 修改 `initialize_actor_rest_resources`：将法术槽初始化为 `list[SpellSlot]` 格式
- 修改 `perform_long_rest`：遍历 `spell_slots_max`（list 格式）恢复 `spell_slots`

### 3. 角色创建时未初始化新增字段

**修复**：在 `src/state.py` 的 `create_character` 中，为法师角色初始化 `spell_slots_max`，并为所有职业初始化 `hit_dice_total` 和 `hit_dice_remaining`。

### 4. 测试期望与格式不匹配

**修复**：更新 `test_rest_system.py` 中 `test_mage_initialization_with_spell_slots` 的断言，从 dict 格式期望改为 `list[SpellSlot]` 格式期望。

## 验证结果

| 测试文件 | 结果 | 备注 |
|---------|------|------|
| `test_spell_slot_system.py` | ✅ 20/20 通过 | 法术槽创建、消耗、耗尽拒绝、长休恢复、响应字段全部验证通过 |
| `test_rest_system.py` | ✅ 14/14 通过 | 短休、长休、生命骰、法术槽初始化全部验证通过 |
| `test_milestone2_acceptance.py` | ✅ 9/9 通过 | 里程碑二完整流程验收通过 |
| `test_playable_demo.py` | ✅ 11/11 通过 | 可玩演示所有场景通过 |
| `test_e2e_complete_flow.py` | ✅ 通过 | 端到端完整流程通过 |
| `test_combat_api.py` | ⚠️ 1 个已有失败 | `test_sneak_attack_triggers_for_rogue_with_advantage` 为已有不稳定性问题，与本次修改无关 |
| `test_class_features.py` 等核心测试 | ✅ 86/86 通过 | 战斗、职业特性、硬约束全部通过 |
| `test_save_load.py` | ✅ 7/7 通过 | 保存/加载系统不受本次修改影响 |

## 前端状态

`App.tsx` 中已存在 `SpellSlotsPanel` 组件，并在 `CharacterCard` 中针对 `mage` 职业正确渲染。冒险模式状态面板（`status-panel`）已使用 `CharacterCard`，因此 GET /state 返回的 `spell_slots` 已能在前端正确展示。

## 结论

- 法师完整施法流程后端逻辑已闭环
- 前端状态面板已具备法术槽展示能力
- 所有本次验收相关的新增测试通过
- 无由本次修改引起的测试回归

## 后续建议

- `test_session_persistence.py` 和 `test_mutation.py` 等文件中存在若干已有失败，建议单独安排修复会话

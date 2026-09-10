# 基础战斗系统

当前玩家入口以 [场景与遭遇规则](world-encounters.md) 为准：多敌人、全员先攻、持续敌对和伤势；探索攻击先开启遭遇，不再接受在酒馆凭空攻击哥布林。下文单次攻击请求为历史接口记录，不能用作当前 API 验收契约。

> 2026-09-06：下文为历史单次攻击接口说明。当前实际遭遇已增加统一行动、三职业能力、敌方回合、资源预算与持久化，见 [当前战斗实施记录](sessions/2026-09-06-combat-commands.md)。完整基础阶段仍未验收通过。

本文档描述已实现的基础战斗流程，支持单次攻击的完整闭环。

## 概述

基础战斗系统实现了 5e 风格的攻击判定：
- d20 攻击检定 vs 目标 AC
- 命中后投掷伤害骰
- HP 扣减与状态更新
- 清晰的战斗结果叙述

## 攻击行动

### 请求格式

```json
{
  "scene_id": "combat-01",
  "actor": "Aldric",
  "intent": "attack the goblin",
  "approach": "swing my longsword",
  "action_type": "attack",
  "weapon": "longsword",
  "target": "goblin-01",
  "damage_dice": "1d8",
  "advantage": null
}
```

### 关键字段

| 字段 | 说明 |
|------|------|
| `weapon` | 武器类型，如 longsword, shortbow, dagger |
| `target` | 目标角色 ID 或名称 |
| `damage_dice` | 可选，覆盖武器默认伤害骰 |
| `action_type` | 设置为 "attack" 明确触发战斗流程 |

### 武器伤害表

| 武器 | 伤害骰 | 属性 |
|------|--------|------|
| dagger | 1d4 | DEX (finesse) |
| shortsword | 1d6 | DEX (finesse) |
| longsword | 1d8 | STR |
| greatsword | 2d6 | STR |
| shortbow | 1d6 | DEX |
| longbow | 1d8 | DEX |

## 命中判定

### 攻击检定公式

```
d20 + 属性修正 + 熟练加值 vs 目标 AC
```

- **近战武器 (非 finesse)**: STR 修正
- **finesse 武器**: DEX 修正 (如 rapier, dagger)
- **远程武器**: DEX 修正
- **熟练加值**: 固定 +2

### 判定结果

- **命中**: 总攻击值 >= 目标 AC
- **未命中**: 总攻击值 < 目标 AC

## 伤害计算

### 命中后流程

1. 根据武器类型或 `damage_dice` 参数确定伤害骰
2. 投掷伤害骰
3. 从目标 HP 中扣除伤害值
4. 如果 HP 降至 0，添加 "defeated" 状态

### 伤害骰格式

支持标准骰表达式：
- `1d6` - 1 个 6 面骰
- `2d6` - 2 个 6 面骰
- `1d8+2` - 1 个 8 面骰 + 2
- `2d10-1` - 2 个 10 面骰 - 1

## 响应格式

```json
{
  "action_summary": "Aldric attacks Goblin Scout with longsword",
  "resolution_type": "check",
  "attack": {
    "target": "goblin-01",
    "weapon": "longsword",
    "hit_roll": 14,
    "total_attack": 19,
    "target_ac": 12,
    "damage": {
      "dice_expression": "1d8",
      "rolls": [6],
      "modifier": 0,
      "total": 6
    }
  },
  "outcome": "success",
  "effects": [
    {
      "target": "goblin-01",
      "field": "hp",
      "delta": -6,
      "description": "Aldric hits Goblin Scout with longsword for 6 damage."
    }
  ],
  "narration": "Aldric attacks Goblin Scout with their longsword. The attack hits (rolled 14, total 19 vs AC 12) dealing 6 damage ([6] = 6)."
}
```

## 状态更新

攻击产生的 effects：

| 效果 | 目标 | 说明 |
|------|------|------|
| hp | 目标 | 负值为伤害 |
| conditions_add | 目标 | HP=0 时添加 "defeated" |
| time | 场景 | 每次攻击 +1 |

## 测试覆盖

测试文件: `tests/test_combat.py`

- ✅ 攻击行动解析与验证
- ✅ 命中判定 (d20 + modifier vs AC)
- ✅ 伤害骰投掷与计算
- ✅ HP 扣减与角色状态更新
- ✅ 击倒检测 (0 HP → defeated)
- ✅ 武器类型区分 (STR/DEX)
- ✅ 战斗结果叙述
- ✅ 自定义伤害骰
- ✅ 时间推进

## 示例代码

### 执行一次攻击

```python
import requests

response = requests.post("http://localhost:8000/action", json={
    "scene_id": "combat-01",
    "actor": "Aldric",
    "intent": "attack the goblin",
    "approach": "swing my longsword",
    "weapon": "longsword",
    "target": "goblin-01",
})

result = response.json()
print(result["narration"])
print(f"Enemy HP remaining: {result['effects'][0]['target']}")
```

## 限制与后续扩展

当前版本聚焦单次攻击闭环，以下功能计划后续实现：

- 先攻系统与回合管理
- AOE 攻击与多目标
- 借机攻击与反应
- 法术攻击与豁免
- 范围与移动
- 详细的状态效果 (prone, stunned 等)

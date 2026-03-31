# Action Types - GM 裁定支持

本文档描述后端 GM 裁定系统支持的行动类型及其分类、裁定规则。

## 支持的行动类型 (V1)

后端支持 5 种行动类型：

| 类型 | 标识符 | 描述 | 示例 |
|------|--------|------|------|
| MOVE | `move` | 物理移动、 repositioning | 行走、攀爬、潜行、跳跃 |
| ATTACK | `attack` | 攻击、伤害性行动 | 近战、远程、法术攻击 |
| SOCIAL | `social` | 社交、影响他人 | 说服、欺骗、恐吓、谈判 |
| EXPLORE | `explore` | 探索、信息收集 | 搜索、调查、感知、追踪 |
| INTERACT | `interact` | 物品/环境交互 | 开锁、拾取、使用物品 |

## 自动分类

系统通过关键词匹配自动识别行动类型：

```python
# 自动分类示例
classify_action_type("walk to the door", "casually")  # -> MOVE
classify_action_type("attack the goblin", "with sword")  # -> ATTACK
classify_action_type("persuade the guard", "to help")  # -> SOCIAL
classify_action_type("search the room", "for clues")  # -> EXPLORE
classify_action_type("unlock the chest", "carefully")  # -> INTERACT
```

### 分类优先级

当关键词可能匹配多个类型时，按以下优先级：

1. SOCIAL (优先于 ATTACK，因为 "charm" 等词在社交场景更常见)
2. ATTACK
3. EXPLORE
4. INTERACT
5. MOVE

## 自动成功规则

不同行动类型的自动成功规则不同：

| 类型 | 自动成功条件 | 永不自动成功 |
|------|-------------|-------------|
| MOVE | 基础移动 (walk to, sit down) | 涉及障碍、守卫、隐藏敌人 |
| INTERACT | 简单物品操作 (pick up, put down) | 涉及锁定、陷阱、复杂机制 |
| EXPLORE | 基础观察 (look around, look at) | 搜索隐藏物品、秘密通道 |
| ATTACK | 永不 | 所有攻击都需要检定 |
| SOCIAL | 永不 | 所有社交互动都需要检定 |

### 自动成功取消词

以下词汇出现时，即使匹配自动成功短语，也不会自动成功：

```
locked, trapped, guard, convince, persuade, deceive, lie, trick,
sneak, steal, force, break, dangerous, difficult, careful, secret,
hidden, enemy, hostile, opponent, combat, battle, fight, opposed, resist
```

## 属性推断

系统根据行动类型自动推断适用的属性：

### MOVE
- **DEX**: 潜行、隐藏、杂技动作
- **STR**: 攀爬、跳跃、游泳、强行移动
- **CON**: 长距离移动、耐力维持

### ATTACK
- **STR**: 近战攻击、斩击、刺击、格斗
- **DEX**: 远程攻击、射击、投掷
- **INT**: 奥术法术
- **WIS**: 神圣/自然法术
- **CHA**: 魅惑、恐惧、幻术

### SOCIAL
- **CHA**: 说服、欺骗、恐吓、魅惑
- **INT**: 谈判、逻辑辩论
- **WIS**: 洞察、安抚、咨询

### EXPLORE
- **WIS**: 感知、察觉、追踪、聆听
- **INT**: 调查、检查、研究、分析
- **DEX**: 潜行、无声移动

### INTERACT
- **DEX**: 开锁、解除陷阱、精细操作
- **STR**: 强行开启、举起、推拉
- **INT**: 解读、解码、复杂机制

## DC 分配

系统根据行动类型和关键词分配难度等级：

| 难度 | DC | 触发条件 |
|------|-----|---------|
| Easy | 10 | 简单、友好目标、生锈/老旧的机制 |
| Medium | 15 | 默认难度 |
| Hard | 20 | 困难、敌对目标、隐藏物品、魔法锁定、特殊攻击 |

### 类型特定规则

- **ATTACK**: 特殊攻击 (缴械、绊倒) 为 Hard DC
- **SOCIAL**: 敌对目标为 Hard，友好目标为 Easy
- **EXPLORE**: 搜索隐藏物品为 Hard
- **INTERACT**: 锁定/陷阱/魔法机制为 Hard

## 效果生成

不同行动类型的成功/失败会产生不同的效果：

### 成功效果

| 类型 | 成功效果 |
|------|---------|
| ATTACK | 造成伤害 (2-5 点) |
| MOVE | 可能获得隐蔽状态 (潜行成功) |
| SOCIAL | 获得影响力状态 |
| EXPLORE | 获得信息状态 |
| INTERACT | 解锁/改变物品状态 |

### 失败效果

| 类型 | 失败效果 |
|------|---------|
| ATTACK | 获得暴露/脆弱状态 |
| MOVE | 攀爬/跳跃失败造成伤害，其他产生噪音 |
| SOCIAL | 获得怀疑状态 |
| EXPLORE | 获得困惑状态 |
| INTERACT | 复杂操作造成伤害，其他沮丧状态 |
| 所有物理属性 | 额外 -1 HP (体力消耗) |

## API 使用

### 自动分类

```json
POST /action
{
  "scene_id": "dungeon-01",
  "actor": "Aldric",
  "intent": "attack the goblin",
  "approach": "with my sword"
}
```

响应：
```json
{
  "action_summary": "Aldric attempts to attack the goblin by with my sword",
  "action_type": "attack",
  "resolution_type": "check",
  "check": {
    "ability": "str",
    "modifier": 3,
    "proficiency_bonus": 2,
    "roll": 15,
    "total": 20,
    "dc": 15
  },
  "outcome": "success",
  "effects": [
    {"target": "scene", "field": "time", "delta": 1, "description": "Time passes."},
    {"target": "target", "field": "hp", "delta": -5, "description": "The attack hits and deals 5 damage."}
  ],
  "narration": "Aldric attempts to attack the goblin by with my sword — your attack succeeds (rolled 20 vs DC 15)."
}
```

### 显式指定类型

```json
POST /action
{
  "scene_id": "dungeon-01",
  "actor": "Aldric",
  "intent": "do something mysterious",
  "approach": "carefully",
  "action_type": "explore"
}
```

## 扩展性

添加新行动类型的步骤：

1. 在 `ActionType` enum 中添加新类型
2. 在 `_ACTION_TYPE_KEYWORDS` 中添加分类关键词
3. 在 `_DEFAULT_ABILITY_BY_TYPE` 中添加默认属性
4. 在 `_ABILITY_HINTS_BY_TYPE` 中添加属性推断提示
5. 在 `_is_auto_success()` 中添加自动成功规则
6. 在 `_pick_dc()` 中添加 DC 分配规则
7. 在 `_build_success_effects()` 和 `_build_failure_effects()` 中添加效果
8. 添加对应的测试

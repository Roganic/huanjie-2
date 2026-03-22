# OSE MVP 规则提炼

## 目标

从 OSE 提炼适合 AI 稳定执行的低复杂度机制，供后续规则整合者回写。

## 六个核心问题

| 问题 | 结论 | MVP 决策 |
| --- | --- | --- |
| 1. 角色创建复杂度如何 | 中等。选项不算爆炸，但步骤多，且依赖职业表、攻击值、豁免、装备限制等派生信息。 | 不直接照搬。改成模板化或半随机创建。 |
| 2. 核心检定机制是什么 | 不是单一机制，而是多种轻量口径并存：属性检定、攻击检定、豁免、x-in-6、2d6 士气。 | 收敛成一个主检定接口，最多保留少数特化子接口。 |
| 3. 战斗状态管理复杂度如何 | 中低。战斗轮次短，但移动、施法中断、掩体、士气、特殊免疫会增加状态负担。 | MVP 只保留最短战斗闭环。 |
| 4. AI 最容易出错的部分是什么 | 多种检定口径串台、THAC0/降序 AC、职业派生值漏算、关键例外忘记执行。 | 系统内置派生与结算，不让模型手算。 |
| 5. 哪些机制值得保留到 MVP | 行动声明优先、统一轻量检定、边先攻、一次攻击、HP/伤害/死亡、资源压力。 | 保留。 |
| 6. 哪些机制应该砍掉或延后 | THAC0、复杂查表、完整法术细则、细碎战术修正、多单位管理。 | 砍掉或延后。 |

## 可直接保留的机制

### 流程

- 玩家先声明行动
- GM / 规则层判断是否自动成功、需要检定、还是直接结算
- 结果应返回结构化后果，而不是只给自然语言描述

### 判定

- 只保留一个主检定接口
- 属性修正保留，但不保留多种骰制并存的原样表达
- 命中用升序 AC 口径

### 战斗

- 边先攻
- 一轮一次主动作
- 命中后直接结算伤害
- `0 HP` 触发明确失败后果

### 资源

- HP
- 装备 / 物品位
- 时间推进
- 基础补给压力

## 不建议原样保留的机制

- THAC0 / attack matrix
- x-in-6 开门等零散专用概率口径
- 五类豁免的完整玩家侧暴露
- 完整法术中断与细节条件
- 远程距离档与掩体修正全开
- 追逐、遭遇距离、惊奇、士气的完整旧式流程
- retainers / mercenaries / hirelings 的多人管理

## AI 风险清单

| 风险 | 原因 | 处理建议 |
| --- | --- | --- |
| 判定口径混淆 | d20 向下、d20 向上、x-in-6、2d6 并存 | 统一主检定 |
| 命中结算错误 | THAC0 与降序 AC 不直观 | 改升序 AC，并由系统自动计算 |
| 创建阶段漏项 | 职业派生值多 | 用模板或自动生成 |
| 战斗例外遗漏 | 撤退、施法中断、怪物免疫都很关键 | 首版只保留少数硬规则 |
| 裁定松紧不一 | OSE 依赖裁判经验 | 把触发条件写成模板 |

## 推荐给整合者的最小规则包

1. 统一属性检定
2. 升序 AC 命中结算
3. 边先攻
4. 一轮一次攻击
5. HP / 伤害 / 死亡
6. 基础时间与资源推进

## 参考来源

- https://oldschoolessentials.necroticgnome.com/srd/index.php/Main_Page
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Creating_a_Character
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Ability_Scores
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Ability_Checks
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Saving_Throws
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Combat
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Encounters
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Morale_%28Optional_Rule%29
- https://oldschoolessentials.necroticgnome.com/srd/index.php/Damage%2C_Healing%2C_and_Death

# OSE 面向 AI 稳定执行的规则分析笔记

## 范围

目标是回答一个具体问题：OSE 中哪些机制适合提炼进“AI 可稳定执行、低复杂度”的 MVP 规则内核。

本笔记基于官方 OSE SRD 在线页面整理。当前 worktree 中未找到用户提到的本地 HTML 导出文件，因此本次以官方在线 SRD 为依据。

## 总结结论

- OSE 的优势不在“机制少到没有规则”，而在“流程短、边界清楚、例外密度低”
- 适合 AI 的不是 OSE 的全部传统表达，而是它的结构：先声明行动，再做必要裁定，再快速结算
- 对 MVP 最有价值的是统一的轻量检定、简短战斗轮次、清楚的死亡与资源压力
- 对 AI 最不友好的部分是并存的多种判定口径、旧式命中表达、职业特有子系统和需要裁判大量临场解释的边缘细则

## 1. 角色创建复杂度如何

结论：中等，不算重构筑，但步骤较多，且存在若干旧式信息分散点。

依据：

- 角色创建流程有 13 个步骤：掷属性、选职业、调主属性、记录修正、记录攻击值、记录豁免和职业能力、掷生命、选阵营、记语言、买装备、记 AC、记等级 XP、命名
- 属性为 6 项，默认 `3d6` 逐项生成
- 职业直接决定种族归属；若选矮人、精灵、半身人，则是种族职业合一
- 一些职业有最低属性要求
- 允许通过降低非主属性提升主属性，但只允许降低力量、智力、感知，且不能降到 9 以下

对 AI / MVP 的含义：

- 对真人玩家而言不算特别复杂，但对系统实现来说，创建流程是“多步骤表单 + 多处规则引用”
- 真正的复杂度不在“选项很多”，而在“角色纸上要同时记录 THAC0、攻击表、豁免、职业能力、装备限制”
- 如果 MVP 目标是快速开局，原样照搬会拖慢首局进入速度

建议：

- MVP 不保留完整 OSE 角色创建流程
- 采用预设模板或半随机模板，最多保留“属性、职业原型、HP、装备包、阵营倾向”这几个输入
- 不要求用户手填 THAC0 攻击表，改为系统内部派生

## 2. 核心检定机制是什么

结论：OSE 并不是单一统一检定系统，而是多个轻量判定机制并存。

主要口径：

- 属性检定：`1d20` 掷出小于等于属性值成功；裁判可给 `-4` 到 `+4` 修正
- 攻击检定：默认使用 THAC0 / 攻击矩阵；可选升序 AC 作为简化
- 豁免：`1d20` 掷出大于等于对应豁免值成功
- 属性附带若干派生小规则，例如开门是 `x-in-6`
- 士气是 `2d6` 口径

对 AI / MVP 的含义：

- OSE 的“轻量”不等于“统一”
- 人类裁判习惯这些并存子系统，但 AI 在长流程里更容易把“d20 向下检定 / d20 向上检定 / x-in-6 / 2d6”混淆
- 所以如果目标是稳定执行，不能直接把 OSE 当作一个统一判定框架接入

建议：

- MVP 只保留一个主检定接口
- 战斗命中改为升序 AC 口径，不保留 THAC0 面向用户的表达
- `x-in-6`、多种专属骰制和细分豁免类别尽量收敛到统一判定层

## 3. 战斗状态管理复杂度如何

结论：中等偏低，轮次短，但局部例外和传统细节会抬高实现成本。

简单之处：

- 每轮流程明确：声明法术和近战移动、按边 initiative、行动顺序固定
- 默认按阵营 / 边来投先攻，而不是全员单独排序
- 普通 PC 通常每轮一次攻击
- 命中后直接掷伤害，降到 `0 HP` 即死亡

复杂点：

- 近战中的移动有专门规则，区分 fighting withdrawal 和 retreat
- 远程攻击还要处理距离档与掩体修正
- 法术需要预声明，失去先攻且在自己行动前受击或豁免失败会被打断且法术位消耗
- 怪物可能有多段攻击、特殊免疫、士气检查
- 默认命中流程依赖 THAC0 / 攻击矩阵

对 AI / MVP 的含义：

- 如果只做“近战命中-伤害-死亡”这一层，OSE 很适合
- 如果同时保留掩体、撤退、施法打断、士气、多攻击、特殊免疫，AI 的状态维护压力会明显上升

建议：

- MVP 保留边先攻、一次攻击、简单移动、HP、死亡
- 撤退、掩体、施法打断、士气可以作为二阶段机制，而不是首版全开

## 4. AI 最容易出错的部分是什么

### A. 多种判定口径并存

- 属性检定是 d20 向下
- 豁免是 d20 向上
- 攻击默认查 THAC0 / attack matrix
- 其他场景还会出现 `x-in-6` 和 `2d6`

这会导致模型在长对话里发生“口径串台”。

### B. 旧式命中表达

- THAC0 与降序 AC 对现代用户和模型都不直观
- 虽然 OSE 提供升序 AC 作为可选规则，但默认主文本仍保留旧式表达

### C. 角色创建中的隐性派生值

- 攻击值、豁免、职业能力、语言、装备限制都依赖职业和表格
- 这些数据如果不由系统预先生成，AI 容易漏记或算错

### D. 战斗中的少量但关键的例外

- 近战撤退与撤离不同
- 施法需要事先声明
- 施法中断会消耗已准备法术
- 特殊怪物免疫会覆盖普通命中结论

这类规则不多，但都足够关键，出错一次就会影响玩家信任。

### E. 探索流程中的裁判自由度

- OSE 很依赖裁判决定何时检定、何时给修正、何时触发风险
- 人类裁判可以凭经验稳定执行；AI 若没有标准模板，容易出现忽严忽松

## 5. 哪些机制值得保留到 MVP

### 强烈建议保留

- 行动声明优先：先说做什么，再决定是否检定
- 轻量主检定：用一个统一接口承接大多数不确定行动
- 边先攻：比逐人排序更稳、更省状态
- 一轮一次主动作的快战斗
- HP / 伤害 / 0 HP 死亡这一套直接后果链
- 简单属性修正：力量影响近战，敏捷影响远程和防御等
- 资源压力的设计方向：装备、补给、时间应有存在感

### 可保留但应现代化表达

- 升序 AC，替代 THAC0 暴露给玩家
- 怪物士气，但应改成更少触发点或由系统自动触发
- 施法被打断，但最好只在明确模板下使用

## 6. 哪些机制应该砍掉或延后

### MVP 直接砍掉

- 向玩家暴露 THAC0 / attack matrix
- `x-in-6`、d20 向下、d20 向上、`2d6` 并存的完整原样表达
- 大量职业特有子系统
- 需要频繁查表的细节

### 延后二期

- 完整法术清单与施法细则
- 掩体、距离档、撤退细分等战术细节
- 全量豁免类别
- 士气、追逐、遭遇距离、惊奇等探索-战斗连接层的完整复刻
- retainers / hirelings / mercenaries 这类多单位管理机制

## 适合回写到规则内核的核心判断

- 保留 OSE 的流程结构，不保留其所有旧式表示法
- 让系统负责派生值与结算，不让玩家或 GM agent 手工查表
- 对 AI 来说，“规则少 + 口径统一”比“规则原汁原味”更重要

## 本次参考来源

- OSE SRD Main Page: https://oldschoolessentials.necroticgnome.com/srd/index.php/Main_Page
- OSE SRD Creating a Character: https://oldschoolessentials.necroticgnome.com/srd/index.php/Creating_a_Character
- OSE SRD Ability Scores: https://oldschoolessentials.necroticgnome.com/srd/index.php/Ability_Scores
- OSE SRD Ability Checks: https://oldschoolessentials.necroticgnome.com/srd/index.php/Ability_Checks
- OSE SRD Saving Throws: https://oldschoolessentials.necroticgnome.com/srd/index.php/Saving_Throws
- OSE SRD Combat: https://oldschoolessentials.necroticgnome.com/srd/index.php/Combat
- OSE SRD Encounters: https://oldschoolessentials.necroticgnome.com/srd/index.php/Encounters
- OSE SRD Morale (Optional Rule): https://oldschoolessentials.necroticgnome.com/srd/index.php/Morale_%28Optional_Rule%29
- OSE SRD Damage, Healing, and Death: https://oldschoolessentials.necroticgnome.com/srd/index.php/Damage%2C_Healing%2C_and_Death

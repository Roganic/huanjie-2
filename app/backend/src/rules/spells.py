"""法术规则模块 - 定义法术数据和规则。

本模块扩展现有法术系统，添加火球术（3环）和治疗术（1环），
并提供法术槽规则查询接口。
"""

from __future__ import annotations

from typing import Optional

# 5e 法师法术槽表（按等级）
# 格式: {character_level: {spell_level: max_slots}}
WIZARD_SPELL_SLOTS_TABLE: dict[int, dict[int, int]] = {
    1:  {1: 2},
    2:  {1: 3},
    3:  {1: 4, 2: 2},
    4:  {1: 4, 2: 3},
    5:  {1: 4, 2: 3, 3: 2},
    6:  {1: 4, 2: 3, 3: 3},
    7:  {1: 4, 2: 3, 3: 3, 4: 1},
    8:  {1: 4, 2: 3, 3: 3, 4: 2},
    9:  {1: 4, 2: 3, 3: 3, 4: 3, 5: 1},
    10: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2},
    11: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    12: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1},
    13: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    14: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1},
    15: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    16: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1},
    17: {1: 4, 2: 3, 3: 3, 4: 3, 5: 2, 6: 1, 7: 1, 8: 1, 9: 1},
    18: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 1, 7: 1, 8: 1, 9: 1},
    19: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 1, 8: 1, 9: 1},
    20: {1: 4, 2: 3, 3: 3, 4: 3, 5: 3, 6: 2, 7: 2, 8: 1, 9: 1},
}


def get_wizard_spell_slots(level: int) -> dict[int, int]:
    """获取法师在指定等级的法术槽配置。

    Args:
        level: 角色等级 (1-20)

    Returns:
        {spell_level: max_slots} 字典
    """
    level = max(1, min(20, level))
    return WIZARD_SPELL_SLOTS_TABLE.get(level, {1: 2})


def get_spell_slot_max(character_class: str, character_level: int, spell_level: int) -> int:
    """获取指定职业、角色等级下某环法术槽的最大值。

    Args:
        character_class: 职业名称 (如 "mage")
        character_level: 角色等级
        spell_level: 法术环级 (1-9)

    Returns:
        该环法术槽的最大数量，如果不可用则返回 0
    """
    if character_class.lower() != "mage":
        return 0

    slots = get_wizard_spell_slots(character_level)
    return slots.get(spell_level, 0)


# ---------------------------------------------------------------------------
# 法术定义 - 扩展现有法术注册表
# ---------------------------------------------------------------------------

# 火球术（3环）- 标准 5e 火球术
FIREBALL_L3_DATA = {
    "id": "fireball_l3",
    "name": "Fireball",
    "name_cn": "火球术",
    "level": 3,
    "school": "evocation",
    "damage_dice": "8d6",
    "damage_type": "fire",
    "saving_throw_ability": "dex",
    "saving_throw_dc_base": 8,
    "range_ft": 150,
    "casting_time": "1 action",
    "description": "你向目标点射出一颗爆裂的火球，20英尺半径范围内所有生物必须通过敏捷豁免，失败则受到 8d6 火焰伤害，成功则减半。",
    "available_to": ["mage"],
}

# 治疗术（1环）- 牧师专属（扩展预留）
CURE_WOUNDS_L1_DATA = {
    "id": "cure_wounds_cleric",
    "name": "Cure Wounds",
    "name_cn": "治疗术",
    "level": 1,
    "school": "evocation",
    "healing_dice": "1d8",
    "healing_bonus_ability": "wis",
    "range_ft": 5,
    "casting_time": "1 action",
    "description": "你触碰一个生物，为其恢复 1d8+感知调整值 点生命值（牧师专属）。",
    "available_to": ["cleric"],
}


def register_extended_spells() -> None:
    """将扩展法术注册到现有法术注册表中。"""
    try:
        from ..spells.spell_registry import SPELLS
        from ..spells.spell_models import Spell, DamageType, SpellSchool

        # 注册3环火球术（覆盖现有1环版本）
        fireball_l3 = Spell(
            id="fireball_l3",
            name="Fireball",
            name_cn="火球术",
            level=3,
            school=SpellSchool.EVOCATION,
            damage_dice="8d6",
            damage_type=DamageType.FIRE,
            saving_throw_ability="dex",
            saving_throw_dc_base=8,
            range_ft=150,
            casting_time="1 action",
            description=FIREBALL_L3_DATA["description"],
            available_to=["mage"],
        )
        SPELLS["fireball_l3"] = fireball_l3
        # 更新火球术别名为3环版本
        SPELLS["火球术"] = fireball_l3
        SPELLS["fireball"] = fireball_l3

        # 注册治疗术（牧师专属）
        cure_wounds_cleric = Spell(
            id="cure_wounds_cleric",
            name="Cure Wounds",
            name_cn="治疗术",
            level=1,
            school=SpellSchool.EVOCATION,
            healing_dice="1d8",
            healing_bonus_ability="wis",
            range_ft=5,
            casting_time="1 action",
            description=CURE_WOUNDS_L1_DATA["description"],
            available_to=["cleric"],
        )
        SPELLS["cure_wounds_cleric"] = cure_wounds_cleric
        # 治疗术别名指向牧师专属版本（扩展注册表）
        SPELLS["治疗术"] = cure_wounds_cleric

    except ImportError:
        pass  # 如果导入失败，静默跳过

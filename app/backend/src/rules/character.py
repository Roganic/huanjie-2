"""角色规则模块 - 法术槽初始化和角色规则。

本模块提供基于 5e 规则的法术槽初始化逻辑，
供角色创建时使用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .spells import get_wizard_spell_slots

if TYPE_CHECKING:
    pass


def init_spell_slots(character_class: str, level: int) -> list[dict]:
    """根据职业和等级初始化法术槽。

    Args:
        character_class: 职业名称 (如 "mage", "cleric", "warrior")
        level: 角色等级 (1-20)

    Returns:
        法术槽列表，每项格式为 {"level": int, "max": int, "current": int}
        非施法职业返回空列表
    """
    class_lower = character_class.lower()

    if class_lower == "mage":
        slots_config = get_wizard_spell_slots(level)
        return [
            {"level": spell_level, "max": max_slots, "current": max_slots}
            for spell_level, max_slots in sorted(slots_config.items())
        ]

    # 未来扩展：牧师、游侠等施法职业
    # if class_lower == "cleric":
    #     return _init_cleric_spell_slots(level)

    return []


def get_spell_slots_after_level_up(
    character_class: str,
    old_level: int,
    new_level: int,
    current_slots: list[dict],
) -> list[dict]:
    """计算升级后的法术槽配置。

    Args:
        character_class: 职业名称
        old_level: 升级前等级
        new_level: 升级后等级
        current_slots: 当前法术槽列表

    Returns:
        更新后的法术槽列表
    """
    class_lower = character_class.lower()

    if class_lower != "mage":
        return current_slots

    new_config = get_wizard_spell_slots(new_level)

    # 构建当前槽的查找表
    current_by_level = {slot["level"]: slot for slot in current_slots}

    result = []
    for spell_level, new_max in sorted(new_config.items()):
        if spell_level in current_by_level:
            old_slot = current_by_level[spell_level]
            old_max = old_slot["max"]
            # 新增的槽位以满值加入
            added = new_max - old_max
            new_current = old_slot["current"] + max(0, added)
            result.append({
                "level": spell_level,
                "max": new_max,
                "current": min(new_current, new_max),
            })
        else:
            # 新解锁的法术环级，满值加入
            result.append({
                "level": spell_level,
                "max": new_max,
                "current": new_max,
            })

    return result

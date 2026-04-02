"""休息与恢复系统 - 短休和长休机制"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models.state import Actor, CharacterClass


# 职业生命骰大小 (D&D 5e 标准)
CLASS_HIT_DICE: dict[CharacterClass, int] = {
    "warrior": 10,  # 战士 d10
    "rogue": 8,     # 盗贼 d8
    "mage": 6,      # 法师 d6
}

# 法师法术位 (V1简化版，1-3级)
MAGE_SPELL_SLOTS = {
    1: {"1": 2},  # 1级法师：2个1环法术位
    2: {"1": 3},  # 2级法师：3个1环法术位
    3: {"1": 4, "2": 2},  # 3级法师：4个1环，2个2环
}


def get_hit_die_size(character_class: CharacterClass | None) -> int:
    """获取职业的生命骰大小"""
    if character_class is None:
        return 8  # 默认 d8
    return CLASS_HIT_DICE.get(character_class.value, 8)


def roll_hit_die(hit_die_size: int) -> int:
    """掷生命骰，返回结果 (1dX)"""
    return random.randint(1, hit_die_size)


def calculate_short_rest_hp_gain(actor: Actor) -> tuple[int, int]:
    """计算短休恢复的HP
    
    Returns:
        tuple: (恢复的HP, 使用的生命骰数量)
    """
    if actor.hit_dice_remaining <= 0:
        return 0, 0
    
    hit_die_size = get_hit_die_size(actor.character_class)
    con_mod = actor.abilities.modifier("con")
    
    # 掷生命骰 + 体质修正
    die_roll = roll_hit_die(hit_die_size)
    hp_gain = max(1, die_roll + con_mod)  # 至少恢复1点HP
    
    # 确保不超过最大HP
    actual_gain = min(hp_gain, actor.hp_max - actor.hp)
    
    return actual_gain, 1  # 短休消耗1个生命骰


def perform_short_rest(actor: Actor) -> tuple[Actor, dict]:
    """执行短休
    
    Returns:
        tuple: (更新后的Actor, 结果信息字典)
    """
    if actor.hit_dice_remaining <= 0:
        return actor, {
            "success": False,
            "message": "没有剩余的生命骰可用于短休",
            "hp_gained": 0,
            "hit_dice_used": 0,
        }
    
    hp_gain, dice_used = calculate_short_rest_hp_gain(actor)
    
    if hp_gain <= 0:
        return actor, {
            "success": False,
            "message": "HP已满，无需短休恢复",
            "hp_gained": 0,
            "hit_dice_used": 0,
        }
    
    # 创建更新后的 actor
    updated_actor = actor.model_copy(
        update={
            "hp": min(actor.hp_max, actor.hp + hp_gain),
            "hit_dice_remaining": actor.hit_dice_remaining - dice_used,
        }
    )
    
    hit_die_size = get_hit_die_size(actor.character_class)
    
    return updated_actor, {
        "success": True,
        "message": f"短休完成，掷出 1d{hit_die_size} 恢复 {hp_gain} 点HP",
        "hp_gained": hp_gain,
        "hit_dice_used": dice_used,
        "hit_die_size": hit_die_size,
    }


def perform_long_rest(actor: Actor) -> tuple[Actor, dict]:
    """执行长休
    
    长休完全恢复HP、法术位，恢复所有生命骰
    
    Returns:
        tuple: (更新后的Actor, 结果信息字典)
    """
    updates: dict = {
        "hp": actor.hp_max,
        "hit_dice_remaining": actor.hit_dice_total,
    }
    
    result_info: dict = {
        "success": True,
        "message": "长休完成，完全恢复HP和所有生命骰",
        "hp_gained": actor.hp_max - actor.hp,
        "hit_dice_restored": actor.hit_dice_total - actor.hit_dice_remaining,
    }
    
    # 恢复法术位
    if actor.spell_slots_max:
        updates["spell_slots"] = dict(actor.spell_slots_max)
        result_info["spell_slots_restored"] = True
        result_info["message"] += "，法术位已完全恢复"
    
    updated_actor = actor.model_copy(update=updates)
    
    return updated_actor, result_info


def initialize_actor_rest_resources(actor: Actor) -> Actor:
    """初始化角色的休息相关资源（创建角色时调用）
    
    根据等级设置生命骰总数和法术位
    """
    level = max(1, actor.level)
    
    updates: dict = {
        "hit_dice_total": level,
        "hit_dice_remaining": level,
    }
    
    # 法师初始化法术位
    if actor.character_class and actor.character_class.value == "mage":
        max_slots = MAGE_SPELL_SLOTS.get(min(level, 3), {"1": 2})
        updates["spell_slots_max"] = dict(max_slots)
        updates["spell_slots"] = dict(max_slots)
    
    return actor.model_copy(update=updates)


def can_rest_in_current_phase(game_phase: str) -> tuple[bool, str]:
    """检查当前游戏阶段是否允许休息
    
    Returns:
        tuple: (是否允许, 错误信息)
    """
    if game_phase == "combat":
        return False, "战斗中无法休息"
    if game_phase != "exploration":
        return False, f"当前阶段 ({game_phase}) 无法休息"
    return True, ""

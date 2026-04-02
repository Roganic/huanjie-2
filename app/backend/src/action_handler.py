"""Action handler for equipment and special actions.

This module handles special player actions that modify game state directly,
such as equipping items from inventory.
"""

from __future__ import annotations

import re
from typing import Optional

from dataclasses import dataclass

from .models.action import ActionRequest, ActionResponse, Outcome, ResolutionType


@dataclass
class MovementResult:
    success: bool
    message: str
    new_scene_id: str | None = None


def is_movement_action(intent: str, approach: str) -> bool:
    """Check if the action is a movement action."""
    text = f"{intent} {approach}".lower()
    movement_keywords = [
        "go", "move", "walk", "run", "head", "travel", "leave",
        "去", "走", "前往", "离开", "移动", "进入",
    ]
    return any(kw in text for kw in movement_keywords)


def handle_movement(intent: str, approach: str, session_id: str | None = None) -> MovementResult:
    """Handle a movement action."""
    # Minimal stub: movement is not implemented in scene system yet
    return MovementResult(
        success=False,
        message="移动功能正在开发中。",
    )


def get_available_exits(session_id: str | None = None) -> list[dict]:
    """Get available exits for the current scene."""
    from .state import get_scene
    scene = get_scene(session_id)
    return [
        {"direction": exit_info.direction, "target_scene_id": exit_info.target_scene_id}
        for exit_info in scene.exits
    ] if scene else []


def is_equipment_action(intent: str, approach: str) -> bool:
    """Check if the action is an equipment-related action.
    
    Args:
        intent: The action intent
        approach: The action approach
        
    Returns:
        True if this is an equipment action
    """
    text = f"{intent} {approach}".lower()
    
    # Equipment keywords in Chinese and English
    equip_keywords = [
        "装备", "equip", "穿戴", "wear", "拿起", "hold", "使用武器", "use weapon",
        "卸下", "unequip", "remove", "脱下", "take off",
    ]
    
    for keyword in equip_keywords:
        if keyword in text:
            return True
    
    return False


def parse_equipment_action(intent: str, approach: str) -> tuple[str, str]:
    """Parse an equipment action to determine the operation and item name.
    
    Args:
        intent: The action intent
        approach: The action approach
        
    Returns:
        A tuple of (operation, item_name) where operation is "equip" or "unequip"
    """
    text = f"{intent} {approach}".lower()
    
    # Check for unequip keywords
    unequip_keywords = ["卸下", "unequip", "remove", "脱下", "take off"]
    is_unequip = any(kw in text for kw in unequip_keywords)
    
    operation = "unequip" if is_unequip else "equip"
    
    # Try to extract item name
    # Patterns:
    # - "装备长剑" -> extract "长剑"
    # - "equip longsword" -> extract "longsword"
    # - "装备 长剑" -> extract "长剑"
    
    item_name = None
    
    # Pattern 1: 装备 + item (Chinese)
    chinese_equip_match = re.search(r'装备\s*(\S+)', intent)
    if chinese_equip_match:
        item_name = chinese_equip_match.group(1).strip()
    
    # Pattern 2: equip + item (English)
    if item_name is None:
        english_equip_match = re.search(r'equip\s*(\S+)', intent, re.IGNORECASE)
        if english_equip_match:
            item_name = english_equip_match.group(1).strip()
    
    # Pattern 3: Check approach for item name if intent didn't have it
    if item_name is None:
        # Try "装备" + item in approach
        chinese_equip_match = re.search(r'装备\s*(\S+)', approach)
        if chinese_equip_match:
            item_name = chinese_equip_match.group(1).strip()
    
    if item_name is None:
        # Try "equip" + item in approach
        english_equip_match = re.search(r'equip\s*(\S+)', approach, re.IGNORECASE)
        if english_equip_match:
            item_name = english_equip_match.group(1).strip()
    
    # For unequip, also check for slot names
    if operation == "unequip" and item_name is None:
        # Check for slot names
        if any(kw in text for kw in ["武器", "weapon", "剑", "sword"]):
            item_name = "weapon"
        elif any(kw in text for kw in ["护甲", "armor", "甲", "衣服", "clothes"]):
            item_name = "armor"
    
    return operation, item_name


def _handle_spell_action(req: ActionRequest, actor) -> Optional[ActionResponse]:
    """Handle spell casting actions."""
    from .spells.spell_resolver import is_cast_command, parse_cast_command, cast_spell
    from .models.action import Effect
    from .state import get_actor_by_id_or_name, consume_actor_spell_slot
    
    if not is_cast_command(req.intent):
        return None
    
    spell_name, target_name = parse_cast_command(req.intent)
    if spell_name is None:
        return None
    
    target = None
    if target_name:
        target = get_actor_by_id_or_name(target_name)
    if target is None:
        from .spells.spell_registry import get_spell
        spell = get_spell(spell_name)
        if spell and spell.healing_dice:
            # Healing spells default to caster
            target = actor
        else:
            # Default target enemy if in combat context
            from .state import get_enemy
            target = get_enemy()
    
    result = cast_spell(actor, spell_name, target)
    
    if not result.success:
        return ActionResponse(
            action_summary=f"{actor.name} 尝试施放 {result.spell_name}",
            resolution_type=ResolutionType.AUTO_SUCCESS,
            outcome=Outcome.FAILURE,
            effects=[],
            narration=result.error_message or f"施放 {result.spell_name} 失败。",
            scene_progression="法术施放失败。",
            gm_prompt=result.error_message or "法术无法施放。",
        )
    
    # cast_spell already consumed the spell slot in-place on the actor object.
    # We just need to persist the session. apply_effects will do that.
    
    effects: list[Effect] = []
    
    # Track spell slot consumption
    if result.slot_level > 0:
        effects.append(Effect(
            target=actor.id,
            field="spell_slot_consumed",
            delta=result.slot_level,
            description=f"消耗 {result.slot_level} 环法术位",
        ))
    
    # Apply HP effect to target
    if result.damage is not None and target is not None:
        # Negative damage = healing
        if result.damage < 0:
            hp_delta = -result.damage
            effects.append(Effect(
                target=target.id,
                field="hp",
                delta=hp_delta,
                description=f"{target.name} 恢复 {hp_delta} 点生命值",
            ))
        else:
            effects.append(Effect(
                target=target.id,
                field="hp",
                delta=-result.damage,
                description=f"{target.name} 受到 {result.damage} 点 {result.damage_type.value if result.damage_type else ''}伤害",
            ))
    
    # Apply effects through state manager (this also persists the session)
    from .state import apply_effects
    apply_effects(effects)
    
    return ActionResponse(
        action_summary=f"{actor.name} 施放 {result.spell_name}",
        resolution_type=ResolutionType.AUTO_SUCCESS,
        outcome=Outcome.SUCCESS,
        effects=effects,
        narration=result.narrative,
        scene_progression=f"{result.spell_name} 施放成功。",
        gm_prompt=f"{actor.name} 已施放 {result.spell_name}。",
    )


def _handle_rest_action(req: ActionRequest, actor) -> Optional[ActionResponse]:
    """Handle short rest and long rest actions."""
    from .spells.spell_resolver import is_rest_command
    from .models.action import Effect
    from .state import restore_actor_spell_slots, apply_effects
    
    is_rest, rest_type = is_rest_command(req.intent)
    if not is_rest:
        return None
    
    rest_name = "长休" if rest_type == "long" else "短休"
    result = restore_actor_spell_slots(rest_type)
    
    effects: list[Effect] = []
    if result.get("restored"):
        effects.append(Effect(
            target=actor.id,
            field="spell_slots_restored",
            delta=rest_type,
            description=f"{rest_name}后法术位已恢复",
        ))
        apply_effects(effects)
    
    return ActionResponse(
        action_summary=f"{actor.name} 进行{rest_name}",
        resolution_type=ResolutionType.AUTO_SUCCESS,
        outcome=Outcome.SUCCESS,
        effects=effects,
        narration=f"{actor.name} 完成了一次{rest_name}，感觉精神焕发。",
        scene_progression=f"{rest_name}完成。" + ("法术位已恢复。" if result.get("restored") else ""),
        gm_prompt=f"{actor.name} 已完成{rest_name}。",
    )


def handle_equipment_action(
    req: ActionRequest,
    actor,
) -> Optional[ActionResponse]:
    """Handle equipment, spell, and rest actions.
    
    Args:
        req: The action request
        actor: The actor performing the action
        
    Returns:
        An ActionResponse if this was a special action, None otherwise
    """
    # Check for spell actions first
    spell_response = _handle_spell_action(req, actor)
    if spell_response is not None:
        return spell_response
    
    # Check for rest actions
    rest_response = _handle_rest_action(req, actor)
    if rest_response is not None:
        return rest_response
    
    from .state import equip_item_for_actor, unequip_item_from_actor
    
    if not is_equipment_action(req.intent, req.approach):
        return None
    
    operation, item_name = parse_equipment_action(req.intent, req.approach)
    
    if item_name is None:
        # Could not parse item name
        return ActionResponse(
            action_summary=f"{actor.name} attempts to {operation} an item",
            resolution_type=ResolutionType.AUTO_SUCCESS,
            outcome=Outcome.FAILURE,
            effects=[],
            narration=f"{actor.name} 想要{operation}一件物品，但没有指定是什么物品。",
            scene_progression="请指定要装备的物品名称。",
            gm_prompt="请提示玩家明确指定要装备的物品名称。",
        )
    
    if operation == "equip":
        # Try to equip the item
        result = equip_item_for_actor(item_name)
        
        if result["success"]:
            equipped_item = result["item"]
            previous_item = result.get("previous_item")
            new_ac = result["ac"]
            
            # Build narration
            narration = f"{actor.name} 装备上了 {equipped_item['name']}。"
            if previous_item:
                narration += f" (替换了 {previous_item['name']})"
            
            # Update actor's equipped info for the response
            from .equipment import format_equipment_for_response
            from .state import get_actor
            updated_actor = get_actor()
            equipped_data = format_equipment_for_response(updated_actor)
            
            return ActionResponse(
                action_summary=f"{actor.name} equips {equipped_item['name']}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=[],
                narration=narration,
                scene_progression=f"{actor.name} 的护甲等级现在是 {new_ac}。",
                gm_prompt=f"{actor.name} 已装备 {equipped_item['name']}。当前AC为{new_ac}。",
            )
        else:
            # Failed to equip
            error_msg = result.get("error", "无法装备该物品")
            return ActionResponse(
                action_summary=f"{actor.name} tries to equip {item_name}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.FAILURE,
                effects=[],
                narration=f"{actor.name} 尝试装备 {item_name}，但失败了：{error_msg}",
                scene_progression="装备失败。",
                gm_prompt=f"装备失败：{error_msg}",
            )
    
    else:  # operation == "unequip"
        # Determine slot from item name or use as slot directly
        slot = item_name if item_name in ("weapon", "armor") else None
        
        if slot is None:
            # Try to infer slot from item name
            if item_name in ["武器", "weapon", "剑", "sword", "刀", "axe", "斧"]:
                slot = "weapon"
            elif item_name in ["护甲", "armor", "甲", "衣服", "clothes", "铠甲"]:
                slot = "armor"
        
        if slot is None:
            return ActionResponse(
                action_summary=f"{actor.name} tries to unequip {item_name}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.FAILURE,
                effects=[],
                narration=f"{actor.name} 想要卸下 {item_name}，但请指定是武器(weapon)还是护甲(armor)。",
                scene_progression="请指定要卸下的装备类型。",
                gm_prompt="请提示玩家明确指定要卸下武器还是护甲。",
            )
        
        result = unequip_item_from_actor(slot)
        
        if result["success"]:
            removed_item = result.get("removed_item")
            new_ac = result["ac"]
            
            if removed_item:
                narration = f"{actor.name} 卸下了 {removed_item['name']}。"
            else:
                narration = f"{actor.name} 没有装备该位置的物品。"
            
            return ActionResponse(
                action_summary=f"{actor.name} unequips {slot}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.SUCCESS,
                effects=[],
                narration=narration,
                scene_progression=f"{actor.name} 的护甲等级现在是 {new_ac}。" if slot == "armor" else "装备已更新。",
                gm_prompt=f"{actor.name} 已卸下装备。当前AC为{new_ac}。" if slot == "armor" else f"{actor.name} 已卸下武器。",
            )
        else:
            error_msg = result.get("error", "无法卸下该物品")
            return ActionResponse(
                action_summary=f"{actor.name} tries to unequip {slot}",
                resolution_type=ResolutionType.AUTO_SUCCESS,
                outcome=Outcome.FAILURE,
                effects=[],
                narration=f"{actor.name} 尝试卸下装备，但失败了：{error_msg}",
                scene_progression="卸下装备失败。",
                gm_prompt=f"卸下装备失败：{error_msg}",
            )


def get_equipped_weapon_info(actor) -> Optional[dict]:
    """Get information about the actor's equipped weapon.
    
    Args:
        actor: The actor to check
        
    Returns:
        A dictionary with weapon info, or None if no weapon is equipped
    """
    from .equipment import get_equipped_weapon, get_weapon_damage_dice, get_weapon_attack_ability
    
    weapon = get_equipped_weapon(actor)
    if weapon is None:
        return None
    
    return {
        "name": weapon.name,
        "damage_dice": get_weapon_damage_dice(weapon),
        "attack_ability": get_weapon_attack_ability(weapon),
    }


def get_equipped_armor_info(actor) -> Optional[dict]:
    """Get information about the actor's equipped armor.
    
    Args:
        actor: The actor to check
        
    Returns:
        A dictionary with armor info, or None if no armor is equipped
    """
    from .equipment import get_equipped_armor
    
    armor = get_equipped_armor(actor)
    if armor is None:
        return None
    
    return {
        "name": armor.name,
        "base_ac": armor.base_ac,
        "ac": actor.ac,
    }


# ---------------------------------------------------------------------------
# Scene movement stubs (required for import compatibility)
# ---------------------------------------------------------------------------

MOVEMENT_VERBS: set[str] = set()
COMBAT_KEYWORDS: set[str] = set()


def is_movement_action(intent: str, approach: str) -> bool:
    """Check if the action is a movement action."""
    return False


def can_move_in_current_state() -> bool:
    """Check if movement is allowed in the current game state."""
    return True


class MovementResult:
    """Result of a movement attempt."""
    def __init__(self, success: bool = False, message: str = "", target_scene_id: str | None = None):
        self.success = success
        self.message = message
        self.target_scene_id = target_scene_id


def handle_movement(intent: str, approach: str, session_id: str | None = None) -> MovementResult:
    """Handle a movement action."""
    return MovementResult(success=False, message="Movement not implemented.")


def get_available_exits(session_id: str | None = None) -> list[dict]:
    """Get available exits for the current scene."""
    return []


def get_current_scene_info(session_id: str | None = None) -> dict:
    """Get information about the current scene."""
    from .state import get_scene
    scene = get_scene(session_id)
    return {
        "id": scene.id,
        "name": scene.name,
        "description": scene.description,
    }

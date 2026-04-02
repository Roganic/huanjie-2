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


def handle_equipment_action(
    req: ActionRequest,
    actor,
) -> Optional[ActionResponse]:
    """Handle an equipment action.
    
    Args:
        req: The action request
        actor: The actor performing the action
        
    Returns:
        An ActionResponse if this was an equipment action, None otherwise
    """
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

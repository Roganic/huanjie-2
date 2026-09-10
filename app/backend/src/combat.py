"""Combat utilities for equipment-based combat calculations.

This module provides helper functions for combat that take into account
the actor's equipped weapons and armor.
"""

from __future__ import annotations

from typing import Optional

from .models.state import Actor, InventoryItem


def get_weapon_for_combat(actor: Actor, weapon_override: Optional[str] = None) -> Optional[InventoryItem]:
    """Get the weapon to use for combat.
    
    Priority:
    1. If weapon_override is provided and matches an inventory item, use that
    2. Otherwise, use the actor's equipped weapon
    3. If no weapon is equipped, return None
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override from the action request
        
    Returns:
        The InventoryItem to use for the attack, or None for unarmed
    """
    # First check if there's a weapon override
    if weapon_override:
        # Try to find the weapon in inventory
        weapon_override_lower = weapon_override.lower().strip()
        for item in actor.inventory:
            if item.type.value == "weapon" and item.name.lower() == weapon_override_lower:
                return item
    
    # Fall back to equipped weapon
    return actor.equipped.weapon


def get_damage_dice_for_combat(actor: Actor, weapon_override: Optional[str] = None) -> str:
    """Get the damage dice to use for a combat attack.
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        The damage dice expression (e.g., "1d8", "1d6")
    """
    weapon = get_weapon_for_combat(actor, weapon_override)
    
    if weapon is None:
        # Unarmed strike: minimal damage
        return "1"
    
    return weapon.damage_dice or "1"


def get_attack_ability_for_combat(actor: Actor, weapon_override: Optional[str] = None) -> str:
    """Get the ability to use for attack rolls.
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        The ability abbreviation ("str" or "dex")
    """
    weapon = get_weapon_for_combat(actor, weapon_override)
    
    if weapon is None:
        # Unarmed uses STR by default
        return "str"
    
    # Use weapon's configured attack ability, or default to STR
    return weapon.attack_ability or "str"


def calculate_attack_modifier(actor: Actor, weapon_override: Optional[str] = None) -> int:
    """Calculate the total attack modifier for a combat attack.
    
    Attack modifier = ability modifier + proficiency bonus
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        The total attack modifier
    """
    ability = get_attack_ability_for_combat(actor, weapon_override)
    ability_modifier = actor.abilities.modifier(ability)
    
    # All weapon attacks add proficiency bonus in 5e
    return ability_modifier + actor.proficiency_bonus


def calculate_damage_modifier(actor: Actor, weapon_override: Optional[str] = None) -> int:
    """Calculate the damage modifier for a combat attack.
    
    Damage modifier = ability modifier (same as attack ability)
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        The damage modifier
    """
    ability = get_attack_ability_for_combat(actor, weapon_override)
    return actor.abilities.modifier(ability)


def format_weapon_name_for_combat(actor: Actor, weapon_override: Optional[str] = None) -> str:
    """Get the display name of the weapon being used.
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        The weapon name for display purposes
    """
    weapon = get_weapon_for_combat(actor, weapon_override)
    
    if weapon is None:
        return "徒手攻击"
    
    return weapon.name


def get_default_weapon_name(actor: Actor) -> str:
    """Get the default weapon name for an actor based on class.
    
    This is a fallback for when no weapon is specified.
    
    Args:
        actor: The actor
        
    Returns:
        A default weapon name
    """
    class_value = (actor.character_class.value if actor.character_class else "warrior")
    return {
        "warrior": "长剑",
        "rogue": "短剑",
        "mage": "匕首",
    }.get(class_value, "长剑")


def get_weapon_info_for_response(actor: Actor, weapon_override: Optional[str] = None) -> dict:
    """Get complete weapon information for an attack response.
    
    Args:
        actor: The actor performing the attack
        weapon_override: Optional weapon name override
        
    Returns:
        A dictionary with weapon information for the response
    """
    weapon = get_weapon_for_combat(actor, weapon_override)
    
    if weapon is None:
        return {
            "name": "徒手攻击",
            "damage_dice": "1",
            "attack_ability": "str",
            "is_equipped": False,
        }
    
    return {
        "name": weapon.name,
        "damage_dice": weapon.damage_dice or "1",
        "attack_ability": weapon.attack_ability or "str",
        "is_equipped": (actor.equipped.weapon is not None and 
                       actor.equipped.weapon.id == weapon.id),
    }


def resolve_attack_with_equipment(
    actor: Actor,
    target_ac: int,
    weapon_override: Optional[str] = None,
    advantage: Optional[bool] = None,
) -> dict:
    """Resolve an attack using the actor's equipped weapon.
    
    This is a high-level function that handles the complete attack resolution
    including dice rolls and damage calculation.
    
    Args:
        actor: The attacking actor
        target_ac: The target's armor class
        weapon_override: Optional weapon name override
        advantage: Whether the attack has advantage
        
    Returns:
        A dictionary with attack results:
        - hit: True if the attack hit
        - attack_roll: The raw d20 roll
        - total_attack: The total attack roll (d20 + modifiers)
        - damage: The damage dealt (if hit)
        - damage_rolls: The individual damage dice rolls
        - weapon_used: The name of the weapon used
    """
    import random
    
    # Get attack parameters
    weapon_name = format_weapon_name_for_combat(actor, weapon_override)
    attack_ability = get_attack_ability_for_combat(actor, weapon_override)
    attack_modifier = calculate_attack_modifier(actor, weapon_override)
    damage_dice = get_damage_dice_for_combat(actor, weapon_override)
    damage_modifier = calculate_damage_modifier(actor, weapon_override)
    
    # Roll d20 for attack (with advantage/disadvantage if applicable)
    if advantage is True:
        roll = max(random.randint(1, 20), random.randint(1, 20))
    elif advantage is False:
        roll = min(random.randint(1, 20), random.randint(1, 20))
    else:
        roll = random.randint(1, 20)
    
    # Natural 1 is always a miss, natural 20 is always a hit
    if roll == 1:
        hit = False
    elif roll == 20:
        hit = True
    else:
        total_attack = roll + attack_modifier
        hit = total_attack >= target_ac
    
    result = {
        "hit": hit,
        "attack_roll": roll,
        "total_attack": roll + attack_modifier,
        "attack_modifier": attack_modifier,
        "target_ac": target_ac,
        "weapon_used": weapon_name,
        "damage": 0,
        "damage_rolls": [],
        "damage_modifier": 0,
    }
    
    # Calculate damage if hit
    if hit and roll != 1:
        # Roll damage dice
        damage_rolls = []
        damage_total = 0
        
        if "d" in damage_dice:
            from .engine.dice import roll_damage
            damage_total, damage_rolls = roll_damage(damage_dice)
        else:
            damage_total = int(damage_dice)

        # Add damage modifier (min 1 damage on hit)
        final_damage = max(1, damage_total + damage_modifier)
        
        result["damage"] = final_damage
        result["damage_rolls"] = damage_rolls
        result["damage_modifier"] = damage_modifier
        result["damage_dice"] = damage_dice
    
    return result

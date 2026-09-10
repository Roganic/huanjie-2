"""Equipment system for managing weapons and armor.

This module provides the core logic for:
- Equipping/unequipping items from inventory
- Calculating AC based on equipped armor
- Getting weapon damage dice and attack abilities
- Validating equipment actions
"""

from __future__ import annotations

from typing import Optional

from .models.state import (
    Actor,
    Armor,
    InventoryItem,
    ItemType,
    Weapon,
)


class EquipmentError(Exception):
    """Error raised for equipment-related failures."""
    pass


class ItemNotFoundError(EquipmentError):
    """Error raised when trying to equip an item not in inventory."""
    pass


class InvalidItemTypeError(EquipmentError):
    """Error raised when trying to equip an item of invalid type."""
    pass


def find_item_in_inventory(actor: Actor, item_name: str) -> Optional[InventoryItem]:
    """Find an item in the actor's inventory by name (case-insensitive).
    
    Args:
        actor: The actor whose inventory to search
        item_name: The name of the item to find
        
    Returns:
        The InventoryItem if found, None otherwise
    """
    item_name_lower = item_name.lower().strip()
    exact = next((item for item in actor.inventory if item.id == item_name), None)
    if exact is not None:
        return exact
    for item in actor.inventory:
        if item.name.lower() == item_name_lower:
            return item
    return None


def get_equipped_weapon(actor: Actor) -> Optional[InventoryItem]:
    """Get the currently equipped weapon.
    
    Args:
        actor: The actor to check
        
    Returns:
        The equipped weapon InventoryItem, or None if no weapon is equipped
    """
    return actor.equipped.weapon


def get_equipped_armor(actor: Actor) -> Optional[InventoryItem]:
    """Get the currently equipped armor.
    
    Args:
        actor: The actor to check
        
    Returns:
        The equipped armor InventoryItem, or None if no armor is equipped
    """
    return actor.equipped.armor


def calculate_ac(abilities, equipped_armor: Optional[InventoryItem] = None) -> int:
    """Calculate AC based on equipped armor and abilities.
    
    5e AC calculation rules:
    - Unarmored: 10 + DEX modifier
    - Light armor: base AC + DEX modifier (full)
    - Medium armor: base AC + DEX modifier (max +2)
    - Heavy armor: base AC only (no DEX modifier)
    
    Args:
        abilities: The actor's AbilityScores
        equipped_armor: The equipped armor item, or None for unarmored
        
    Returns:
        The calculated AC value
    """
    if equipped_armor is None:
        # Unarmored: 10 + DEX modifier
        return 10 + abilities.modifier("dex")
    
    base_ac = equipped_armor.base_ac or 10
    
    if not equipped_armor.add_dex_modifier:
        # Heavy armor: use base AC only
        return base_ac
    
    # Light/medium armor: add DEX modifier (with optional cap for medium)
    dex_mod = abilities.modifier("dex")
    if equipped_armor.max_dex_bonus is not None:
        dex_mod = min(dex_mod, equipped_armor.max_dex_bonus)
    
    return base_ac + dex_mod


def get_weapon_damage_dice(weapon_item: Optional[InventoryItem] = None) -> str:
    """Get the damage dice for a weapon.
    
    Args:
        weapon_item: The equipped weapon item, or None
        
    Returns:
        The damage dice expression (e.g., "1d8", "1d6")
    """
    if weapon_item is None or weapon_item.damage_dice is None:
        # Unarmed strike: 1 damage (or 1d4 for monks, but default to simple)
        return "1"
    return weapon_item.damage_dice


def get_weapon_attack_ability(weapon_item: Optional[InventoryItem] = None) -> str:
    """Get the ability used for attack rolls with a weapon.
    
    Args:
        weapon_item: The equipped weapon item, or None
        
    Returns:
        The ability abbreviation ("str" or "dex")
    """
    if weapon_item is None:
        return "str"
    
    # Check if weapon has an explicit attack ability
    if weapon_item.attack_ability:
        return weapon_item.attack_ability
    
    # Default to STR for most weapons
    return "str"


def equip_item(actor: Actor, item_name: str) -> tuple[Actor, InventoryItem, Optional[InventoryItem]]:
    """Equip an item from the actor's inventory.
    
    Args:
        actor: The actor equipping the item
        item_name: The name of the item to equip
        
    Returns:
        A tuple of (updated_actor, equipped_item, previous_item)
        - updated_actor: The actor with updated equipped items and AC
        - equipped_item: The newly equipped item
        - previous_item: The previously equipped item of the same slot (if any)
        
    Raises:
        ItemNotFoundError: If the item is not in the actor's inventory
        InvalidItemTypeError: If the item is not a weapon or armor
    """
    # Find the item in inventory
    item = find_item_in_inventory(actor, item_name)
    if item is None:
        raise ItemNotFoundError(f"背包中没有 '{item_name}'")
    
    # Validate item type
    if item.type not in (ItemType.WEAPON, ItemType.ARMOR):
        raise InvalidItemTypeError(f"无法装备 '{item_name}'：不是武器或护甲")
    
    # Get current equipped items
    previous_weapon = actor.equipped.weapon
    previous_armor = actor.equipped.armor
    
    # Prepare updates
    from .models.state import EquippedItems
    
    if item.type == ItemType.WEAPON:
        new_equipped = EquippedItems(
            weapon=item,
            armor=previous_armor,
        )
        previous_item = previous_weapon
    else:  # ItemType.ARMOR
        new_equipped = EquippedItems(
            weapon=previous_weapon,
            armor=item,
        )
        previous_item = previous_armor
    
    # Calculate new AC if armor changed
    new_ac = actor.ac
    if item.type == ItemType.ARMOR:
        new_ac = calculate_ac(actor.abilities, item)
    
    # Create updated actor
    updated_actor = actor.model_copy(
        update={
            "equipped": new_equipped,
            "ac": new_ac,
        }
    )
    
    return updated_actor, item, previous_item


def unequip_item(actor: Actor, slot: str) -> tuple[Actor, Optional[InventoryItem]]:
    """Unequip an item from a specific slot.
    
    Args:
        actor: The actor unequipping the item
        slot: The slot to unequip ("weapon" or "armor")
        
    Returns:
        A tuple of (updated_actor, removed_item)
        - updated_actor: The actor with the item removed
        - removed_item: The item that was unequipped, or None if nothing was equipped
        
    Raises:
        ValueError: If slot is not "weapon" or "armor"
    """
    if slot not in ("weapon", "armor"):
        raise ValueError(f"Invalid slot '{slot}': must be 'weapon' or 'armor'")
    
    from .models.state import EquippedItems
    
    if slot == "weapon":
        removed_item = actor.equipped.weapon
        new_equipped = EquippedItems(
            weapon=None,
            armor=actor.equipped.armor,
        )
    else:  # slot == "armor"
        removed_item = actor.equipped.armor
        new_equipped = EquippedItems(
            weapon=actor.equipped.weapon,
            armor=None,
        )
    
    # Recalculate AC if armor was unequipped
    new_ac = actor.ac
    if slot == "armor":
        new_ac = calculate_ac(actor.abilities, None)
    
    updated_actor = actor.model_copy(
        update={
            "equipped": new_equipped,
            "ac": new_ac,
        }
    )
    
    return updated_actor, removed_item


def get_equipment_summary(actor: Actor) -> dict:
    """Get a summary of the actor's current equipment.
    
    Args:
        actor: The actor to summarize
        
    Returns:
        A dictionary with equipment information
    """
    weapon = actor.equipped.weapon
    armor = actor.equipped.armor
    
    return {
        "weapon": {
            "name": weapon.name if weapon else None,
            "damage_dice": weapon.damage_dice if weapon else None,
            "attack_ability": weapon.attack_ability if weapon else "str",
        } if weapon else None,
        "armor": {
            "name": armor.name if armor else None,
            "base_ac": armor.base_ac if armor else None,
            "ac": actor.ac,
        } if armor else None,
        "ac": actor.ac,
    }


def format_equipment_for_response(actor: Actor) -> dict:
    """Format equipped items for API response.
    
    Args:
        actor: The actor whose equipment to format
        
    Returns:
        A dictionary with weapon and armor info for the response
    """
    weapon = actor.equipped.weapon
    armor = actor.equipped.armor
    
    result = {
        "weapon": None,
        "armor": None,
    }
    
    if weapon:
        result["weapon"] = {
            "id": weapon.id,
            "name": weapon.name,
            "type": weapon.type.value,
            "damage_dice": weapon.damage_dice,
            "attack_ability": weapon.attack_ability,
            "description": weapon.description,
        }
    
    if armor:
        result["armor"] = {
            "id": armor.id,
            "name": armor.name,
            "type": armor.type.value,
            "base_ac": armor.base_ac,
            "add_dex_modifier": armor.add_dex_modifier,
            "max_dex_bonus": armor.max_dex_bonus,
            "description": armor.description,
        }
    
    return result

"""Loot generation logic for combat encounters.

Handles probability-based loot drops from defeated enemies.
"""

from __future__ import annotations

import random
from typing import Callable

from .models import GeneratedLoot, LootGained, LootItem
from .tables import get_loot_table


# Type alias for random number generator
RandomGenerator = Callable[[], float]


def _default_random() -> float:
    """Default random number generator (0.0 to 1.0)."""
    return random.random()


def roll_loot_item(item: LootItem, random_gen: RandomGenerator | None = None) -> bool:
    """Roll to determine if an item should drop.
    
    Args:
        item: The loot item with probability
        random_gen: Optional custom random generator (0.0 to 1.0)
        
    Returns:
        True if the item should drop, False otherwise
        
    Examples:
        >>> item = LootItem(item_id="sword", name="Sword", probability=1.0)
        >>> roll_loot_item(item)  # Always True
        
        >>> item = LootItem(item_id="rare_gem", name="Rare Gem", probability=0.0)
        >>> roll_loot_item(item)  # Always False
    """
    roll = (random_gen or _default_random)()
    return roll < item.probability


def generate_loot_for_enemy(
    enemy_id: str,
    enemy_name: str,
    random_gen: RandomGenerator | None = None,
) -> LootGained:
    """Generate loot drops for a defeated enemy.
    
    Args:
        enemy_id: The enemy's unique ID
        enemy_name: The enemy's display name
        random_gen: Optional custom random generator
        
    Returns:
        LootGained containing all dropped items
    """
    loot_table = get_loot_table(enemy_id, enemy_name)
    dropped_items: list[LootItem] = []
    
    for item in loot_table.drops:
        if roll_loot_item(item, random_gen):
            # Create a copy of the item for this drop
            dropped_items.append(LootItem(
                item_id=item.item_id,
                name=item.name,
                quantity=item.quantity,
                probability=item.probability,
                description=item.description,
            ))
    
    return LootGained(
        enemy_id=enemy_id,
        enemy_name=enemy_name,
        items=dropped_items,
    )


def generate_combat_loot(
    defeated_enemies: list[tuple[str, str]],
    random_gen: RandomGenerator | None = None,
) -> GeneratedLoot:
    """Generate loot for all defeated enemies in a combat encounter.
    
    Args:
        defeated_enemies: List of (enemy_id, enemy_name) tuples
        random_gen: Optional custom random generator
        
    Returns:
        GeneratedLoot containing all loot entries
    """
    loot_entries: list[LootGained] = []
    
    for enemy_id, enemy_name in defeated_enemies:
        loot = generate_loot_for_enemy(enemy_id, enemy_name, random_gen)
        if loot.items:  # Only add if there are drops
            loot_entries.append(loot)
    
    return GeneratedLoot(loot_entries=loot_entries)


def format_loot_for_narrative(loot: GeneratedLoot) -> str:
    """Format loot for inclusion in AI narrative prompt.
    
    Args:
        loot: The generated loot
        
    Returns:
        A narrative-friendly string describing the loot
    """
    if loot.is_empty():
        return "没有发现战利品。"
    
    parts = []
    for entry in loot.loot_entries:
        if not entry.items:
            continue
        item_descriptions = []
        for item in entry.items:
            if item.quantity > 1:
                item_descriptions.append(f"{item.name} x{item.quantity}")
            else:
                item_descriptions.append(item.name)
        parts.append(f"从{entry.enemy_name}身上搜到了：{', '.join(item_descriptions)}")
    
    return "；".join(parts)


def get_loot_item_names(loot: GeneratedLoot) -> list[str]:
    """Get a flat list of all loot item names.
    
    Args:
        loot: The generated loot
        
    Returns:
        List of item names
    """
    names = []
    for entry in loot.loot_entries:
        for item in entry.items:
            names.append(item.name)
    return names

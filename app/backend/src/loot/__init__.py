"""Loot system for enemy drops.

Provides loot table definitions, probability-based drop generation,
and integration with combat system.
"""

from .generator import (
    generate_combat_loot,
    generate_loot_for_enemy,
    get_loot_item_names,
    format_loot_for_narrative,
    roll_loot_item,
)
from .models import GeneratedLoot, LootGained, LootItem, LootTable
from .tables import (
    LOOT_TABLES,
    bandit_loot,
    default_loot,
    get_loot_table,
    goblin_loot,
    skeleton_loot,
)

__all__ = [
    # Models
    "LootItem",
    "LootTable",
    "LootGained",
    "GeneratedLoot",
    # Tables
    "LOOT_TABLES",
    "goblin_loot",
    "skeleton_loot",
    "bandit_loot",
    "default_loot",
    "get_loot_table",
    # Generator
    "generate_loot_for_enemy",
    "generate_combat_loot",
    "format_loot_for_narrative",
    "get_loot_item_names",
    "roll_loot_item",
]

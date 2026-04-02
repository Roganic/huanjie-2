"""Loot table definitions for enemy types.

Defines drop tables for:
- 哥布林 (Goblin): 短剑、金币
- 骷髅 (Skeleton): 骨头、生锈剑
- 强盗 (Bandit): 匕首、皮革
"""

from .models import LootItem, LootTable


# Goblin loot table - drops shortsword and gold
goblin_loot = LootTable(
    enemy_type="goblin",
    enemy_name="哥布林",
    drops=[
        LootItem(
            item_id="shortsword",
            name="短剑",
            quantity=1,
            probability=0.3,  # 30% chance
            description="一把轻便的短剑，适合快速攻击。",
        ),
        LootItem(
            item_id="gold_coins",
            name="金币",
            quantity=5,
            probability=0.5,  # 50% chance
            description="几枚闪闪发光的金币。",
        ),
        LootItem(
            item_id="dagger",
            name="匕首",
            quantity=1,
            probability=0.2,  # 20% chance
            description="一把锈迹斑斑的匕首。",
        ),
    ]
)


# Skeleton loot table - drops bones and rusty sword
skeleton_loot = LootTable(
    enemy_type="skeleton",
    enemy_name="骷髅",
    drops=[
        LootItem(
            item_id="bones",
            name="骨头",
            quantity=2,
            probability=0.8,  # 80% chance - very common
            description="几根散落的骨头，可能有些用途。",
        ),
        LootItem(
            item_id="rusty_sword",
            name="生锈剑",
            quantity=1,
            probability=0.4,  # 40% chance
            description="一把锈迹斑斑的旧剑，但仍可使用。",
        ),
        LootItem(
            item_id="gold_coins",
            name="金币",
            quantity=3,
            probability=0.3,  # 30% chance
            description="几枚古老的金币。",
        ),
    ]
)


# Bandit loot table - drops dagger and leather
bandit_loot = LootTable(
    enemy_type="bandit",
    enemy_name="强盗",
    drops=[
        LootItem(
            item_id="dagger",
            name="匕首",
            quantity=1,
            probability=0.5,  # 50% chance
            description="一把锋利的匕首。",
        ),
        LootItem(
            item_id="leather_scrap",
            name="皮革碎片",
            quantity=2,
            probability=0.6,  # 60% chance
            description="一些皮革碎片，可以用来修补装备。",
        ),
        LootItem(
            item_id="gold_coins",
            name="金币",
            quantity=10,
            probability=0.4,  # 40% chance
            description="一袋沉甸甸的金币。",
        ),
    ]
)


# Default loot table for unknown enemy types
default_loot = LootTable(
    enemy_type="default",
    enemy_name="未知敌人",
    drops=[
        LootItem(
            item_id="gold_coins",
            name="金币",
            quantity=2,
            probability=0.3,
            description="几枚金币。",
        ),
    ]
)


# Registry of all loot tables
LOOT_TABLES: dict[str, LootTable] = {
    "goblin": goblin_loot,
    "goblin_scout": goblin_loot,
    "goblin_warrior": goblin_loot,
    "哥布林": goblin_loot,
    "哥布林斥候": goblin_loot,
    "skeleton": skeleton_loot,
    "骷髅": skeleton_loot,
    "bandit": bandit_loot,
    "强盗": bandit_loot,
    "default": default_loot,
}


def get_loot_table(enemy_id: str, enemy_name: str) -> LootTable:
    """Get the loot table for an enemy.
    
    Args:
        enemy_id: The enemy's unique ID
        enemy_name: The enemy's display name
        
    Returns:
        The matching LootTable or default if no match found
    """
    # Try to match by enemy_id (case-insensitive, partial match)
    enemy_id_lower = enemy_id.lower()
    for key, table in LOOT_TABLES.items():
        if key.lower() in enemy_id_lower:
            return table
    
    # Try to match by enemy_name (case-insensitive, partial match)
    enemy_name_lower = enemy_name.lower()
    for key, table in LOOT_TABLES.items():
        if key.lower() in enemy_name_lower:
            return table
    
    # Check for specific keywords
    if "goblin" in enemy_name_lower or "哥布林" in enemy_name:
        return goblin_loot
    elif "skeleton" in enemy_name_lower or "骷髅" in enemy_name:
        return skeleton_loot
    elif "bandit" in enemy_name_lower or "强盗" in enemy_name:
        return bandit_loot
    
    return default_loot

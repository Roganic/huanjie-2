"""Dice rolling utilities."""

from __future__ import annotations

import random
import re
from typing import Optional


def roll_d20(advantage: Optional[bool] = None) -> int:
    """Roll 1d20, applying advantage/disadvantage if specified.

    advantage=True  -> roll twice, take higher
    advantage=False -> roll twice, take lower
    advantage=None  -> single roll
    """
    if advantage is None:
        return random.randint(1, 20)
    a, b = random.randint(1, 20), random.randint(1, 20)
    return max(a, b) if advantage else min(a, b)


def roll_damage(dice_expr: str) -> tuple[int, list[int]]:
    """Roll damage dice and return total and individual rolls.

    Supports standard dice notation like "1d6", "2d8", "1d6+2", "2d10-1".
    Returns (total, list_of_rolls).
    """
    # Parse dice expression: e.g., "2d6+3", "1d8-1", "3d4"
    match = re.match(r"(\d+)d(\d+)([+-]\d+)?", dice_expr.strip())
    if not match:
        raise ValueError(f"Invalid dice expression: {dice_expr}")

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    return max(0, total), rolls  # Damage cannot be negative


# Predefined weapon damage dice for common weapon types
WEAPON_DAMAGE = {
    "dagger": "1d4",
    "shortsword": "1d6",
    "longsword": "1d8",
    "greatsword": "2d6",
    "battleaxe": "1d8",
    "greataxe": "1d12",
    "club": "1d4",
    "mace": "1d6",
    "spear": "1d6",
    "halberd": "1d10",
    "rapier": "1d8",
    "scimitar": "1d6",
    "quarterstaff": "1d6",
    "handaxe": "1d6",
    "light_crossbow": "1d8",
    "shortbow": "1d6",
    "longbow": "1d8",
    "heavy_crossbow": "1d10",
}


def get_weapon_damage(weapon: str) -> str:
    """Get damage dice expression for a weapon type."""
    return WEAPON_DAMAGE.get(weapon.lower(), "1d6")  # Default to 1d6

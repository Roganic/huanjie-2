"""Experience points and leveling system for D&D 5e.

This module handles:
- XP rewards for defeating enemies
- Level progression thresholds
- Level-up calculations (HP max, proficiency bonus)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.state import Actor, CharacterClass


# D&D 5e XP thresholds for leveling
# Level 1 -> 2 requires 300 XP total
# Level 2 -> 3 requires 900 XP total
# etc.
XP_THRESHOLDS: dict[int, int] = {
    1: 0,       # Starting level
    2: 300,     # 300 XP to reach level 2
    3: 900,     # 900 XP to reach level 3
    4: 2700,
    5: 6500,
}

# XP rewards for defeating enemies by type/name
ENEMY_XP_REWARDS: dict[str, int] = {
    "goblin": 50,
    "哥布林": 50,
    "哥布林斥候": 50,
    "bandit": 100,
    "强盗": 100,
    "skeleton": 50,
    "骷髅": 50,
}

# Default XP for unknown enemies
DEFAULT_ENEMY_XP: int = 50


@dataclass
class LevelUpResult:
    """Result of a level-up operation."""
    
    leveled_up: bool
    old_level: int
    new_level: int
    hp_increase: int
    new_proficiency_bonus: int
    new_hp_max: int


def get_enemy_xp_reward(enemy_name: str) -> int:
    """Get XP reward for defeating an enemy.
    
    Args:
        enemy_name: Name of the defeated enemy
        
    Returns:
        XP amount to award
    """
    # Try exact match first
    if enemy_name in ENEMY_XP_REWARDS:
        return ENEMY_XP_REWARDS[enemy_name]
    
    # Try case-insensitive partial match
    enemy_lower = enemy_name.lower()
    for key, xp in ENEMY_XP_REWARDS.items():
        if key.lower() in enemy_lower or enemy_lower in key.lower():
            return xp
    
    return DEFAULT_ENEMY_XP


def get_level_from_xp(xp: int) -> int:
    """Calculate character level from total XP.
    
    Args:
        xp: Total experience points
        
    Returns:
        Current level (1-20)
    """
    level = 1
    for lvl, threshold in sorted(XP_THRESHOLDS.items()):
        if xp >= threshold:
            level = lvl
        else:
            break
    return level


def get_next_level_xp(level: int) -> int | None:
    """Get XP required to reach the next level.
    
    Args:
        level: Current level
        
    Returns:
        XP needed for next level, or None if at max level
    """
    next_level = level + 1
    if next_level in XP_THRESHOLDS:
        return XP_THRESHOLDS[next_level]
    return None


def calculate_level_up(
    current_level: int,
    current_xp: int,
    xp_gained: int,
    con_modifier: int,
    character_class: CharacterClass,
) -> tuple[int, LevelUpResult | None]:
    """Calculate new level and level-up details after gaining XP.
    
    Args:
        current_level: Current character level
        current_xp: Current experience points
        xp_gained: XP to add
        con_modifier: Constitution modifier for HP calculation
        character_class: Character class for hit die
        
    Returns:
        Tuple of (new_total_xp, LevelUpResult or None)
    """
    from src.rules.calculations import CLASS_HIT_DICE, proficiency_bonus
    
    new_xp = current_xp + xp_gained
    new_level = get_level_from_xp(new_xp)
    
    if new_level > current_level:
        # Calculate HP increase for each level gained
        hit_die = CLASS_HIT_DICE[character_class]
        # Average hit die roll rounded up: (die_size / 2) + 1
        hp_per_level = (hit_die // 2) + 1 + con_modifier
        levels_gained = new_level - current_level
        total_hp_increase = hp_per_level * levels_gained
        
        # Calculate new HP max
        # For simplicity, we calculate based on current max + increase
        # In a full implementation, we'd recalculate from level 1
        
        return new_xp, LevelUpResult(
            leveled_up=True,
            old_level=current_level,
            new_level=new_level,
            hp_increase=total_hp_increase,
            new_proficiency_bonus=proficiency_bonus(new_level),
            new_hp_max=0,  # Will be calculated by caller
        )
    
    return new_xp, None


def get_xp_progress(current_xp: int, current_level: int) -> dict[str, int]:
    """Get XP progress information for display.
    
    Args:
        current_xp: Total experience points
        current_level: Current level
        
    Returns:
        Dict with xp_current, xp_needed, xp_for_next_level
    """
    current_threshold = XP_THRESHOLDS.get(current_level, 0)
    next_threshold = get_next_level_xp(current_level)
    
    if next_threshold is None:
        # Max level
        return {
            "xp_current": current_xp,
            "xp_needed": 0,
            "xp_for_next_level": current_xp,
        }
    
    return {
        "xp_current": current_xp - current_threshold,
        "xp_needed": next_threshold - current_threshold,
        "xp_for_next_level": next_threshold,
    }

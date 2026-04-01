"""D&D 5e calculation engine.

All derived values are computed via formula, no hardcoded final values.
"""

from enum import Enum


class CharacterClass(str, Enum):
    """Supported character classes."""
    WARRIOR = "warrior"
    MAGE = "mage"
    ROGUE = "rogue"


# Class hit dice mapping
CLASS_HIT_DICE: dict[CharacterClass, int] = {
    CharacterClass.WARRIOR: 10,  # d10
    CharacterClass.MAGE: 6,      # d6
    CharacterClass.ROGUE: 8,     # d8
}


def ability_modifier(score: int) -> int:
    """Calculate ability modifier from score.
    
    Formula: floor((score - 10) / 2)
    
    Args:
        score: Ability score (typically 3-18)
        
    Returns:
        Modifier value (e.g., 10 -> 0, 15 -> +2, 8 -> -1)
        
    Examples:
        >>> ability_modifier(10)
        0
        >>> ability_modifier(15)
        2
        >>> ability_modifier(8)
        -1
        >>> ability_modifier(14)
        2
    """
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    """Calculate proficiency bonus from character level.
    
    Formula: 2 + ((level - 1) // 4)
    
    Args:
        level: Character level (1-20)
        
    Returns:
        Proficiency bonus value
        
    Examples:
        >>> proficiency_bonus(1)
        2
        >>> proficiency_bonus(4)
        2
        >>> proficiency_bonus(5)
        3
        >>> proficiency_bonus(8)
        3
        >>> proficiency_bonus(9)
        4
    """
    return 2 + ((level - 1) // 4)


def calculate_max_hp(
    character_class: CharacterClass,
    con_modifier: int,
    level: int = 1,
) -> int:
    """Calculate maximum HP for a character.
    
    Level 1: HP = hit_die_max + CON modifier
    
    Args:
        character_class: The character's class
        con_modifier: Constitution modifier
        level: Character level (default 1)
        
    Returns:
        Maximum HP value
        
    Examples:
        >>> calculate_max_hp(CharacterClass.WARRIOR, 2)  # CON 14 (+2)
        12
        >>> calculate_max_hp(CharacterClass.MAGE, 0)     # CON 10 (+0)
        6
        >>> calculate_max_hp(CharacterClass.ROGUE, 1)    # CON 12 (+1)
        9
    """
    hit_die = CLASS_HIT_DICE[character_class]
    # For level 1, HP = max hit die value + CON modifier
    if level == 1:
        return hit_die + con_modifier
    # For higher levels, would add average/hit die per level
    # This simplified version just uses level 1 formula
    return hit_die + con_modifier


def calculate_ac(
    dex_modifier: int,
    base_ac: int = 10,
    has_shield: bool = False,
) -> int:
    """Calculate Armor Class.
    
    Base formula: 10 + DEX modifier (unarmored)
    With shield: +2 to AC
    
    Args:
        dex_modifier: Dexterity modifier
        base_ac: Base AC value (default 10 for unarmored)
        has_shield: Whether character is wielding a shield
        
    Returns:
        Armor Class value
        
    Examples:
        >>> calculate_ac(2)           # DEX 14, no shield
        12
        >>> calculate_ac(2, has_shield=True)  # DEX 14, shield
        14
        >>> calculate_ac(0)           # DEX 10
        10
    """
    ac = base_ac + dex_modifier
    if has_shield:
        ac += 2
    return ac


def calculate_skill_modifier(
    ability_modifier: int,
    is_proficient: bool,
    prof_bonus: int,
) -> int:
    """Calculate skill check modifier.
    
    Formula: ability_modifier + (proficiency_bonus if proficient)
    
    Args:
        ability_modifier: The governing ability's modifier
        is_proficient: Whether the character is proficient in this skill
        prof_bonus: Character's proficiency bonus
        
    Returns:
        Skill modifier value
        
    Examples:
        >>> calculate_skill_modifier(3, True, 2)   # STR mod +3, proficient
        5
        >>> calculate_skill_modifier(3, False, 2)  # STR mod +3, not proficient
        3
        >>> calculate_skill_modifier(-1, True, 2)  # CHA mod -1, proficient
        1
    """
    modifier = ability_modifier
    if is_proficient:
        modifier += prof_bonus
    return modifier

"""Scene-specific skill check resolution.

This module handles skill checks for scene interactive elements,
providing detailed results for scene interactions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..engine.dice import roll_d20
from ..engine.resolver import _is_skill_proficient, _get_skill_ability
from ..models.state import Actor
from ..scenes.data import InteractiveElement


@dataclass
class SceneCheckResult:
    """Detailed result of a scene skill check.
    
    This is used internally for scene interaction resolution and testing.
    """
    skill: str
    ability: str
    roll: int
    ability_modifier: int
    proficiency_bonus: int
    total: int
    dc: int
    success: bool
    is_proficient: bool


def resolve_scene_skill_check(
    actor: Actor,
    element: InteractiveElement,
    advantage: Optional[bool] = None,
) -> SceneCheckResult:
    """Resolve a skill check for a scene interactive element.
    
    Formula: d20 + ability modifier + proficiency bonus (if proficient)
    
    Args:
        actor: The actor performing the check
        element: The interactive element being interacted with
        advantage: Optional advantage/disadvantage flag
        
    Returns:
        SceneCheckResult with detailed check information
    """
    # Determine skill and governing ability
    skill_name = element.skill
    ability = _get_skill_ability(skill_name)
    
    # Calculate modifiers
    ability_modifier = actor.abilities.modifier(ability)
    is_proficient = _is_skill_proficient(actor, skill_name)
    prof_bonus = actor.proficiency_bonus if is_proficient else 0
    
    dc = element.dc
    
    # Roll d20 + ability modifier + proficiency (if proficient)
    roll = roll_d20(advantage=advantage)
    total = roll + ability_modifier + prof_bonus
    success = total >= dc
    
    return SceneCheckResult(
        skill=skill_name,
        ability=ability,
        roll=roll,
        ability_modifier=ability_modifier,
        proficiency_bonus=prof_bonus,
        total=total,
        dc=dc,
        success=success,
        is_proficient=is_proficient,
    )

"""Scene interaction handler for interactive elements.

This module handles player interactions with environmental elements in scenes,
triggering appropriate skill checks and managing rewards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..models.action import ActionRequest, ActionResponse, Effect, Outcome, ResolutionType
from ..scenes.data import InteractiveElement, SceneData, get_scene_by_id
from ..state import get_actor, get_scene


@dataclass
class SceneInteractionRequest:
    """Request to interact with a scene element."""
    element_id: str
    action_name: str
    actor_id: str


@dataclass
class SceneInteractionResult:
    """Result of a scene interaction."""
    element: InteractiveElement
    success: bool
    roll: int
    modifier: int
    proficiency_bonus: int
    total: int
    dc: int
    skill: str
    narrative: str
    reward_item: Optional[str] = None
    reward_info: Optional[str] = None


def is_scene_interaction_action(intent: str, scene_id: str) -> bool:
    """Check if the action intent matches a scene interactive element.
    
    Args:
        intent: The player's action intent
        scene_id: The current scene ID
        
    Returns:
        True if the intent matches an interactive element's action
    """
    scene_data = get_scene_by_id(scene_id)
    if not scene_data or not scene_data.interactive_elements:
        return False
    
    intent_lower = intent.lower()
    for element in scene_data.interactive_elements:
        # Match by action name or element name
        if element.action_name.lower() in intent_lower:
            return True
        if element.name.lower() in intent_lower:
            return True
        # Match by keywords in intent
        action_keywords = element.action_name.lower().split()
        if all(kw in intent_lower for kw in action_keywords):
            return True
    
    return False


def find_interactive_element(intent: str, scene_id: str) -> Optional[InteractiveElement]:
    """Find a matching interactive element for the given intent.
    
    Args:
        intent: The player's action intent
        scene_id: The current scene ID
        
    Returns:
        The matching InteractiveElement or None
    """
    scene_data = get_scene_by_id(scene_id)
    if not scene_data or not scene_data.interactive_elements:
        return None
    
    intent_lower = intent.lower()
    
    for element in scene_data.interactive_elements:
        # Direct match by action name
        if element.action_name.lower() in intent_lower:
            return element
        # Match by element name
        if element.name.lower() in intent_lower:
            return element
        # Match by keywords
        action_keywords = element.action_name.lower().split()
        if len(action_keywords) > 0 and all(kw in intent_lower for kw in action_keywords):
            return element
    
    return None


def handle_scene_interaction(
    req: ActionRequest,
    element: InteractiveElement,
) -> tuple[ActionResponse, SceneInteractionResult]:
    """Handle a scene interaction, performing skill check and returning result.
    
    Args:
        req: The action request
        element: The interactive element being interacted with
        
    Returns:
        Tuple of (ActionResponse, SceneInteractionResult)
    """
    from ..engine.dice import roll_d20
    from ..engine.resolver import _is_skill_proficient, _get_skill_ability
    
    actor = get_actor()
    scene = get_scene()
    
    # Determine skill and governing ability
    skill_name = element.skill
    ability = _get_skill_ability(skill_name)
    
    # Calculate modifiers
    ability_modifier = actor.abilities.modifier(ability)
    is_proficient = _is_skill_proficient(actor, skill_name)
    prof_bonus = actor.proficiency_bonus if is_proficient else 0
    
    dc = element.dc
    
    # Roll d20 + ability modifier + proficiency (if proficient)
    roll = roll_d20(advantage=None)
    total = roll + ability_modifier + prof_bonus
    success = total >= dc
    
    # Build effects
    effects: list[Effect] = []
    effects.append(
        Effect(
            target=scene.id,
            field="time",
            delta=1,
            description=f"Interacted with {element.name}.",
        )
    )
    
    # Determine narrative based on success/failure
    if success:
        narrative = element.success_narrative
        if element.reward_item:
            effects.append(
                Effect(
                    target=actor.id,
                    field="inventory_add",
                    delta=element.reward_item,
                    description=f"Acquired {element.reward_item} from {element.name}.",
                )
            )
    else:
        narrative = element.failure_narrative
        # Minor penalty on failure - small HP loss
        effects.append(
            Effect(
                target=actor.id,
                field="hp",
                delta=-1,
                description=f"Minor harm from failed attempt on {element.name}.",
            )
        )
    
    action_summary = f"{req.actor} {element.action_name}"
    
    from ..models.action import CheckDetail, SkillCheckDetail
    
    check = CheckDetail(
        ability=ability,
        modifier=ability_modifier,
        proficiency_bonus=prof_bonus,
        advantage=None,
        roll=roll,
        total=total,
        dc=dc,
        skill_name=skill_name,
    )
    
    skill_check = SkillCheckDetail(
        skill=skill_name,
        roll=roll,
        modifier=ability_modifier + prof_bonus,
        total=total,
        dc=dc,
        success=success,
    )
    
    # Scene progression hint
    if success:
        scene_progression = f"你成功与{element.name}互动。可以继续探索或尝试其他行动。"
    else:
        scene_progression = f"你未能成功与{element.name}互动。可以选择再次尝试或改变策略。"
    
    response = ActionResponse(
        action_summary=action_summary,
        resolution_type=ResolutionType.CHECK,
        check=check,
        skill_check=skill_check,
        attack=None,
        outcome=Outcome.SUCCESS if success else Outcome.FAILURE,
        effects=effects,
        narration=narrative,
        scene_progression=scene_progression,
        gm_prompt=f"Player {'succeeded' if success else 'failed'} to interact with {element.name}.",
    )
    
    result = SceneInteractionResult(
        element=element,
        success=success,
        roll=roll,
        modifier=ability_modifier,
        proficiency_bonus=prof_bonus,
        total=total,
        dc=dc,
        skill=skill_name,
        narrative=narrative,
        reward_item=element.reward_item if success else None,
        reward_info=element.reward_info if success else None,
    )
    
    return response, result

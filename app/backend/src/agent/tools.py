"""GM Agent tool definitions.

This module defines the tool interface for the GM Agent, including:
- Tool schemas for agent reasoning
- Tool implementations that wrap engine functions
- Tool result types for tracking multi-step execution
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..engine.dice import roll_d20, roll_damage
from ..models.action import ActionRequest, Effect, Outcome
from ..models.state import Actor, NarrativeHistoryEntry, Scene
from ..state import (
    apply_effects,
    get_actor,
    get_actor_by_id_or_name,
    get_narrative_context,
    get_scene,
)


# ---------------------------------------------------------------------------
# Tool Types
# ---------------------------------------------------------------------------

class ToolType(str, Enum):
    """Available tool types for GM Agent."""
    ROLL_DICE = "roll_dice"
    APPLY_STATE_CHANGE = "apply_state_change"
    GET_CURRENT_STATE = "get_current_state"
    GENERATE_NARRATIVE = "generate_narrative"


class DiceType(str, Enum):
    """Types of dice rolls."""
    D20 = "d20"
    DAMAGE = "damage"


# ---------------------------------------------------------------------------
# Tool Input Schemas
# ---------------------------------------------------------------------------

class RollDiceInput(BaseModel):
    """Input for roll_dice tool."""
    dice_type: DiceType = Field(..., description="Type of dice to roll")
    advantage: Optional[bool] = Field(None, description="Advantage/disadvantage for d20")
    dice_expression: Optional[str] = Field(None, description="Dice expression for damage (e.g., '1d8')")
    reason: str = Field(..., description="Why this roll is needed")


class ApplyStateChangeInput(BaseModel):
    """Input for apply_state_change tool."""
    target: str = Field(..., description="Target actor ID or scene ID")
    field: str = Field(..., description="Field to modify (hp, conditions_add, etc.)")
    delta: int | str = Field(..., description="Change amount or value")
    description: str = Field(..., description="Human-readable description of the change")


class GetCurrentStateInput(BaseModel):
    """Input for get_current_state tool (empty - returns full state)."""
    actor_id: Optional[str] = Field(None, description="Optional specific actor ID")


class GenerateNarrativeInput(BaseModel):
    """Input for generate_narrative tool."""
    outcome: Outcome = Field(..., description="Overall outcome of the action")
    check_result: Optional[dict] = Field(None, description="Details of ability check if any")
    attack_result: Optional[dict] = Field(None, description="Details of attack if any")
    saving_throw_result: Optional[dict] = Field(None, description="Details of saving throw if any")
    context: dict = Field(default_factory=dict, description="Additional context for narrative")


# ---------------------------------------------------------------------------
# Tool Result Types
# ---------------------------------------------------------------------------

class ToolResult(BaseModel):
    """Base class for tool execution results."""
    tool: ToolType
    success: bool
    error: Optional[str] = None


class RollDiceResult(ToolResult):
    """Result of a dice roll."""
    tool: ToolType = ToolType.ROLL_DICE
    roll_type: DiceType
    roll: int
    total: int
    rolls: list[int] = Field(default_factory=list)
    modifier: int = 0
    reason: str = ""


class ApplyStateChangeResult(ToolResult):
    """Result of applying a state change."""
    tool: ToolType = ToolType.APPLY_STATE_CHANGE
    effect: Effect
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None


class CurrentStateResult(ToolResult):
    """Result of getting current state."""
    tool: ToolType = ToolType.GET_CURRENT_STATE
    actor: Actor
    scene: Scene
    other_actors: list[Actor] = Field(default_factory=list)


class NarrativeResult(ToolResult):
    """Result of narrative generation."""
    tool: ToolType = ToolType.GENERATE_NARRATIVE
    narrative: str
    scene_progression: str
    gm_prompt: str


# Union type for all tool results
ToolResultType = RollDiceResult | ApplyStateChangeResult | CurrentStateResult | NarrativeResult


# ---------------------------------------------------------------------------
# Tool Implementations
# ---------------------------------------------------------------------------

def tool_roll_dice(
    dice_type: DiceType,
    reason: str,
    advantage: Optional[bool] = None,
    dice_expression: Optional[str] = None,
    modifier: int = 0,
) -> RollDiceResult:
    """Execute a dice roll.
    
    Args:
        dice_type: Type of dice roll (d20 or damage)
        reason: Why this roll is being made
        advantage: Advantage/disadvantage for d20 rolls
        dice_expression: Dice expression for damage rolls (e.g., "1d8", "2d6+3")
        modifier: Modifier to add to the roll
        
    Returns:
        RollDiceResult with roll details
    """
    try:
        if dice_type == DiceType.D20:
            roll = roll_d20(advantage)
            total = roll + modifier
            return RollDiceResult(
                success=True,
                roll_type=dice_type,
                roll=roll,
                total=total,
                rolls=[roll],
                modifier=modifier,
                reason=reason,
            )
        elif dice_type == DiceType.DAMAGE:
            if not dice_expression:
                dice_expression = "1d6"
            total, rolls = roll_damage(dice_expression)
            return RollDiceResult(
                success=True,
                roll_type=dice_type,
                roll=total,
                total=total,
                rolls=rolls,
                modifier=0,
                reason=reason,
            )
        else:
            return RollDiceResult(
                success=False,
                roll_type=dice_type,
                roll=0,
                total=0,
                reason=reason,
                error=f"Unknown dice type: {dice_type}",
            )
    except Exception as e:
        return RollDiceResult(
            success=False,
            roll_type=dice_type,
            roll=0,
            total=0,
            reason=reason,
            error=str(e),
        )


def tool_apply_state_change(
    target: str,
    field: str,
    delta: int | str,
    description: str,
) -> ApplyStateChangeResult:
    """Apply a state change to the game state.
    
    Args:
        target: Target actor ID or scene ID
        field: Field to modify
        delta: Change amount or value
        description: Human-readable description
        
    Returns:
        ApplyStateChangeResult with effect details
    """
    effect = Effect(
        target=target,
        field=field,
        delta=delta,
        description=description,
    )
    
    # Capture previous values if possible
    previous_value = None
    actor = get_actor_by_id_or_name(target)
    if actor and field == "hp":
        previous_value = actor.hp
    
    # Apply the effect
    apply_effects([effect])
    
    # Capture new value
    new_value = None
    actor = get_actor_by_id_or_name(target)
    if actor and field == "hp":
        new_value = actor.hp
    
    return ApplyStateChangeResult(
        success=True,
        effect=effect,
        previous_value=previous_value,
        new_value=new_value,
    )


def tool_get_current_state(actor_id: Optional[str] = None) -> CurrentStateResult:
    """Get the current game state.
    
    Args:
        actor_id: Optional specific actor ID to focus on
        
    Returns:
        CurrentStateResult with actor, scene, and other actors
    """
    actor = get_actor_by_id_or_name(actor_id) if actor_id else get_actor()
    if actor is None:
        actor = get_actor()
    
    scene = get_scene()
    
    # Get other actors in scene
    other_actors: list[Actor] = []
    for actor_id_in_scene in scene.actors:
        if actor_id_in_scene != actor.id:
            other = get_actor_by_id_or_name(actor_id_in_scene)
            if other:
                other_actors.append(other)
    
    return CurrentStateResult(
        success=True,
        actor=actor,
        scene=scene,
        other_actors=other_actors,
    )


def tool_generate_narrative(
    req: ActionRequest,
    outcome: Outcome,
    check_result: Optional[dict] = None,
    attack_result: Optional[dict] = None,
    saving_throw_result: Optional[dict] = None,
    effects: Optional[list[Effect]] = None,
    narrative_history: Optional[list[NarrativeHistoryEntry]] = None,
) -> NarrativeResult:
    """Generate narrative text for the action resolution.
    
    Args:
        req: The original action request
        outcome: Overall outcome
        check_result: Optional ability check details
        attack_result: Optional attack details
        saving_throw_result: Optional saving throw details
        
    Returns:
        NarrativeResult with generated narrative
    """
    from .narrator import generate_narration
    
    state = tool_get_current_state()
    target = None
    if attack_result:
        target_name = attack_result.get("target")
        if isinstance(target_name, str):
            target = get_actor_by_id_or_name(target_name)
    
    narrative = generate_narration(
        req=req,
        actor=state.actor,
        scene=state.scene,
        outcome=outcome,
        check_result=check_result,
        attack_result=attack_result,
        saving_throw_result=saving_throw_result,
        effects=effects,
        target=target,
        narrative_history=narrative_history or get_narrative_context(),
    )
    
    return NarrativeResult(
        success=True,
        narrative=narrative.action_result,
        scene_progression=narrative.scene_progression,
        gm_prompt=narrative.gm_prompt,
    )


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[ToolType, callable] = {
    ToolType.ROLL_DICE: tool_roll_dice,
    ToolType.APPLY_STATE_CHANGE: tool_apply_state_change,
    ToolType.GET_CURRENT_STATE: tool_get_current_state,
    ToolType.GENERATE_NARRATIVE: tool_generate_narrative,
}


def execute_tool(tool_type: ToolType, **kwargs) -> ToolResultType:
    """Execute a tool by type with given arguments.
    
    Args:
        tool_type: Type of tool to execute
        **kwargs: Arguments for the tool
        
    Returns:
        Tool execution result
    """
    tool_func = TOOL_REGISTRY.get(tool_type)
    if not tool_func:
        raise ValueError(f"Unknown tool type: {tool_type}")
    return tool_func(**kwargs)

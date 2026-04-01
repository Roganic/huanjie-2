"""GM Agent module for action orchestration.

The GM Agent is the primary driver of action resolution, replacing
the linear "action -> rules -> narrative" pipeline with an agent-driven
orchestration that can perform multi-step reasoning.
"""

from .narrator import generate_narration
from .orchestrator import GMAgent, resolve_action_with_agent
from .tools import (
    ApplyStateChangeResult,
    CurrentStateResult,
    DiceType,
    NarrativeResult,
    RollDiceResult,
    ToolResultType,
    ToolType,
    tool_apply_state_change,
    tool_generate_narrative,
    tool_get_current_state,
    tool_roll_dice,
)

__all__ = [
    # Main orchestrator
    "GMAgent",
    "resolve_action_with_agent",
    # Narrative
    "generate_narration",
    # Tools
    "ToolType",
    "DiceType",
    "ToolResultType",
    "RollDiceResult",
    "ApplyStateChangeResult",
    "CurrentStateResult",
    "NarrativeResult",
    "tool_roll_dice",
    "tool_apply_state_change",
    "tool_get_current_state",
    "tool_generate_narrative",
]

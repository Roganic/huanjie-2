"""NPC system with dialogue state management."""

# Re-export NPC functions from the sibling npc.py module
# Note: This requires the parent module to have imported npc.py first

# Import dialogue state functions
from .dialogue_state import (
    NPCDialogueEntry,
    NPCDialogueState,
    record_dialogue,
    get_dialogue_history,
    get_npc_dialogue_count,
    build_dialogue_context_for_prompt,
)

# Deferred import from npc.py to avoid circular import issues
def is_npc_interaction(*args, **kwargs):
    """Check if the intent/approach is targeting an NPC."""
    from ..npc import is_npc_interaction as _is_npc_interaction
    return _is_npc_interaction(*args, **kwargs)

def find_target_npc(*args, **kwargs):
    """Find the target NPC based on intent/approach."""
    from ..npc import find_target_npc as _find_target_npc
    return _find_target_npc(*args, **kwargs)

__all__ = [
    "is_npc_interaction",
    "find_target_npc",
    "NPCDialogueEntry",
    "NPCDialogueState",
    "record_dialogue",
    "get_dialogue_history",
    "get_npc_dialogue_count",
    "build_dialogue_context_for_prompt",
]

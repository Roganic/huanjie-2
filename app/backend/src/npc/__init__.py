"""NPC system with dialogue state management."""

from .dialogue_state import (
    NPCDialogueEntry,
    NPCDialogueState,
    record_dialogue,
    get_dialogue_history,
    get_npc_dialogue_count,
    build_dialogue_context_for_prompt,
)

__all__ = [
    "NPCDialogueEntry",
    "NPCDialogueState",
    "record_dialogue",
    "get_dialogue_history",
    "get_npc_dialogue_count",
    "build_dialogue_context_for_prompt",
]

"""NPC system with dialogue state management."""

import importlib.util
import os

# Load the shadowed src/npc.py module so its functions remain accessible
_spec = importlib.util.spec_from_file_location(
    "_npc_core", os.path.join(os.path.dirname(__file__), "..", "npc.py")
)
_npc_core = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_npc_core)

NPC = _npc_core.NPC
NPCType = _npc_core.NPCType
find_target_npc = _npc_core.find_target_npc
is_npc_interaction = _npc_core.is_npc_interaction
get_npc_by_id = _npc_core.get_npc_by_id
get_npcs_by_ids = _npc_core.get_npcs_by_ids
get_npc_names_for_scene = _npc_core.get_npc_names_for_scene

from .dialogue_state import (
    NPCDialogueEntry,
    NPCDialogueState,
    record_dialogue,
    get_dialogue_history,
    get_npc_dialogue_count,
    build_dialogue_context_for_prompt,
)

__all__ = [
    "NPC",
    "NPCType",
    "find_target_npc",
    "is_npc_interaction",
    "get_npc_by_id",
    "get_npcs_by_ids",
    "get_npc_names_for_scene",
    "NPCDialogueEntry",
    "NPCDialogueState",
    "record_dialogue",
    "get_dialogue_history",
    "get_npc_dialogue_count",
    "build_dialogue_context_for_prompt",
]

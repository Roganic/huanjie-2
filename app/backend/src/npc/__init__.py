"""NPC helpers over the shared content and session models."""
import re
from ..models.state import NPC, NPCType
from .dialogue_state import (
    NPCDialogueEntry, NPCDialogueState, record_dialogue, get_dialogue_history,
    get_npc_dialogue_count, build_dialogue_context_for_prompt,
)


def get_npc_by_id(npc_id, pack=None):
    from ..content.store import builtin
    definition = (pack or builtin()).characters.get(npc_id)
    if definition is None:
        return None
    return NPC.model_validate(definition.model_dump())


def get_npcs_by_ids(npc_ids, pack=None):
    return [npc for id in npc_ids if (npc := get_npc_by_id(id, pack)) is not None]


def get_npc_names_for_scene(npc_ids, pack=None):
    return [npc.name for npc in get_npcs_by_ids(npc_ids, pack)]


def find_target_npc(intent, approach_or_ids, npcs=None):
    # Retain both historical calling forms without a second NPC registry.
    text = intent if npcs is None else f"{intent} {approach_or_ids}"
    candidates = get_npcs_by_ids(approach_or_ids) if npcs is None else npcs
    return next((npc for npc in candidates if npc.name.lower() in text.lower() or npc.id.lower() in text.lower()), None)


def is_npc_interaction(intent, approach_or_ids=""):
    if isinstance(approach_or_ids, list):
        return find_target_npc(intent, approach_or_ids) is not None
    return bool(re.search(r"说话|交谈|对话|聊天|询问|打听|问候|搭话|打招呼|\b(talk|speak|chat|ask|hello)\b", f"{intent} {approach_or_ids}", re.I))

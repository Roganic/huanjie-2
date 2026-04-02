"""NPC system with dialogue state management."""

from typing import Optional

from ..models.state import NPC

# Import dialogue state functions
from .dialogue_state import (
    NPCDialogueEntry,
    NPCDialogueState,
    record_dialogue,
    get_dialogue_history,
    get_npc_dialogue_count,
    build_dialogue_context_for_prompt,
)

# NPC interaction keywords
_NPC_INTERACTION_KEYWORDS = [
    # Chinese
    "说话", "交谈", "聊天", "对话", "询问", "打听", "问", "聊", "谈",
    "打招呼", "问候", "求助", "请求", "商量", "讨论", "说服", "劝说",
    "贿赂", "交易", "购买", "卖", "买", "雇佣", "邀请",
    # English
    "talk", "speak", "chat", "converse", "ask", "inquire", "greet",
    "question", "persuade", "convince", "bribe", "trade", "buy", "sell",
    "hire", "invite", "approach", "address",
]


def _is_npc_interaction_text(text: str) -> bool:
    """Check if text contains NPC interaction keywords."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in _NPC_INTERACTION_KEYWORDS)


def is_npc_interaction(intent: str, approach: str) -> bool:
    """Check if an action intent/approach indicates NPC interaction."""
    return _is_npc_interaction_text(intent) or _is_npc_interaction_text(approach)


def find_target_npc(intent: str, approach: str, npcs: list[NPC]) -> Optional[NPC]:
    """Find the target NPC from action text based on name matching.
    
    Args:
        intent: The player's action intent
        approach: The player's action approach
        npcs: List of NPCs present in the current scene
        
    Returns:
        The matched NPC if found, None otherwise
    """
    combined = f"{intent} {approach}".lower()
    
    for npc in npcs:
        # Check for exact name match
        if npc.name.lower() in combined:
            return npc
        # Check for ID match (without hyphens for flexibility)
        npc_id_simple = npc.id.replace("-", "").lower()
        if npc_id_simple in combined.replace("-", " ").lower():
            return npc
        # Check for race/occupation match if unique in scene
        if npc.race and npc.race.lower() in combined:
            # Only match if this race is unique in the scene
            race_matches = [n for n in npcs if n.race and n.race.lower() == npc.race.lower()]
            if len(race_matches) == 1:
                return npc
        if npc.occupation and npc.occupation.lower() in combined:
            occupation_matches = [n for n in npcs if n.occupation and n.occupation.lower() == npc.occupation.lower()]
            if len(occupation_matches) == 1:
                return npc
    
    return None


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

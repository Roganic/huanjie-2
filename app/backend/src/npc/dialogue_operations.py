"""NPC dialogue operations for action resolution.

This module provides functionality to detect NPC dialogue actions and
record them to the dialogue state.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from ..models.action import ActionRequest
from ..models.state import Scene
from ..state import (
    get_scene,
    record_npc_dialogue as _record_npc_dialogue,
)


# Keywords that indicate talking/speaking to an NPC
DIALOGUE_KEYWORDS = [
    "talk", "speak", "say", "ask", "chat", "greet", "hello", "hi",
    "conversation", "dialogue", "tell", "inquire", "question",
    "说", "说话", "谈话", "交谈", "问", "询问", "打招呼", "问候",
    "聊", "聊聊", "告诉", "打听", "和.*说话", "与.*交谈", "对.*说",
]


def is_npc_dialogue_action(req: ActionRequest) -> bool:
    """Check if the action involves talking to an NPC.
    
    Args:
        req: The action request
        
    Returns:
        True if this is a dialogue action with an NPC
    """
    action_text = f"{req.intent} {req.approach}".lower()
    
    # Check for dialogue keywords
    for keyword in DIALOGUE_KEYWORDS:
        # Handle regex patterns (like "和.*说话")
        if ".*" in keyword:
            if re.search(keyword, action_text):
                return True
        elif keyword in action_text:
            return True
    
    return False


def identify_target_npc(
    req: ActionRequest,
    scene: Optional[Scene] = None,
) -> Optional[Tuple[str, str]]:
    """Identify which NPC the player is talking to.
    
    Args:
        req: The action request
        scene: Optional scene (uses current scene if None)
        
    Returns:
        Tuple of (npc_id, npc_name) if found, None otherwise
    """
    if scene is None:
        scene = get_scene()
    
    if not scene.npcs:
        return None
    
    action_text = f"{req.intent} {req.approach}".lower()
    
    # Try to match specific NPC by name or ID
    for npc in scene.npcs:
        npc_name_lower = npc.name.lower()
        npc_id_lower = npc.id.lower()
        
        # Check for exact name match
        if npc_name_lower in action_text:
            return (npc.id, npc.name)
        
        # Check for ID match
        if npc_id_lower in action_text:
            return (npc.id, npc.name)
        
        # Check for partial name match (e.g., "老马库斯" matches "马库斯")
        name_parts = npc_name_lower.split()
        for part in name_parts:
            if len(part) >= 2 and part in action_text:
                return (npc.id, npc.name)
    
    # If no specific match but there's only one friendly/neutral NPC, use that
    non_hostile = [n for n in scene.npcs if n.type.value in ("friendly", "neutral")]
    if len(non_hostile) == 1:
        npc = non_hostile[0]
        return (npc.id, npc.name)
    
    return None


def record_dialogue_from_action(
    req: ActionRequest,
    narration: str,
    scene: Optional[Scene] = None,
    session_id: Optional[str] = None,
) -> bool:
    """Record dialogue from an action if it involves NPC interaction.
    
    This function:
    1. Checks if the action is a dialogue action
    2. Identifies the target NPC
    3. Records the player dialogue and NPC response
    
    Args:
        req: The action request
        narration: The generated narration (NPC response)
        scene: Optional scene (uses current scene if None)
        session_id: Optional session ID (uses current if None)
        
    Returns:
        True if dialogue was recorded, False otherwise
    """
    if not is_npc_dialogue_action(req):
        return False
    
    npc_info = identify_target_npc(req, scene)
    if npc_info is None:
        return False
    
    npc_id, npc_name = npc_info
    
    # Record player dialogue
    player_message = f"{req.intent} (方式: {req.approach})"
    _record_npc_dialogue(npc_id, npc_name, "player", player_message, session_id)
    
    # Record NPC response (truncated for storage)
    npc_response = narration[:200] if len(narration) > 200 else narration
    _record_npc_dialogue(npc_id, npc_name, npc_name, npc_response, session_id)
    
    return True


def get_dialogue_context_for_narration(
    req: ActionRequest,
    scene: Optional[Scene] = None,
) -> str:
    """Get dialogue context for narrative generation.
    
    This is used to inject dialogue history into the narrative prompt.
    
    Args:
        req: The action request
        scene: Optional scene (uses current scene if None)
        
    Returns:
        Dialogue context string for prompt injection
    """
    from ..npc.dialogue_state import (
        build_dialogue_context_for_prompt,
        is_first_npc_contact,
    )
    
    if not is_npc_dialogue_action(req):
        return ""
    
    npc_info = identify_target_npc(req, scene)
    if npc_info is None:
        return ""
    
    npc_id, npc_name = npc_info
    
    if is_first_npc_contact(npc_id):
        return (
            f"【NPC 对话情境 / NPC DIALOGUE CONTEXT】\n"
            f"这是玩家第一次与 {npc_name} 对话。\n"
            f"NPC 还不认识玩家，应该以初次见面的态度回应。\n"
        )
    
    return build_dialogue_context_for_prompt(npc_id, npc_name)

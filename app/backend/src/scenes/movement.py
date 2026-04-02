"""Scene movement and navigation handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..scene_map import get_connected_scene, parse_movement_intent


MOVEMENT_VERBS = [
    "前往", "走向", "进入", "去", "到", "回", "返回", "离开", "走",
    "go to", "move to", "head to", "go", "move", "enter", "walk to", "walk",
    "return", "leave", "back to",
]

COMBAT_KEYWORDS = [
    "attack", "fight", "combat", "hit", "strike", "stab", "slash", "shoot",
    "kill", "defeat", "engage", "ambush", "assault", "battle",
    "攻击", "战斗", "打", "杀", "砍", "刺", "射击", "开战",
]


@dataclass
class MovementResult:
    """Result of a movement action."""
    success: bool
    message: str
    scene_id: Optional[str] = None


def is_movement_action(intent: str, approach: str) -> bool:
    """Check if the action intent describes a movement between scenes."""
    text = f"{intent} {approach}".lower()
    # Sort by length descending to match longer phrases first
    sorted_verbs = sorted(MOVEMENT_VERBS, key=len, reverse=True)
    for verb in sorted_verbs:
        verb_lower = verb.lower()
        if verb_lower in text:
            # For short English verbs, require word boundaries to avoid matching inside words
            if len(verb_lower) <= 3 and verb_lower.isascii():
                import re
                pattern = r'\b' + re.escape(verb_lower) + r'\b'
                if re.search(pattern, text):
                    return True
            else:
                return True
    return False


def can_move_in_current_state(session_id: str | None = None) -> bool:
    """Check if the actor can move in the current game state."""
    from ..models.state import AdventurePhase
    from ..state import get_game_phase
    return get_game_phase(session_id) == AdventurePhase.EXPLORATION


def handle_movement(intent: str, approach: str, session_id: str) -> MovementResult:
    """Handle a movement action and switch scenes if valid.
    
    Args:
        intent: The player's movement intent
        approach: How they attempt the movement
        session_id: The current session ID
        
    Returns:
        MovementResult indicating success/failure and any message
    """
    from ..state import get_scene, switch_scene
    
    if not can_move_in_current_state(session_id):
        return MovementResult(
            success=False,
            message="当前状态无法移动。",
        )
    
    current_scene = get_scene(session_id)
    
    # Parse the intent to find target scene or direction
    target_scene_id, direction_or_name = parse_movement_intent(intent)
    
    # If parse_movement_intent returned a direction only, try to resolve it
    if target_scene_id is None and direction_or_name:
        target_scene_id = get_connected_scene(current_scene.id, direction_or_name)
    
    # Also try direct scene name resolution from the full intent
    if target_scene_id is None:
        from ..scene_map import resolve_scene_by_name
        # Try resolving the full intent as a scene name
        target_scene_id = resolve_scene_by_name(intent)
        if target_scene_id is None and approach:
            target_scene_id = resolve_scene_by_name(approach)
    
    if target_scene_id is None:
        return MovementResult(
            success=False,
            message="不清楚你要去哪里。请指明方向或目的地。",
        )
    
    # Verify the target scene is connected from current scene
    # Allow direct transition if it's in the scene registry (for keywords like "返回酒馆")
    from ..scene_map import get_scene_node
    node = get_scene_node(current_scene.id)
    
    is_connected = False
    if node:
        for exit_info in node.exits:
            if exit_info.target_scene_id == target_scene_id:
                is_connected = True
                break
    
    # Also check via get_connected_scene with the direction
    if not is_connected and direction_or_name:
        connected = get_connected_scene(current_scene.id, direction_or_name)
        if connected == target_scene_id:
            is_connected = True
    
    # Fallback: allow movement if target is in the old scene's connected_scenes
    if not is_connected:
        from ..scenes.data import get_scene_by_id
        current_data = get_scene_by_id(current_scene.id)
        if current_data and target_scene_id in current_data.connected_scenes:
            is_connected = True
    
    if not is_connected:
        return MovementResult(
            success=False,
            message="那个方向没有路。",
        )
    
    # Perform the scene switch
    switch_success, _ = switch_scene(target_scene_id, session_id)
    if not switch_success:
        return MovementResult(
            success=False,
            message="无法到达该场景。",
        )
    
    from ..scenes.data import get_scene_by_id
    new_scene = get_scene_by_id(target_scene_id)
    scene_name = new_scene.name if new_scene else target_scene_id
    
    return MovementResult(
        success=True,
        message=f"你来到了{scene_name}。",
        scene_id=target_scene_id,
    )


def get_available_exits(session_id: str | None = None) -> list[dict]:
    """Get available exits from the current scene."""
    from ..state import get_scene
    current_scene = get_scene(session_id)
    exits = []
    
    # Try scene_map node first
    from ..scene_map import get_scene_node
    node = get_scene_node(current_scene.id)
    if node:
        for exit_info in node.exits:
            exits.append({
                "direction": exit_info.direction,
                "target_scene_id": exit_info.target_scene_id,
                "description": exit_info.description or "",
            })
        return exits
    
    # Fallback to scene exits
    for exit_data in current_scene.exits:
        exits.append({
            "direction": exit_data.direction,
            "target_scene_id": exit_data.target_scene_id,
            "description": "",
        })
    
    return exits


def get_current_scene_info(session_id: str | None = None) -> dict:
    """Get information about the current scene."""
    from ..state import get_scene
    current_scene = get_scene(session_id)
    return {
        "id": current_scene.id,
        "name": current_scene.name,
        "description": current_scene.description,
        "exits": get_available_exits(session_id),
    }

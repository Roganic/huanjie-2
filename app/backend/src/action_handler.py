"""Action handler for player movement and scene transitions.

This module handles movement actions, including:
- Parsing movement intents
- Checking combat state restrictions
- Resolving scene transitions
- Random encounter checks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .models.state import AdventurePhase
from .scene_map import (
    get_scene_node,
    get_connected_scene,
    parse_movement_intent,
    check_encounter_on_move,
    SCENE_NAME_ALIASES,
)
from .state import (
    get_game_phase,
    switch_scene,
    set_combat_scene,
    get_scene,
    get_enemy,
    _get_session,
    _resolve_session_id,
)


@dataclass
class MovementResult:
    """Result of a movement action."""
    success: bool
    message: str
    from_scene_id: str
    to_scene_id: Optional[str] = None
    triggered_combat: bool = False
    enemy_id: Optional[str] = None
    error_code: Optional[str] = None  # "in_combat", "invalid_direction", "same_scene", etc.


# Movement keywords for intent detection
MOVEMENT_VERBS = [
    "去", "前往", "走向", "进入", "到", "向", "走", "移动", "回去", "返回",
    "go", "move", "walk", "head", "enter", "leave", "exit", "return", "back",
    "north", "south", "east", "west", "up", "down",
    "北", "南", "东", "西", "上", "下",
]

# Combat-related keywords that should NOT be treated as movement
COMBAT_KEYWORDS = [
    "攻击", "战斗", "打", "杀", "砍", "刺", "射击", "开战", "战斗",
    "attack", "fight", "combat", "hit", "strike", "stab", "slash", "shoot",
    "kill", "defeat", "engage", "ambush", "assault", "battle",
]


def is_movement_action(intent: str, approach: str = "") -> bool:
    """Check if the action intent is a movement action.
    
    Args:
        intent: The action intent
        approach: The approach description
        
    Returns:
        True if this appears to be a movement action
    """
    text = f"{intent} {approach}".lower()
    
    # Check for combat keywords first - if present, it's not movement
    for keyword in COMBAT_KEYWORDS:
        if keyword.lower() in text:
            return False
    
    # Check for movement verbs
    for verb in MOVEMENT_VERBS:
        if verb.lower() in text:
            # Additional check: make sure it's not part of another word
            # For Chinese, we can do direct containment
            # For English, we'd need word boundary checks
            if len(verb) > 2 or any(c in text for c in [" ", verb]):
                return True
    
    # Check for scene name aliases
    for alias in SCENE_NAME_ALIASES.keys():
        if alias.lower() in text:
            return True
    
    return False


def can_move_in_current_state(session_id: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Check if the player can move in their current state.
    
    Args:
        session_id: The session ID
        
    Returns:
        Tuple of (can_move, error_message)
    """
    game_phase = get_game_phase(session_id)
    
    if game_phase == AdventurePhase.COMBAT:
        return False, "你正处于战斗中，无法移动！先结束战斗或击败所有敌人。"
    
    return True, None


def handle_movement(
    intent: str,
    approach: str = "",
    session_id: Optional[str] = None
) -> MovementResult:
    """Handle a movement action.
    
    Args:
        intent: The movement intent (e.g., "向北走", "去酒馆")
        approach: Optional approach description
        session_id: The session ID
        
    Returns:
        MovementResult with outcome details
    """
    # Check if we can move
    can_move, error_msg = can_move_in_current_state(session_id)
    if not can_move:
        current_scene = get_scene(session_id)
        return MovementResult(
            success=False,
            message=error_msg or "无法移动",
            from_scene_id=current_scene.id,
            error_code="in_combat"
        )
    
    # Get current scene
    current_scene = get_scene(session_id)
    current_node = get_scene_node(current_scene.id)
    
    if not current_node:
        return MovementResult(
            success=False,
            message=f"当前场景 {current_scene.name} 无法导航",
            from_scene_id=current_scene.id,
            error_code="no_nav_data"
        )
    
    # Parse the movement intent
    full_intent = f"{intent} {approach}".strip()
    target_scene_id, direction_or_name = parse_movement_intent(full_intent)
    
    # If we got a direction, resolve it using current scene exits
    if direction_or_name and not target_scene_id:
        target_scene_id = get_connected_scene(current_scene.id, direction_or_name)
        if not target_scene_id:
            available_exits = current_node.get_exit_directions()
            return MovementResult(
                success=False,
                message=f"无法向'{direction_or_name}'移动。可用出口: {', '.join(available_exits) or '无'}",
                from_scene_id=current_scene.id,
                error_code="invalid_direction"
            )
    
    # If we got a scene ID, validate it's connected
    if target_scene_id:
        # Check if this scene is directly reachable
        connected_scene = get_connected_scene(current_scene.id, target_scene_id)
        
        # Also check if the target_scene_id is actually a scene name/alias that resolves
        if not connected_scene:
            # Try to find an exit that leads to this scene
            for exit_info in current_node.exits:
                if exit_info.target_scene_id == target_scene_id:
                    connected_scene = target_scene_id
                    break
        
        if not connected_scene and target_scene_id != current_scene.id:
            # Scene exists but isn't directly connected
            target_node = get_scene_node(target_scene_id)
            if target_node:
                return MovementResult(
                    success=False,
                    message=f"无法直接前往{target_node.name}。请检查可用出口。",
                    from_scene_id=current_scene.id,
                    error_code="not_connected"
                )
        
        if target_scene_id == current_scene.id:
            return MovementResult(
                success=False,
                message=f"你已经在了{current_node.name}。",
                from_scene_id=current_scene.id,
                error_code="same_scene"
            )
        
        # Perform the scene switch
        switch_scene(target_scene_id, session_id)
        
        # Check for random encounter at destination
        triggered_combat = False
        enemy_id = None
        encounter_triggered, encounter_enemy = check_encounter_on_move(
            current_scene.id, target_scene_id
        )
        
        if encounter_triggered:
            triggered_combat = True
            enemy_id = encounter_enemy
            # Set combat scene
            set_combat_scene(session_id)
        
        target_node = get_scene_node(target_scene_id)
        target_name = target_node.name if target_node else target_scene_id
        
        message = f"你移动到了{target_name}。"
        if triggered_combat:
            message += f" {target_node.encounter_config.encounter_description if target_node else '遭遇敌人！'}"
        
        return MovementResult(
            success=True,
            message=message,
            from_scene_id=current_scene.id,
            to_scene_id=target_scene_id,
            triggered_combat=triggered_combat,
            enemy_id=enemy_id,
        )
    
    # Could not parse movement intent
    available_exits = current_node.get_exit_directions()
    return MovementResult(
        success=False,
        message=f"无法理解移动意图'{intent}'。可用出口: {', '.join(available_exits) or '无'}",
        from_scene_id=current_scene.id,
        error_code="parse_error"
    )


def get_available_exits(session_id: Optional[str] = None) -> list[dict]:
    """Get available exits from current scene.
    
    Args:
        session_id: The session ID
        
    Returns:
        List of exit info dictionaries
    """
    current_scene = get_scene(session_id)
    node = get_scene_node(current_scene.id)
    
    if not node:
        return []
    
    exits = []
    for exit_info in node.exits:
        target_node = get_scene_node(exit_info.target_scene_id)
        exits.append({
            "direction": exit_info.direction,
            "target_scene_id": exit_info.target_scene_id,
            "target_name": target_node.name if target_node else exit_info.target_scene_id,
            "description": exit_info.description,
        })
    
    return exits


def get_current_scene_info(session_id: Optional[str] = None) -> dict:
    """Get comprehensive current scene information.
    
    Args:
        session_id: The session ID
        
    Returns:
        Dictionary with scene info including exits, npcs, encounter rate
    """
    current_scene = get_scene(session_id)
    node = get_scene_node(current_scene.id)
    game_phase = get_game_phase(session_id)
    
    result = {
        "scene_id": current_scene.id,
        "name": current_scene.name,
        "description": current_scene.description,
        "exits": [],
        "npcs": [npc.model_dump(mode="json") for npc in current_scene.npcs],
        "can_move": game_phase != AdventurePhase.COMBAT,
        "game_phase": game_phase.value,
        "encounter_rate": 0.0,
    }
    
    if node:
        result["exits"] = [
            {
                "direction": exit_info.direction,
                "target_scene_id": exit_info.target_scene_id,
                "target_name": get_scene_node(exit_info.target_scene_id).name if get_scene_node(exit_info.target_scene_id) else exit_info.target_scene_id,
                "description": exit_info.description,
            }
            for exit_info in node.exits
        ]
        result["encounter_rate"] = node.encounter_config.encounter_rate
        result["available_actions"] = node.available_actions
    
    return result

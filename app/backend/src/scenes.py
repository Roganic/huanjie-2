"""Scene management module.

This module provides a unified interface for scene data and navigation.
It re-exports from scene_map and scenes subpackage for backward compatibility.
"""

from __future__ import annotations

# Re-export from scene_map (new scene navigation system)
from .scene_map import (
    # Classes
    SceneExitInfo,
    EncounterConfig,
    SceneMapNode,
    MovementResult,
    
    # Scene nodes
    VILLAGE_SQUARE_NODE,
    TAVERN_NODE,
    DUNGEON_ENTRANCE_NODE,
    VAULT_NODE,
    
    # Registries
    SCENE_MAP,
    DIRECTION_ALIASES,
    SCENE_NAME_ALIASES,
    
    # Functions
    get_scene_node,
    get_default_scene_node,
    resolve_direction,
    resolve_scene_by_name,
    parse_movement_intent,
    get_connected_scene,
    check_encounter_on_move,
)

# Re-export from scenes.data (original scene data)
from .scenes.data import (
    # Classes
    SceneData,
    
    # Scene data (mapped to new node system)
    VILLAGE_SQUARE_SCENE,
    TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE,
    COMBAT_ENCOUNTER_SCENE,
    VAULT_SCENE,
    
    # Registries
    SCENE_REGISTRY,
    SCENE_TRANSITION_KEYWORDS,
    
    # Functions
    get_scene_by_id,
    get_scene_transition,
    get_default_exploration_scene,
    get_all_scene_names,
    build_scene_context_for_prompt,
)

# Re-export from action_handler
from .action_handler import (
    is_movement_action,
    can_move_in_current_state,
    handle_movement,
    get_available_exits,
    get_current_scene_info,
    MOVEMENT_VERBS,
    COMBAT_KEYWORDS,
)

__all__ = [
    # Classes
    "SceneExitInfo",
    "EncounterConfig",
    "SceneMapNode",
    "MovementResult",
    "SceneData",
    
    # Scene nodes
    "VILLAGE_SQUARE_NODE",
    "TAVERN_NODE",
    "DUNGEON_ENTRANCE_NODE",
    "VAULT_NODE",
    
    # Scene data
    "VILLAGE_SQUARE_SCENE",
    "TAVERN_SCENE",
    "DUNGEON_ENTRANCE_SCENE",
    "COMBAT_ENCOUNTER_SCENE",
    "VAULT_SCENE",
    
    # Registries
    "SCENE_MAP",
    "SCENE_REGISTRY",
    "DIRECTION_ALIASES",
    "SCENE_NAME_ALIASES",
    "SCENE_TRANSITION_KEYWORDS",
    
    # Constants
    "MOVEMENT_VERBS",
    "COMBAT_KEYWORDS",
    
    # Scene map functions
    "get_scene_node",
    "get_default_scene_node",
    "resolve_direction",
    "resolve_scene_by_name",
    "parse_movement_intent",
    "get_connected_scene",
    "check_encounter_on_move",
    
    # Scene data functions
    "get_scene_by_id",
    "get_scene_transition",
    "get_default_exploration_scene",
    "get_all_scene_names",
    "build_scene_context_for_prompt",
    
    # Action handler functions
    "is_movement_action",
    "can_move_in_current_state",
    "handle_movement",
    "get_available_exits",
    "get_current_scene_info",
]

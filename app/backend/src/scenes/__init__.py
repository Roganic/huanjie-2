"""Scene content system for exploration phase.

This module manages scene data, scene switching, and scene-related utilities.
Scenes are the primary locations where gameplay takes place.
"""

from .data import (
    InteractiveElement,
    SceneData,
    VILLAGE_SQUARE_SCENE,
    TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE,
    COMBAT_ENCOUNTER_SCENE,
    VAULT_SCENE,
    SCENE_REGISTRY,
    SCENE_TRANSITION_KEYWORDS,
    get_scene_by_id,
    get_scene_transition,
    get_default_exploration_scene,
    get_all_scene_names,
    build_scene_context_for_prompt,
)
from ..action_handler import (
    is_movement_action,
    handle_movement,
    get_available_exits,
)

__all__ = [
    "InteractiveElement",
    "SceneData",
    "VILLAGE_SQUARE_SCENE",
    "TAVERN_SCENE",
    "DUNGEON_ENTRANCE_SCENE",
    "COMBAT_ENCOUNTER_SCENE",
    "VAULT_SCENE",
    "SCENE_REGISTRY",
    "SCENE_TRANSITION_KEYWORDS",
    "get_scene_by_id",
    "get_scene_transition",
    "get_default_exploration_scene",
    "get_all_scene_names",
    "build_scene_context_for_prompt",
    "is_movement_action",
    "handle_movement",
    "get_available_exits",
]

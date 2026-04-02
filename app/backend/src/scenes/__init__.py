"""Scene content system for exploration phase.

This module manages scene data, scene switching, and scene-related utilities.
Scenes are the primary locations where gameplay takes place.
"""

from .data import (
    InteractiveElement,
    SceneData,
    TAVERN_SCENE,
    VILLAGE_SQUARE_SCENE,
    DUNGEON_ENTRANCE_SCENE,
    COMBAT_ENCOUNTER_SCENE,
    SCENE_REGISTRY,
    SCENE_TRANSITION_KEYWORDS,
    get_scene_by_id,
    get_scene_transition,
    get_default_exploration_scene,
    get_all_scene_names,
    build_scene_context_for_prompt,
)

__all__ = [
    "InteractiveElement",
    "SceneData",
    "TAVERN_SCENE",
    "VILLAGE_SQUARE_SCENE",
    "DUNGEON_ENTRANCE_SCENE",
    "COMBAT_ENCOUNTER_SCENE",
    "SCENE_REGISTRY",
    "SCENE_TRANSITION_KEYWORDS",
    "get_scene_by_id",
    "get_scene_transition",
    "get_default_exploration_scene",
    "get_all_scene_names",
    "build_scene_context_for_prompt",
]

"""Compatibility imports: authored scenes live in content/builtin.json."""
from ..scene import (
    InteractiveElement, SceneData, VILLAGE_SQUARE_SCENE, TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE, COMBAT_ENCOUNTER_SCENE, SCENE_REGISTRY,
    SCENE_TRANSITION_KEYWORDS, get_scene_by_id, get_scene_transition,
    get_default_exploration_scene, get_all_scene_names, build_scene_context_for_prompt,
)

"""Scene action handlers for interactive elements.

This module manages scene-specific interactive actions that trigger skill checks.
"""

from .scene_interaction import (
    SceneInteractionRequest,
    SceneInteractionResult,
    find_interactive_element,
    handle_scene_interaction,
    is_scene_interaction_action,
)

__all__ = [
    "SceneInteractionRequest",
    "SceneInteractionResult",
    "find_interactive_element",
    "handle_scene_interaction",
    "is_scene_interaction_action",
]

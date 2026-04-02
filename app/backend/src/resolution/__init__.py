"""Resolution system for scene interactions and skill checks.

This module provides specialized resolution logic for scene-based interactions,
extending the core resolution engine with scene-specific functionality.
"""

from .scene_resolver import (
    SceneCheckResult,
    resolve_scene_skill_check,
)

__all__ = [
    "SceneCheckResult",
    "resolve_scene_skill_check",
]

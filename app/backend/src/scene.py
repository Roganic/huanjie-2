"""Scene content system for exploration phase.

This module manages scene data, scene switching, and scene-related utilities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .models.state import NPC, NPCType, SceneExit
from .scenes.data import (
    VILLAGE_SQUARE_SCENE as DATA_VILLAGE_SQUARE,
    TAVERN_SCENE as DATA_TAVERN,
    DUNGEON_ENTRANCE_SCENE as DATA_DUNGEON_ENTRANCE,
    COMBAT_ENCOUNTER_SCENE as DATA_COMBAT_ENCOUNTER,
)


class SceneData(BaseModel):
    """Complete scene data including NPCs and available actions.
    
    This extends the base Scene model with NPC information and
    action hints for narrative generation.
    """
    id: str
    name: str
    description: str
    actors: list[str] = Field(default_factory=list, description="Actor IDs present")
    npcs: list[NPC] = Field(default_factory=list, description="NPCs present in this scene")
    time: int = Field(default=0, description="Abstract time ticks elapsed")
    flags: list[str] = Field(default_factory=list, description="Mutable scene state flags")
    available_actions: list[str] = Field(
        default_factory=list,
        description="Suggested actions for this scene"
    )
    connected_scenes: list[str] = Field(
        default_factory=list,
        description="IDs of scenes connected to this one"
    )
    exits: list[SceneExit] = Field(
        default_factory=list,
        description="Available exits from this scene with direction names"
    )
    
    model_config = {"populate_by_name": True}
    
    def to_scene_dict(self) -> dict:
        """Convert to dict compatible with Scene model (without npcs list)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "actors": self.actors,
            "time": self.time,
            "flags": self.flags,
        }
    
    def get_npc_ids(self) -> list[str]:
        """Get list of NPC IDs in this scene."""
        return [npc.id for npc in self.npcs]
    
    def get_friendly_npcs(self) -> list[NPC]:
        """Get friendly NPCs in this scene."""
        return [npc for npc in self.npcs if npc.type == NPCType.FRIENDLY]
    
    def get_hostile_npcs(self) -> list[NPC]:
        """Get hostile NPCs in this scene."""
        return [npc for npc in self.npcs if npc.type == NPCType.HOSTILE]


# -----------------------------------------------------------------------------
# Pre-defined Scenes
# -----------------------------------------------------------------------------

# Re-export scenes from scenes.data to maintain a single source of truth
VILLAGE_SQUARE_SCENE = DATA_VILLAGE_SQUARE
TAVERN_SCENE = DATA_TAVERN
DUNGEON_ENTRANCE_SCENE = DATA_DUNGEON_ENTRANCE
COMBAT_ENCOUNTER_SCENE = DATA_COMBAT_ENCOUNTER

# Scene registry and utilities from scenes.data (single source of truth)
from .scenes.data import (
    SCENE_REGISTRY,
    SCENE_TRANSITION_KEYWORDS,
    get_scene_by_id,
    get_scene_transition,
    get_default_exploration_scene,
    get_all_scene_names,
)


def build_scene_context_for_prompt(scene: SceneData) -> str:
    """Build scene context string for narrative generation prompts.
    
    This provides the GM agent with scene information to generate
    contextually appropriate narration.
    
    Args:
        scene: The current scene data
        
    Returns:
        Formatted scene context string
    """
    lines = [
        f"当前场景: {scene.name}",
        f"场景描述: {scene.description}",
        "",
    ]
    
    if scene.npcs:
        lines.append("场景中的NPC:")
        for npc in scene.npcs:
            type_label = {
                NPCType.FRIENDLY: "[友好]",
                NPCType.NEUTRAL: "[中立]",
                NPCType.HOSTILE: "[敌对]",
            }.get(npc.type, "[未知]")
            lines.append(f"  - {npc.name} {type_label}: {npc.description}")
        lines.append("")
    
    if scene.available_actions:
        lines.append("可能的行动:")
        for action in scene.available_actions[:5]:  # Limit to 5 suggestions
            lines.append(f"  - {action}")
    
    return "\n".join(lines)

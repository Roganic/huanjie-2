"""Scene content system for exploration phase.

This module manages scene data, scene switching, and scene-related utilities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .models.state import NPC, NPCType, SceneExit, InventoryItem


from .content.schema import InteractionDefinition as InteractiveElement


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
    interactive_elements: list[InteractiveElement] = Field(default_factory=list)
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
    loot_items: list[InventoryItem] = Field(
        default_factory=list,
        description="Items available to pick up in this scene"
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
# All authored content lives in the versioned module pack.
from .content.store import builtin


def get_scene_by_id(scene_id: str, pack=None) -> Optional[SceneData]:
    pack = pack or builtin()
    definition = pack.scenes.get(scene_id)
    if definition is None:
        return None
    npcs = [NPC(**pack.characters[id].model_dump(exclude={"hp", "ac", "abilities", "weapon_id", "dialogue", "clue", "alive"})) for id in definition.character_ids]
    return SceneData(id=definition.id, name=definition.name, description=definition.description,
                     interactive_elements=definition.interactions,
                     npcs=npcs, exits=[SceneExit(**e.model_dump()) for e in definition.exits],
                     loot_items=[pack.items[id].model_copy(deep=True) for id in definition.item_ids],
                     connected_scenes=[e.target_scene_id for e in definition.exits])


# Read-only compatibility projections for previous import paths.
SCENE_REGISTRY = {id: get_scene_by_id(id) for id in builtin().scenes}
VILLAGE_SQUARE_SCENE = SCENE_REGISTRY["village-square-01"]
TAVERN_SCENE = SCENE_REGISTRY["tavern-01"]
DUNGEON_ENTRANCE_SCENE = SCENE_REGISTRY["dungeon-entrance-01"]
COMBAT_ENCOUNTER_SCENE = SCENE_REGISTRY["combat-encounter-01"]
SCENE_TRANSITION_KEYWORDS = {alias: id for id, scene in builtin().scenes.items() for alias in [scene.name, *scene.aliases]}


def get_scene_transition(intent: str) -> Optional[str]:
    """Check if intent contains scene transition keywords.
    
    Args:
        intent: The player's action intent
        
    Returns:
        Target scene ID if transition keyword found, None otherwise
    """
    intent_lower = intent.lower()
    for keyword, scene_id in SCENE_TRANSITION_KEYWORDS.items():
        if keyword in intent_lower:
            return scene_id
    return None


def get_default_exploration_scene() -> SceneData:
    """Get the default starting exploration scene."""
    return get_scene_by_id(builtin().starting_scene_id)


def get_all_scene_names() -> dict[str, str]:
    """Get mapping of scene IDs to names for display."""
    return {scene_id: scene.name for scene_id, scene in SCENE_REGISTRY.items()}


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

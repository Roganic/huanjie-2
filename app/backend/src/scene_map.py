"""Scene map system for multi-scene exploration.

This module manages the scene graph, including exits, encounters, and navigation.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

from .models.state import NPC, NPCType, SceneExit


@dataclass
class SceneExitInfo:
    """Information about a scene exit."""
    direction: str  # e.g., "north", "south", "酒馆", "地下城"
    target_scene_id: str
    description: Optional[str] = None  # Optional flavor text for the exit


@dataclass
class EncounterConfig:
    """Configuration for random encounters in a scene."""
    encounter_rate: float = 0.0  # 0.0 to 1.0 probability
    possible_encounters: list[str] = field(default_factory=list)  # Enemy IDs that can be encountered
    encounter_description: str = "你遭遇了敌人！"


@dataclass
class SceneMapNode:
    """A node in the scene map representing a navigable location."""
    scene_id: str
    name: str
    description: str
    exits: list[SceneExitInfo] = field(default_factory=list)
    encounter_config: EncounterConfig = field(default_factory=lambda: EncounterConfig())
    npcs: list[NPC] = field(default_factory=list)
    available_actions: list[str] = field(default_factory=list)

    def get_exit_directions(self) -> list[str]:
        """Get all available exit directions."""
        return [exit_info.direction for exit_info in self.exits]

    def get_exit_by_direction(self, direction: str) -> Optional[SceneExitInfo]:
        """Get exit info for a specific direction."""
        direction_lower = direction.lower()
        for exit_info in self.exits:
            if exit_info.direction.lower() == direction_lower:
                return exit_info
        return None

    def get_exit_by_keyword(self, keyword: str) -> Optional[SceneExitInfo]:
        """Get exit info by matching keyword in direction."""
        keyword_lower = keyword.lower()
        for exit_info in self.exits:
            if keyword_lower in exit_info.direction.lower():
                return exit_info
        return None

    def should_trigger_encounter(self) -> bool:
        """Check if moving from this scene should trigger a random encounter."""
        if not self.encounter_config.possible_encounters:
            return False
        return random.random() < self.encounter_config.encounter_rate

    def get_random_encounter(self) -> Optional[str]:
        """Get a random enemy ID for an encounter."""
        if not self.encounter_config.possible_encounters:
            return None
        return random.choice(self.encounter_config.possible_encounters)

    def to_scene_exit_list(self) -> list[SceneExit]:
        """Convert exits to SceneExit model list."""
        return [
            SceneExit(direction=exit_info.direction, target_scene_id=exit_info.target_scene_id)
            for exit_info in self.exits
        ]


# -----------------------------------------------------------------------------
# Compatibility topology views generated from the same content pack as scenes.
from .content.store import builtin


def nodes_for(pack=None):
    pack = pack or builtin()
    from .scene import get_scene_by_id
    result = {}
    for id, definition in pack.scenes.items():
        scene = get_scene_by_id(id, pack)
        enemies = [n.id for n in scene.npcs if n.type == NPCType.HOSTILE]
        result[id] = SceneMapNode(scene_id=id, name=scene.name, description=scene.description,
            exits=[SceneExitInfo(**e.model_dump()) for e in definition.exits], npcs=scene.npcs,
            encounter_config=EncounterConfig(encounter_rate=1.0 if enemies else 0.0, possible_encounters=enemies))
    return result


SCENE_MAP = nodes_for()
VILLAGE_SQUARE_NODE = SCENE_MAP["village-square-01"]
TAVERN_NODE = SCENE_MAP["tavern-01"]
DUNGEON_ENTRANCE_NODE = SCENE_MAP["dungeon-entrance-01"]
COMBAT_ENCOUNTER_NODE = SCENE_MAP["combat-encounter-01"]
FOREST_PATH_NODE = SCENE_MAP["forest-path-01"]
ANCIENT_TEMPLE_NODE = SCENE_MAP["ancient-temple-01"]
VAULT_NODE = SCENE_MAP["vault-01"]

# Direction aliases for natural language parsing
DIRECTION_ALIASES: dict[str, list[str]] = {
    "north": ["北", "向北", "向北走", "往北", "去北", "north", "n"],
    "south": ["南", "向南", "向南走", "往南", "去南", "south", "s"],
    "east": ["东", "向东", "向东走", "往东", "去东", "east", "e"],
    "west": ["西", "向西", "向西走", "往西", "去西", "west", "w"],
    "up": ["上", "向上", "上去", "up", "u"],
    "down": ["下", "向下", "下去", "down", "d"],
}

# Scene name to ID mapping for natural language navigation
def aliases_for(pack=None):
    return {alias: id for id, scene in (pack or builtin()).scenes.items() for alias in [scene.name, *scene.aliases]}

SCENE_NAME_ALIASES = aliases_for()


def get_scene_node(scene_id: str, pack=None) -> Optional[SceneMapNode]:
    """Get scene node by ID."""
    return (nodes_for(pack) if pack else SCENE_MAP).get(scene_id)


def get_default_scene_node() -> SceneMapNode:
    """Get the default starting scene node."""
    return VILLAGE_SQUARE_NODE


def get_default_exploration_scene() -> SceneMapNode:
    """Get the default starting exploration scene (alias for get_default_scene_node)."""
    return get_default_scene_node()


def resolve_direction(direction: str) -> Optional[str]:
    """Resolve a direction string to canonical direction.
    
    Args:
        direction: User input direction (e.g., "向北", "north", "n")
        
    Returns:
        Canonical direction (north, south, east, west, up, down) or None
    """
    direction_lower = direction.lower().strip()
    
    for canonical, aliases in DIRECTION_ALIASES.items():
        if direction_lower in [a.lower() for a in aliases]:
            return canonical
    return None


def resolve_scene_by_name(name: str, pack=None) -> Optional[str]:
    """Resolve a scene name/alias to scene ID.
    
    Args:
        name: Scene name or alias (e.g., "酒馆", "tavern")
        
    Returns:
        Scene ID or None if not found
    """
    name_lower = name.lower().strip()
    
    if not name_lower:
        return None
    # Direct ID match
    if name in (pack or builtin()).scenes:
        return name
    
    # Alias match
    for alias, scene_id in sorted(aliases_for(pack).items(), key=lambda pair: -len(pair[0])):
        if alias.lower() in name_lower:
            return scene_id
    
    return None


def parse_movement_intent(intent: str, pack=None) -> tuple[Optional[str], Optional[str]]:
    """Parse a movement intent to determine target scene.
    
    Args:
        intent: User's movement intent (e.g., "向北走", "去酒馆")
        
    Returns:
        Tuple of (target_scene_id, direction_or_name)
        - target_scene_id: The scene ID to move to, or None if not parseable
        - direction_or_name: The direction or scene name used, or None
    """
    intent_lower = intent.lower().strip()
    
    # First, try to resolve the full intent as a direction
    direction = resolve_direction(intent_lower)
    if direction:
        return None, direction
    
    # Try to resolve as scene name first (before stripping prefixes)
    scene_id = resolve_scene_by_name(intent_lower, pack)
    if scene_id:
        return scene_id, intent_lower
    
    # Movement keywords to strip - order matters (longer prefixes first)
    movement_prefixes = ["前往", "走向", "进入", "去", "到", "go to", "move to", "head to", "go", "move", "enter", "walk to", "walk"]
    
    # Remove movement prefixes
    cleaned = intent_lower
    for prefix in movement_prefixes:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    
    # Try to resolve as direction again after stripping prefix
    direction = resolve_direction(cleaned)
    if direction:
        return None, direction
    
    # Try to resolve as scene name
    scene_id = resolve_scene_by_name(cleaned, pack)
    if scene_id:
        return scene_id, cleaned
    
    # Check for partial matches in the intent for scene names
    for alias, scene_id in sorted(aliases_for(pack).items(), key=lambda pair: -len(pair[0])):
        if alias.lower() in intent_lower:
            return scene_id, alias
    
    return None, None


def get_connected_scene(current_scene_id: str, direction: str, pack=None) -> Optional[str]:
    """Get the scene ID connected to current scene in given direction.
    
    Args:
        current_scene_id: Current scene ID
        direction: Direction to move (canonical or alias)
        
    Returns:
        Target scene ID or None if no exit in that direction
    """
    node = get_scene_node(current_scene_id, pack)
    if not node:
        return None
    
    # Try canonical direction first
    canonical = resolve_direction(direction)
    if canonical:
        exit_info = node.get_exit_by_direction(canonical)
        if exit_info:
            return exit_info.target_scene_id
    
    # Try direct match
    exit_info = node.get_exit_by_direction(direction)
    if exit_info:
        return exit_info.target_scene_id
    
    # Try keyword match
    exit_info = node.get_exit_by_keyword(direction)
    if exit_info:
        return exit_info.target_scene_id
    
    return None


def check_encounter_on_move(from_scene_id: str, to_scene_id: str) -> tuple[bool, Optional[str]]:
    """Check if an encounter should trigger when moving between scenes.
    
    Args:
        from_scene_id: Scene being left
        to_scene_id: Scene being entered
        
    Returns:
        Tuple of (should_trigger_encounter, enemy_id)
    """
    # Use the encounter rate of the destination scene
    node = get_scene_node(to_scene_id)
    if not node:
        return False, None
    
    if node.should_trigger_encounter():
        return True, node.get_random_encounter()
    
    return False, None

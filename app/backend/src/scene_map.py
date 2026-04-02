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
# Scene Map Definitions
# -----------------------------------------------------------------------------

# Scene 1: Village Square
VILLAGE_SQUARE_NODE = SceneMapNode(
    scene_id="village-square-01",
    name="十字路口村庄广场",
    description=(
        "村庄的中心广场，几座破旧但整洁的房屋环绕着一口古老的水井。"
        "清晨的阳光洒在鹅卵石铺就的地面上，几个村民正在忙碌地准备着新的一天。"
        "铁匠铺传来叮叮当当的敲打声，杂货店老板正在门前整理货物。"
    ),
    exits=[
        SceneExitInfo(direction="north", target_scene_id="tavern-01", description="通往酒馆的小路"),
        SceneExitInfo(direction="east", target_scene_id="dungeon-entrance-01", description="通向森林的小路"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.1,  # 10% chance
        possible_encounters=["goblin-01"],
        encounter_description="从阴影中窜出一只哥布林！"
    ),
    npcs=[
        NPC(id="village-elder-01", name="村长托马斯", type=NPCType.FRIENDLY,
            description="白发苍苍的村庄长老，对本地的历史和附近的危险了如指掌。",
            race="人类", occupation="村长"),
        NPC(id="blacksmith-01", name="铁匠格鲁姆", type=NPCType.FRIENDLY,
            description="身材魁梧的矮人铁匠，正在铁匠铺里忙碌地打造农具。",
            race="矮人", occupation="铁匠"),
        NPC(id="merchant-02", name="杂货商莉莉", type=NPCType.NEUTRAL,
            description="精明的半精灵商人，出售各种冒险必需品。",
            race="半精灵", occupation="商人"),
    ],
    available_actions=[
        "与村长托马斯交谈",
        "去铁匠铺找格鲁姆",
        "在杂货店购买补给",
        "向北前往酒馆",
        "向东前往森林入口",
    ],
)

# Scene 2: The Tavern
TAVERN_NODE = SceneMapNode(
    scene_id="tavern-01",
    name="锈迹斑斑的灯笼酒馆",
    description=(
        "十字路口村庄的一家昏暗酒馆。陈年麦酒的气味混合着木柴烟雾。"
        "几个当地人默默地喝着酒，角落里传来轻柔的竖琴声。"
        "酒保老马库斯在吧台后面擦拭着酒杯，不时用独眼打量着客人。"
    ),
    exits=[
        SceneExitInfo(direction="south", target_scene_id="village-square-01", description="返回村庄广场"),
        SceneExitInfo(direction="east", target_scene_id="dungeon-entrance-01", description="通往森林的小路"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.0,  # Safe zone - no encounters
        possible_encounters=[],
        encounter_description=""
    ),
    npcs=[
        NPC(id="tavern-keeper-01", name="老马库斯", type=NPCType.FRIENDLY,
            description="灯笼酒馆的老板，一位白发苍苍的老兵，瞎了一只眼但笑容温暖。",
            race="人类", occupation="酒馆老板"),
        NPC(id="tavern-bard-01", name="银弦艾拉", type=NPCType.NEUTRAL,
            description="在角落演奏竖琴的吟游诗人，据说知道很多古老传说。",
            race="精灵", occupation="吟游诗人"),
        NPC(id="merchant-01", name="戴兜帽的商人", type=NPCType.NEUTRAL,
            description="独自坐在阴影中的神秘商人，时不时打量着进出的客人。",
            race="未知", occupation="商人"),
    ],
    available_actions=[
        "与老马库斯交谈",
        "聆听银弦艾拉的演奏",
        "接近神秘的商人",
        "向南返回村庄广场",
        "向东前往森林入口",
    ],
)

# Scene 3: Dungeon Entrance
DUNGEON_ENTRANCE_NODE = SceneMapNode(
    scene_id="dungeon-entrance-01",
    name="遗忘地下城入口",
    description=(
        "一座古老的石门半埋在藤蔓之中，门上刻满了风化的符文。"
        "入口旁躺着一具石像守卫的残骸，似乎经历过激烈的战斗。"
        "不远处，一个受伤的矮人靠在树干上，神情惊恐地看着地下城的方向。"
    ),
    exits=[
        SceneExitInfo(direction="west", target_scene_id="village-square-01", description="返回村庄广场"),
        SceneExitInfo(direction="west", target_scene_id="tavern-01", description="返回酒馆"),
        SceneExitInfo(direction="down", target_scene_id="vault-01", description="进入地下城宝库"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.3,  # 30% chance - dangerous area
        possible_encounters=["goblin-01", "goblin-shaman-01", "wolf-01"],
        encounter_description="敌人从阴影中出现！"
    ),
    npcs=[
        NPC(id="wounded-adventurer-01", name="托尔金", type=NPCType.FRIENDLY,
            description="从地下城逃出来的受伤冒险者，神情惊恐。",
            race="矮人", occupation="冒险者"),
        NPC(id="guard-corpse-01", name="死去的守卫", type=NPCType.NEUTRAL,
            description="倒在地下城入口旁的石像守卫，身上布满了战斗的痕迹。",
            race="构造体", occupation="守卫"),
    ],
    available_actions=[
        "与受伤的托尔金交谈",
        "检查死去的守卫尸体",
        "检查石门上的符文",
        "向西返回村庄",
        "向下进入宝库",
    ],
)

# Scene 4: The Vault (treasure room)
VAULT_NODE = SceneMapNode(
    scene_id="vault-01",
    name="古老宝库",
    description=(
        "地下深处的一间石室，墙壁上镶嵌着发出微光的水晶。"
        "中央的石台上放着一个古老的宝箱，周围散落着一些金币和珠宝。"
        "空气中弥漫着古老魔法的气息，让人既兴奋又警惕。"
    ),
    exits=[
        SceneExitInfo(direction="up", target_scene_id="dungeon-entrance-01", description="返回地下城入口"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.5,  # 50% chance - very dangerous
        possible_encounters=["goblin-shaman-01", "wolf-01"],
        encounter_description="守护宝库的敌人出现了！"
    ),
    npcs=[
        NPC(id="treasure-guardian-01", name="宝箱守护者", type=NPCType.HOSTILE,
            description="守护着宝箱的魔法构造体，虽然已经残破但仍然危险。",
            race="构造体", occupation="守护者"),
    ],
    available_actions=[
        "打开宝箱",
        "搜索周围的金币",
        "检查墙壁上的水晶",
        "向上返回地下城入口",
    ],
)

# Scene Map Registry
SCENE_MAP: dict[str, SceneMapNode] = {
    VILLAGE_SQUARE_NODE.scene_id: VILLAGE_SQUARE_NODE,
    TAVERN_NODE.scene_id: TAVERN_NODE,
    DUNGEON_ENTRANCE_NODE.scene_id: DUNGEON_ENTRANCE_NODE,
    VAULT_NODE.scene_id: VAULT_NODE,
}

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
SCENE_NAME_ALIASES: dict[str, str] = {
    # Village square aliases
    "村庄广场": "village-square-01",
    "广场": "village-square-01",
    "村庄": "village-square-01",
    "村里": "village-square-01",
    "village square": "village-square-01",
    "square": "village-square-01",
    
    # Tavern aliases
    "酒馆": "tavern-01",
    "灯笼酒馆": "tavern-01",
    "tavern": "tavern-01",
    
    # Dungeon entrance aliases
    "地下城入口": "dungeon-entrance-01",
    "森林入口": "dungeon-entrance-01",
    "入口": "dungeon-entrance-01",
    "石门": "dungeon-entrance-01",
    "森林": "dungeon-entrance-01",
    "dungeon entrance": "dungeon-entrance-01",
    "dungeon": "dungeon-entrance-01",
    
    # Vault aliases
    "宝库": "vault-01",
    "地下城": "vault-01",
    "vault": "vault-01",
    "treasure room": "vault-01",
}


def get_scene_node(scene_id: str) -> Optional[SceneMapNode]:
    """Get scene node by ID."""
    return SCENE_MAP.get(scene_id)


def get_default_scene_node() -> SceneMapNode:
    """Get the default starting scene node."""
    return VILLAGE_SQUARE_NODE


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


def resolve_scene_by_name(name: str) -> Optional[str]:
    """Resolve a scene name/alias to scene ID.
    
    Args:
        name: Scene name or alias (e.g., "酒馆", "tavern")
        
    Returns:
        Scene ID or None if not found
    """
    name_lower = name.lower().strip()
    
    # Direct ID match
    if name_lower in SCENE_MAP:
        return name_lower
    
    # Alias match
    for alias, scene_id in SCENE_NAME_ALIASES.items():
        if alias.lower() in name_lower or name_lower in alias.lower():
            return scene_id
    
    return None


def parse_movement_intent(intent: str) -> tuple[Optional[str], Optional[str]]:
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
    scene_id = resolve_scene_by_name(intent_lower)
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
    scene_id = resolve_scene_by_name(cleaned)
    if scene_id:
        return scene_id, cleaned
    
    # Check for partial matches in the intent for scene names
    for alias, scene_id in SCENE_NAME_ALIASES.items():
        if alias.lower() in intent_lower:
            return scene_id, alias
    
    return None, None


def get_connected_scene(current_scene_id: str, direction: str) -> Optional[str]:
    """Get the scene ID connected to current scene in given direction.
    
    Args:
        current_scene_id: Current scene ID
        direction: Direction to move (canonical or alias)
        
    Returns:
        Target scene ID or None if no exit in that direction
    """
    node = get_scene_node(current_scene_id)
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

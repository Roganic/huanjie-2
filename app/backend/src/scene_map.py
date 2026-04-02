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
        SceneExitInfo(direction="east", target_scene_id="dungeon-entrance-01", description="通向地下城的小路"),
        SceneExitInfo(direction="south", target_scene_id="forest-path-01", description="通往幽暗森林的小径"),
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
        "向西可以返回村庄，向下则进入危险的地下宝库，向南通往古庙废墟。"
    ),
    exits=[
        SceneExitInfo(direction="west", target_scene_id="village-square-01", description="返回村庄广场"),
        SceneExitInfo(direction="down", target_scene_id="vault-01", description="进入地下城宝库"),
        SceneExitInfo(direction="south", target_scene_id="ancient-temple-01", description="前往古庙废墟"),
        SceneExitInfo(direction="north", target_scene_id="combat-encounter-01", description="进入地下城通道"),
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
        "向南前往古庙废墟",
        "向北进入地下城通道",
    ],
)

# Scene 4: Combat Encounter (goblin patrol in dungeon corridor)
COMBAT_ENCOUNTER_NODE = SceneMapNode(
    scene_id="combat-encounter-01",
    name="地下城通道",
    description=(
        "狭窄的地下通道，墙壁上长满了发光的苔藓，提供微弱的照明。"
        "前方传来沙沙声和低沉的念诵声。"
        "几只哥布林从阴影中窜出，挡住了去路，其中一只头戴骨饰，似乎是个施法者。"
    ),
    exits=[
        SceneExitInfo(direction="south", target_scene_id="dungeon-entrance-01", description="返回地下城入口"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.8,  # 80% chance - combat zone
        possible_encounters=["goblin-01", "goblin-shaman-01", "wolf-01"],
        encounter_description="哥布林们发现了你！"
    ),
    npcs=[
        NPC(id="goblin-01", name="哥布林斥候", type=NPCType.HOSTILE,
            description="一只瘦小的哥布林，手持锈迹斑斑的匕首，眼中闪烁着贪婪的光芒。",
            race="哥布林", occupation="斥候"),
        NPC(id="goblin-shaman-01", name="哥布林萨满", type=NPCType.HOSTILE,
            description="头戴骨饰的哥布林施法者，正在低声念诵某种咒语。",
            race="哥布林", occupation="萨满"),
        NPC(id="wolf-01", name="座狼", type=NPCType.HOSTILE,
            description="一只体型巨大的灰狼，獠牙外露，口水滴落在地上。",
            race="野兽", occupation="战斗伙伴"),
    ],
    available_actions=[
        "与哥布林战斗",
        "尝试与哥布林谈判",
        "悄悄后退，返回入口",
        "利用通道的狭窄地形",
    ],
)

# Scene 5: Forest Path (branch path from village square)
FOREST_PATH_NODE = SceneMapNode(
    scene_id="forest-path-01",
    name="幽暗森林小径",
    description=(
        "一条蜿蜒穿过古老森林的小径，参天大树遮蔽了大部分阳光，只有零星的光束穿透树冠。"
        "空气中弥漫着潮湿泥土和松针的气息，远处偶尔传来不明生物的叫声。"
        "小径两侧长满了各种草药植物，一个经验丰富的采集者也许能找到有价值的东西。"
    ),
    exits=[
        SceneExitInfo(direction="north", target_scene_id="village-square-01", description="返回村庄广场"),
        SceneExitInfo(direction="east", target_scene_id="ancient-temple-01", description="前往古庙废墟"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.2,  # 20% chance - light danger
        possible_encounters=["wolf-01"],
        encounter_description="一只野狼从树丛中冲出！"
    ),
    npcs=[
        NPC(id="forest-hermit-01", name="隐士阿德里安", type=NPCType.FRIENDLY,
            description="住在森林中的老隐士，精通草药知识，对森林中的秘密了如指掌。",
            race="人类", occupation="隐士"),
        NPC(id="forest-wolf-01", name="野狼", type=NPCType.HOSTILE,
            description="一只在森林中游荡的野狼，正在警惕地打量着入侵者。",
            race="野兽", occupation="野生动物"),
    ],
    available_actions=[
        "与隐士阿德里安交谈",
        "搜索草药",
        "观察野狼的动向",
        "向北返回村庄广场",
        "向东前往古庙废墟",
    ],
)

# Scene 6: Ancient Temple Ruins (with skeleton combat and altar interaction)
ANCIENT_TEMPLE_NODE = SceneMapNode(
    scene_id="ancient-temple-01",
    name="古庙废墟",
    description=(
        "一座被岁月侵蚀的古老神庙，大部分屋顶已经坍塌，只剩下几根粗大的石柱矗立着。"
        "地面上散落着破碎的祭坛碎片和风化的石像。"
        "神庙深处隐约可见一个发光的祭坛，散发出神秘的蓝色光芒。"
    ),
    exits=[
        SceneExitInfo(direction="west", target_scene_id="forest-path-01", description="返回森林小径"),
        SceneExitInfo(direction="north", target_scene_id="dungeon-entrance-01", description="前往地下城入口"),
        SceneExitInfo(direction="down", target_scene_id="vault-01", description="进入地下宝库"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.6,  # 60% chance - undead patrol
        possible_encounters=["skeleton-warrior-01", "skeleton-archer-01"],
        encounter_description="骷髅守卫向你发起攻击！"
    ),
    npcs=[
        NPC(id="skeleton-warrior-01", name="骷髅战士", type=NPCType.HOSTILE,
            description="一具披着锈蚀铠甲的骷髅，手持断剑，眼眶中燃烧着幽蓝色的鬼火。",
            race="亡灵", occupation="守卫"),
        NPC(id="skeleton-archer-01", name="骷髅弓手", type=NPCType.HOSTILE,
            description="一具骷髅弓手，手持腐朽的弓，正在废墟高处巡逻。",
            race="亡灵", occupation="弓手"),
        NPC(id="ghost-priest-01", name="幽灵祭司", type=NPCType.NEUTRAL,
            description="一个半透明的幽灵，穿着古代祭司的服装，神情悲伤地飘荡在神庙中。",
            race="亡灵", occupation="祭司"),
    ],
    available_actions=[
        "与骷髅战士战斗",
        "尝试与幽灵祭司交谈",
        "检查发光的祭坛",
        "向西返回森林小径",
        "向北前往地下城入口",
        "向下进入地下宝库",
    ],
)

# Scene 7: The Vault (treasure room - with chest event)
VAULT_NODE = SceneMapNode(
    scene_id="vault-01",
    name="古老宝库",
    description=(
        "地下深处的一间石室，墙壁上镶嵌着发出微光的水晶，照亮了整个空间。"
        "中央的石台上放着一个古老的宝箱，铁锁已经锈迹斑斑，周围散落着一些金币和珠宝碎片。"
        "空气中弥漫着古老魔法的气息，让人既兴奋又警惕。"
    ),
    exits=[
        SceneExitInfo(direction="up", target_scene_id="dungeon-entrance-01", description="返回地下城入口"),
        SceneExitInfo(direction="north", target_scene_id="ancient-temple-01", description="返回古庙废墟"),
    ],
    encounter_config=EncounterConfig(
        encounter_rate=0.5,  # 50% chance - very dangerous
        possible_encounters=["goblin-shaman-01", "wolf-01"],
        encounter_description="守护宝库的敌人出现了！"
    ),
    npcs=[
        NPC(id="treasure-guardian-01", name="宝库守护傀儡", type=NPCType.HOSTILE,
            description="守护着宝箱的魔法构造体，虽然已经残破但仍然危险。",
            race="构造体", occupation="守护者"),
    ],
    available_actions=[
        "搜索宝箱",
        "检查骷髅手中的钥匙",
        "搜索散落的金币",
        "与宝库守护傀儡战斗",
        "向上返回地下城入口",
        "向北返回古庙废墟",
    ],
)

# Scene Map Registry
SCENE_MAP: dict[str, SceneMapNode] = {
    VILLAGE_SQUARE_NODE.scene_id: VILLAGE_SQUARE_NODE,
    TAVERN_NODE.scene_id: TAVERN_NODE,
    DUNGEON_ENTRANCE_NODE.scene_id: DUNGEON_ENTRANCE_NODE,
    COMBAT_ENCOUNTER_NODE.scene_id: COMBAT_ENCOUNTER_NODE,
    FOREST_PATH_NODE.scene_id: FOREST_PATH_NODE,
    ANCIENT_TEMPLE_NODE.scene_id: ANCIENT_TEMPLE_NODE,
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
    "地下宝库": "vault-01",
    "古老宝库": "vault-01",
    "vault": "vault-01",
    "treasure room": "vault-01",

    # Combat encounter aliases
    "地下城通道": "combat-encounter-01",
    "通道": "combat-encounter-01",
    "combat encounter": "combat-encounter-01",

    # Forest path aliases
    "幽暗森林小径": "forest-path-01",
    "森林小径": "forest-path-01",
    "幽暗森林": "forest-path-01",
    "小径": "forest-path-01",
    "forest path": "forest-path-01",

    # Ancient temple aliases
    "古庙废墟": "ancient-temple-01",
    "古庙": "ancient-temple-01",
    "神庙": "ancient-temple-01",
    "废墟": "ancient-temple-01",
    "ancient temple": "ancient-temple-01",
    "temple": "ancient-temple-01",
}


def get_scene_node(scene_id: str) -> Optional[SceneMapNode]:
    """Get scene node by ID."""
    return SCENE_MAP.get(scene_id)


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

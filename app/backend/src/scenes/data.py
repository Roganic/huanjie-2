"""Scene data definitions.

This module contains all preset scene definitions and scene-related utilities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..models.state import NPC, NPCType, SceneExit, InventoryItem


class InteractiveElement(BaseModel):
    """Interactive element in a scene that can trigger skill checks."""
    id: str
    name: str
    action_name: str
    skill: str
    dc: int = 10
    success_narrative: str = ""
    failure_narrative: str = ""
    reward_item: str | None = None
    reward_info: str | None = None


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
    loot_items: list[InventoryItem] = Field(
        default_factory=list,
        description="Items available to pick up in this scene"
    )
    interactive_elements: list[InteractiveElement] = Field(
        default_factory=list,
        description="Interactive elements in this scene"
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

# Scene 1: Village Square (new starting exploration scene)
VILLAGE_SQUARE_SCENE = SceneData(
    id="village-square-01",
    name="十字路口村庄广场",
    description=(
        "村庄的中心广场，几座破旧但整洁的房屋环绕着一口古老的水井。"
        "清晨的阳光洒在鹅卵石铺就的地面上，几个村民正在忙碌地准备着新的一天。"
        "铁匠铺传来叮叮当当的敲打声，杂货店老板正在门前整理货物。"
        "一条小路通向村外的森林，另一条则通往村中心的酒馆。"
    ),
    actors=[],
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
        "与村长托马斯交谈，打听消息",
        "去铁匠铺找格鲁姆修理装备",
        "在杂货店购买补给",
        "前往酒馆休息",
        "去地下城入口探险",
        "与村民交谈收集情报",
    ],
    connected_scenes=["tavern-01", "dungeon-entrance-01", "forest-path-01"],
    exits=[
        SceneExit(direction="酒馆", target_scene_id="tavern-01"),
        SceneExit(direction="地下城入口", target_scene_id="dungeon-entrance-01"),
        SceneExit(direction="森林小径", target_scene_id="forest-path-01"),
    ],
    loot_items=[
        InventoryItem(id="dagger", name="匕首", type="weapon", damage_dice="1d4", attack_ability="dex", description="一把锋利的匕首。"),
        InventoryItem(id="leather", name="皮甲", type="armor", base_ac=11, add_dex_modifier=True, description="轻便的皮革护甲。"),
    ],
)

# Scene 2: The Tavern (starting exploration scene)
TAVERN_SCENE = SceneData(
    id="tavern-01",
    name="锈迹斑斑的灯笼酒馆",
    description=(
        "十字路口村庄的一家昏暗酒馆。陈年麦酒的气味混合着木柴烟雾。"
        "几个当地人默默地喝着酒，角落里传来轻柔的竖琴声。"
        "酒保老马库斯在吧台后面擦拭着酒杯，不时用独眼打量着客人。"
    ),
    actors=[],
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
        "与老马库斯交谈，打听消息",
        "聆听银弦艾拉的演奏或询问传说",
        "接近神秘的商人",
        "离开酒馆，前往地下城入口",
        "在酒馆休息",
        "观察其他客人",
        "返回村庄广场",
    ],
    connected_scenes=["village-square-01", "dungeon-entrance-01"],
    exits=[
        SceneExit(direction="村庄广场", target_scene_id="village-square-01"),
        SceneExit(direction="森林入口", target_scene_id="dungeon-entrance-01"),
    ],
    loot_items=[
        InventoryItem(id="shortsword", name="短剑", type="weapon", damage_dice="1d6", attack_ability="dex", description="一把轻便的短剑。"),
        InventoryItem(id="robe", name="布袍", type="armor", base_ac=10, add_dex_modifier=True, description="普通的布制长袍。"),
    ],
)

# Scene 3: Dungeon Entrance
DUNGEON_ENTRANCE_SCENE = SceneData(
    id="dungeon-entrance-01",
    name="遗忘地下城入口",
    description=(
        "一座古老的石门半埋在藤蔓之中，门上刻满了风化的符文。"
        "入口旁躺着一具石像守卫的残骸，似乎经历过激烈的战斗。"
        "不远处，一个受伤的矮人靠在树干上，神情惊恐地看着地下城的方向。"
        "阴冷的风从黑暗中吹出，带来腐朽和某种更危险的气息。"
    ),
    actors=[],
    npcs=[
        NPC(id="wounded-adventurer-01", name="托尔金", type=NPCType.FRIENDLY,
            description="从地下城逃出来的受伤冒险者，神情惊恐。",
            race="矮人", occupation="冒险者"),
        NPC(id="guard-corpse-01", name="死去的守卫", type=NPCType.NEUTRAL,
            description="倒在地下城入口旁的石像守卫，身上布满了战斗的痕迹。",
            race="构造体", occupation="守卫"),
    ],
    available_actions=[
        "与受伤的托尔金交谈，了解情况",
        "检查死去的守卫尸体",
        "检查石门上的符文",
        "进入地下城",
        "返回酒馆",
        "返回村庄广场",
        "在入口处搜索线索",
    ],
    connected_scenes=["village-square-01", "tavern-01", "combat-encounter-01", "ancient-temple-01", "vault-01"],
    exits=[
        SceneExit(direction="村庄广场", target_scene_id="village-square-01"),
        SceneExit(direction="酒馆", target_scene_id="tavern-01"),
        SceneExit(direction="地下城通道", target_scene_id="combat-encounter-01"),
        SceneExit(direction="古庙废墟", target_scene_id="ancient-temple-01"),
        SceneExit(direction="地下宝库", target_scene_id="vault-01"),
    ],
)

# Scene 4: Combat Encounter (used when combat triggers)
COMBAT_ENCOUNTER_SCENE = SceneData(
    id="combat-encounter-01",
    name="地下城通道",
    description=(
        "狭窄的地下通道，墙壁上长满了发光的苔藓，提供微弱的照明。"
        "前方传来沙沙声和低沉的念诵声。"
        "几只哥布林从阴影中窜出，挡住了去路，其中一只头戴骨饰，似乎是个施法者。"
        "一只体型巨大的座狼伴随在它们身边，獠牙外露。"
    ),
    actors=[],
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
        "悄悄后退，寻找其他路径",
        "利用环境优势",
    ],
    connected_scenes=["dungeon-entrance-01"],
    exits=[
        SceneExit(direction="地下城入口", target_scene_id="dungeon-entrance-01"),
    ],
)

# Scene 5: Forest Path (branch path from village square)
FOREST_PATH_SCENE = SceneData(
    id="forest-path-01",
    name="幽暗森林小径",
    description=(
        "一条蜿蜒穿过古老森林的小径，参天大树遮蔽了大部分阳光，只有零星的光束穿透树冠。"
        "空气中弥漫着潮湿泥土和松针的气息，远处偶尔传来不明生物的叫声。"
        "小径两侧长满了各种草药植物，一个经验丰富的采集者也许能找到有价值的东西。"
        "小径向前延伸通往古庙废墟，向后则回到村庄广场。"
    ),
    actors=[],
    npcs=[
        NPC(id="forest-hermit-01", name="隐士阿德里安", type=NPCType.FRIENDLY,
            description="住在森林中的老隐士，精通草药知识，对森林中的秘密了如指掌。",
            race="人类", occupation="隐士"),
        NPC(id="forest-wolf-01", name="野狼", type=NPCType.HOSTILE,
            description="一只在森林中游荡的野狼，正在警惕地打量着入侵者。",
            race="野兽", occupation="野生动物"),
    ],
    available_actions=[
        "与隐士阿德里安交谈，询问草药知识",
        "搜索草药（感知检定 DC 12）",
        "观察野狼的动向",
        "向前前往古庙废墟",
        "返回村庄广场",
    ],
    connected_scenes=["village-square-01", "ancient-temple-01"],
    exits=[
        SceneExit(direction="村庄广场", target_scene_id="village-square-01"),
        SceneExit(direction="古庙废墟", target_scene_id="ancient-temple-01"),
    ],
    interactive_elements=[
        InteractiveElement(
            id="herb-gathering-01",
            name="草药丛",
            action_name="搜索草药",
            skill="perception",
            dc=12,
            success_narrative="你仔细搜索了草药丛，找到了几株珍贵的治愈草！",
            failure_narrative="你翻遍了草丛，但只找到了一些普通的杂草，什么有用的都没有。",
            reward_item="healing_herb",
            reward_info="治愈草：可以恢复少量生命值",
        ),
    ],
)

# Scene 6: Ancient Temple Ruins (deep exploration with combat)
ANCIENT_TEMPLE_SCENE = SceneData(
    id="ancient-temple-01",
    name="古庙废墟",
    description=(
        "一座被岁月侵蚀的古老神庙，大部分屋顶已经坍塌，只剩下几根粗大的石柱矗立着。"
        "地面上散落着破碎的祭坛碎片和风化的石像。"
        "神庙深处隐约可见一个发光的祭坛，散发出神秘的蓝色光芒。"
        "几只亡灵骷髅正在废墟中游荡，守护着这片被遗忘的圣地。"
    ),
    actors=[],
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
        "搜索神庙废墟",
        "返回森林小径",
        "前往地下城入口",
    ],
    connected_scenes=["forest-path-01", "dungeon-entrance-01", "vault-01"],
    exits=[
        SceneExit(direction="森林小径", target_scene_id="forest-path-01"),
        SceneExit(direction="地下城入口", target_scene_id="dungeon-entrance-01"),
        SceneExit(direction="地下宝库", target_scene_id="vault-01"),
    ],
    interactive_elements=[
        InteractiveElement(
            id="glowing-altar-01",
            name="发光祭坛",
            action_name="检查祭坛",
            skill="arcana",
            dc=14,
            success_narrative="你解读了祭坛上的古代符文，获得了神秘的魔法知识，祭坛中央出现了一个发光的神圣护符！",
            failure_narrative="你试图解读祭坛上的符文，但古老的魔法太过复杂，触发了一道电弧，让你轻微受伤。",
            reward_item="holy_amulet",
            reward_info="神圣护符：古代神庙的守护之物，蕴含神圣力量",
        ),
    ],
)

# Scene 7: The Vault (treasure room - with chest event)
VAULT_SCENE = SceneData(
    id="vault-01",
    name="古老宝库",
    description=(
        "地下深处的一间石室，墙壁上镶嵌着发出微光的水晶，照亮了整个空间。"
        "中央的石台上放着一个古老的宝箱，铁锁已经锈迹斑斑，周围散落着一些金币和珠宝碎片。"
        "空气中弥漫着古老魔法的气息，让人既兴奋又警惕。"
        "宝箱旁边还有一具倒下的骷髅，手中握着一把精致的钥匙。"
    ),
    actors=[],
    npcs=[
        NPC(id="treasure-guardian-01", name="宝库守护傀儡", type=NPCType.HOSTILE,
            description="守护着宝箱的魔法构造体，虽然已经残破但仍然危险，用空洞的眼睛盯着入侵者。",
            race="构造体", occupation="守护者"),
    ],
    available_actions=[
        "搜索宝箱（技巧检定 DC 12）",
        "检查骷髅手中的钥匙",
        "搜索散落的金币",
        "与宝库守护傀儡战斗",
        "返回地下城入口",
        "返回古庙废墟",
    ],
    connected_scenes=["dungeon-entrance-01", "ancient-temple-01"],
    exits=[
        SceneExit(direction="地下城入口", target_scene_id="dungeon-entrance-01"),
        SceneExit(direction="古庙废墟", target_scene_id="ancient-temple-01"),
    ],
    loot_items=[
        InventoryItem(id="longsword", name="精钢长剑", type="weapon", damage_dice="1d8", attack_ability="str", description="一把做工精良的长剑，刀刃依然锋利。"),
        InventoryItem(id="chainmail", name="锁子甲", type="armor", base_ac=13, add_dex_modifier=False, description="一套保存完好的锁子甲，防护力不俗。"),
    ],
    interactive_elements=[
        InteractiveElement(
            id="treasure-chest-01",
            name="古老宝箱",
            action_name="搜索",
            skill="sleight_of_hand",
            dc=12,
            success_narrative="你巧妙地撬开了宝箱的锁，箱子里装满了金币，还有一枚闪闪发光的魔法戒指！",
            failure_narrative="你尝试撬开宝箱，但锁扣太过复杂，你的工具在锁芯里折断了，宝箱纹丝未动。",
            reward_item="magic_ring",
            reward_info="魔法戒指：蕴含古老魔法的戒指，佩戴后能增强持有者的意志力",
        ),
    ],
)

# Scene registry for lookups
SCENE_REGISTRY: dict[str, SceneData] = {
    VILLAGE_SQUARE_SCENE.id: VILLAGE_SQUARE_SCENE,
    TAVERN_SCENE.id: TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE.id: DUNGEON_ENTRANCE_SCENE,
    COMBAT_ENCOUNTER_SCENE.id: COMBAT_ENCOUNTER_SCENE,
    FOREST_PATH_SCENE.id: FOREST_PATH_SCENE,
    ANCIENT_TEMPLE_SCENE.id: ANCIENT_TEMPLE_SCENE,
    VAULT_SCENE.id: VAULT_SCENE,
}

# Scene transition keywords
# Maps keywords to target scene IDs
SCENE_TRANSITION_KEYWORDS: dict[str, str] = {
    # To village square
    "village": "village-square-01",
    "square": "village-square-01",
    "广场": "village-square-01",
    "村庄广场": "village-square-01",
    "村广场": "village-square-01",
    "去广场": "village-square-01",
    "回广场": "village-square-01",
    "村庄": "village-square-01",
    "回村庄": "village-square-01",
    "去村庄": "village-square-01",
    "村里": "village-square-01",
    "回村里": "village-square-01",
    
    # To tavern
    "tavern": "tavern-01",
    "酒馆": "tavern-01",
    "返回酒馆": "tavern-01",
    "回酒馆": "tavern-01",
    "灯笼酒馆": "tavern-01",
    "去酒馆": "tavern-01",
    "回村": "tavern-01",
    
    # To dungeon entrance
    "dungeon": "dungeon-entrance-01",
    "地下城": "dungeon-entrance-01",
    "去地下城": "dungeon-entrance-01",
    "前往地下城": "dungeon-entrance-01",
    "入口": "dungeon-entrance-01",
    "石门": "dungeon-entrance-01",
    "去入口": "dungeon-entrance-01",
    "离开酒馆": "dungeon-entrance-01",
    "离开广场": "dungeon-entrance-01",
    
    # To combat encounter
    "combat": "combat-encounter-01",
    "战斗": "combat-encounter-01",
    "进入地下城": "combat-encounter-01",
    "进入通道": "combat-encounter-01",
    "深入": "combat-encounter-01",
    "前进": "combat-encounter-01",

    # To forest path
    "forest": "forest-path-01",
    "森林小径": "forest-path-01",
    "幽暗森林": "forest-path-01",
    "小径": "forest-path-01",
    "去森林": "forest-path-01",
    "前往森林": "forest-path-01",

    # To ancient temple
    "temple": "ancient-temple-01",
    "古庙": "ancient-temple-01",
    "废墟": "ancient-temple-01",
    "古庙废墟": "ancient-temple-01",
    "神庙": "ancient-temple-01",
    "去古庙": "ancient-temple-01",
    "前往古庙": "ancient-temple-01",

    # To vault
    "vault": "vault-01",
    "宝库": "vault-01",
    "宝箱": "vault-01",
    "地下宝库": "vault-01",
    "古老宝库": "vault-01",
    "去宝库": "vault-01",
    "前往宝库": "vault-01",
}


def get_scene_by_id(scene_id: str) -> Optional[SceneData]:
    """Get scene data by ID."""
    return SCENE_REGISTRY.get(scene_id)


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
    return TAVERN_SCENE


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

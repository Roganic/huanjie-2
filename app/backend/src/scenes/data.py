"""Scene data definitions.

This module contains all preset scene definitions and scene-related utilities.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from ..models.state import NPC, NPCType, SceneExit


# ---------------------------------------------------------------------------
# Interactive Element Models
# ---------------------------------------------------------------------------

class InteractiveElement(BaseModel):
    """An interactive element in a scene that can trigger skill checks.
    
    Interactive elements are environmental features that players can interact with,
    potentially triggering skill checks with different outcomes based on success/failure.
    """
    id: str = Field(description="Unique identifier for this element")
    name: str = Field(description="Display name of the element")
    description: str = Field(description="Description shown to players")
    hint: str = Field(description="Hint text suggesting possible interaction")
    skill: str = Field(description="Skill required for the check (e.g., investigation, athletics)")
    dc: int = Field(default=15, description="Difficulty class for the skill check")
    action_name: str = Field(description="Name of the action to trigger this interaction")
    action_description: str = Field(description="Description of what happens when triggered")
    success_narrative: str = Field(description="Narrative text on successful check")
    failure_narrative: str = Field(description="Narrative text on failed check")
    reward_item: Optional[str] = Field(default=None, description="Optional item ID rewarded on success")
    reward_info: Optional[str] = Field(default=None, description="Optional information revealed on success")
    
    model_config = {"populate_by_name": True}


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
    interactive_elements: list[InteractiveElement] = Field(
        default_factory=list,
        description="Interactive environmental elements that can trigger skill checks"
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
    connected_scenes=["tavern-01", "dungeon-entrance-01"],
    exits=[
        SceneExit(direction="酒馆", target_scene_id="tavern-01"),
        SceneExit(direction="森林入口", target_scene_id="dungeon-entrance-01"),
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
        "在酒馆后方，一堵古老的石壁上似乎有微弱的空气流通。"
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
    interactive_elements=[
        InteractiveElement(
            id="secret-climb-wall",
            name="古老石壁",
            description="酒馆后方的一堵古老石壁，表面有可以用来攀爬的裂缝。",
            hint="这堵石壁看起来可以攀爬，裂缝似乎通向某个隐藏的地方。",
            skill="athletics",
            dc=14,
            action_name="攀爬石壁",
            action_description="利用石壁上的裂缝和突起，尝试攀爬到上方",
            success_narrative="你成功攀上了石壁，发现一个小隐藏的壁龛，里面有一把精致的匕首！",
            failure_narrative="石壁太滑了，你爬到一半就滑了下来，手臂有些擦伤。",
            reward_item="hidden_dagger",
            reward_info="石壁上方的壁龛似乎是以前的冒险者留下的",
        ),
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
    connected_scenes=["village-square-01", "tavern-01", "combat-encounter-01"],
    exits=[
        SceneExit(direction="村庄广场", target_scene_id="village-square-01"),
        SceneExit(direction="酒馆", target_scene_id="tavern-01"),
        SceneExit(direction="地下城", target_scene_id="combat-entrance-01"),
    ],
    interactive_elements=[
        InteractiveElement(
            id="mysterious-chest",
            name="神秘箱子",
            description="一个被遗弃在角落的古老箱子，表面覆盖着奇怪的符文。",
            hint="这个箱子看起来被锁住了，但似乎可以检查它的构造。",
            skill="investigation",
            dc=12,
            action_name="调查神秘箱子",
            action_description="仔细检查箱子的锁和符文，尝试找到打开它的方法",
            success_narrative="你发现符文是一个简单的魔法陷阱。小心地解除后，箱子打开了，里面有一瓶治疗药水！",
            failure_narrative="你不小心触发了符文的保护机制，箱子释放出一股寒气，但你未能打开它。",
            reward_item="healing_potion",
            reward_info="箱子里的符文是矮人制造的简单防护魔法",
        ),
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

# Scene registry for lookups
SCENE_REGISTRY: dict[str, SceneData] = {
    VILLAGE_SQUARE_SCENE.id: VILLAGE_SQUARE_SCENE,
    TAVERN_SCENE.id: TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE.id: DUNGEON_ENTRANCE_SCENE,
    COMBAT_ENCOUNTER_SCENE.id: COMBAT_ENCOUNTER_SCENE,
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

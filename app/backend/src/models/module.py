"""Module data models for the modular adventure system.

A module contains scenes, NPCs, quests, story nodes, and triggers that
define an adventure or story segment.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Trigger Conditions
# -----------------------------------------------------------------------------

class TriggerType(str, Enum):
    """Types of trigger conditions."""
    LOCATION = "location"      # Entering a specific scene/location
    ITEM = "item"              # Obtaining a specific item
    QUEST = "quest"            # Quest state change
    DIALOGUE = "dialogue"      # Specific dialogue completed
    FLAG = "flag"              # Game flag set/unset
    TIME = "time"              # Time-based trigger
    CUSTOM = "custom"          # Custom condition logic


class TriggerCondition(BaseModel):
    """A condition that must be met for a trigger to fire."""
    type: TriggerType
    target_id: str = Field(description="ID of the target (scene_id, item_id, quest_id, etc.)")
    value: Any = Field(default=None, description="Optional value to compare against")
    operator: str = Field(default="equals", description="Comparison operator: equals, not_equals, gt, lt, contains")
    
    model_config = {"populate_by_name": True}


class TriggerAction(BaseModel):
    """An action to execute when a trigger fires."""
    type: str = Field(description="Action type: unlock_node, start_quest, spawn_npc, set_flag, etc.")
    target_id: str = Field(description="Target ID for the action")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Additional parameters")
    
    model_config = {"populate_by_name": True}


class Trigger(BaseModel):
    """A trigger that responds to game events."""
    id: str
    name: str
    description: str = ""
    conditions: list[TriggerCondition] = Field(default_factory=list)
    actions: list[TriggerAction] = Field(default_factory=list)
    once_only: bool = Field(default=True, description="Whether this trigger fires only once")
    enabled: bool = Field(default=True)
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Story Nodes
# -----------------------------------------------------------------------------

class StoryNodeType(str, Enum):
    """Types of story nodes."""
    START = "start"            # Starting node
    DIALOGUE = "dialogue"      # Dialogue/conversation node
    COMBAT = "combat"          # Combat encounter node
    EXPLORATION = "exploration"  # Free exploration node
    CHOICE = "choice"          # Player choice node
    EVENT = "event"            # Scripted event
    END = "end"                # Ending node


class StoryNodeTransition(BaseModel):
    """A possible transition to another story node."""
    target_node_id: str
    condition: Optional[str] = None  # Optional condition expression
    description: str = ""
    
    model_config = {"populate_by_name": True}


class StoryNode(BaseModel):
    """A node in the story progression graph."""
    id: str
    name: str
    type: StoryNodeType
    description: str = ""
    scene_id: Optional[str] = None  # Associated scene
    npc_ids: list[str] = Field(default_factory=list)  # NPCs involved
    dialogue_text: Optional[str] = None  # For dialogue nodes
    transitions: list[StoryNodeTransition] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)  # Trigger IDs to activate
    required_flags: list[str] = Field(default_factory=list)  # Flags required to enter
    sets_flags: list[str] = Field(default_factory=list)  # Flags set upon completion
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Quests
# -----------------------------------------------------------------------------

class QuestStatus(str, Enum):
    """Status of a quest."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class QuestObjective(BaseModel):
    """An objective within a quest."""
    id: str
    description: str
    completed: bool = False
    optional: bool = False
    
    model_config = {"populate_by_name": True}


class Quest(BaseModel):
    """A quest or mission in the module."""
    id: str
    name: str
    description: str
    status: QuestStatus = QuestStatus.NOT_STARTED
    objectives: list[QuestObjective] = Field(default_factory=list)
    rewards: dict[str, Any] = Field(default_factory=dict)  # XP, items, etc.
    prerequisites: list[str] = Field(default_factory=list)  # Quest IDs required
    starting_node_id: Optional[str] = None
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# NPCs
# -----------------------------------------------------------------------------

class NPCRole(str, Enum):
    """Role of an NPC in the module."""
    QUEST_GIVER = "quest_giver"
    MERCHANT = "merchant"
    ENEMY = "enemy"
    ALLY = "ally"
    NEUTRAL = "neutral"
    BOSS = "boss"


class NPCStats(BaseModel):
    """Combat stats for an NPC if applicable."""
    hp: int = 10
    ac: int = 10
    str: int = 10
    dex: int = 10
    con: int = 10
    
    model_config = {"populate_by_name": True}


class ModuleNPC(BaseModel):
    """An NPC definition within a module."""
    id: str
    name: str
    description: str = ""
    race: Optional[str] = None
    role: NPCRole = NPCRole.NEUTRAL
    stats: NPCStats = Field(default_factory=NPCStats)
    dialogue_tree_id: Optional[str] = None
    inventory: list[dict[str, Any]] = Field(default_factory=list)
    is_hostile: bool = False
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Scenes
# -----------------------------------------------------------------------------

class SceneExit(BaseModel):
    """An exit from a scene to another scene."""
    direction: str  # "north", "door", "portal", etc.
    target_scene_id: str
    description: str = ""
    locked: bool = False
    key_item_id: Optional[str] = None  # Item required to unlock
    
    model_config = {"populate_by_name": True}


class ModuleScene(BaseModel):
    """A scene/location within a module."""
    id: str
    name: str
    description: str
    npc_ids: list[str] = Field(default_factory=list)  # NPCs present
    exits: list[SceneExit] = Field(default_factory=list)
    items: list[dict[str, Any]] = Field(default_factory=list)  # Items in scene
    flags: list[str] = Field(default_factory=list)  # Scene-specific flags
    lighting: str = "normal"  # normal, dark, bright, dim
    atmosphere: str = ""  # Mood/atmosphere description
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Module
# -----------------------------------------------------------------------------

class ModuleMetadata(BaseModel):
    """Metadata for a module."""
    author: str = ""
    version: str = "1.0.0"
    created_at: str = ""
    tags: list[str] = Field(default_factory=list)
    difficulty: str = "normal"  # easy, normal, hard
    estimated_duration: str = ""  # "30 minutes", "2 hours", etc.
    
    model_config = {"populate_by_name": True}


class Module(BaseModel):
    """A complete adventure module.
    
    Contains all the data needed to run an adventure: scenes, NPCs,
    quests, story nodes, and triggers.
    """
    id: str
    name: str
    description: str
    metadata: ModuleMetadata = Field(default_factory=ModuleMetadata)
    
    # Core content
    scenes: list[ModuleScene] = Field(default_factory=list)
    npcs: list[ModuleNPC] = Field(default_factory=list)
    quests: list[Quest] = Field(default_factory=list)
    story_nodes: list[StoryNode] = Field(default_factory=list)
    triggers: list[Trigger] = Field(default_factory=list)
    
    # Starting state
    starting_scene_id: Optional[str] = None
    starting_node_id: Optional[str] = None
    
    model_config = {"populate_by_name": True}
    
    def get_scene(self, scene_id: str) -> Optional[ModuleScene]:
        """Get a scene by ID."""
        for scene in self.scenes:
            if scene.id == scene_id:
                return scene
        return None
    
    def get_npc(self, npc_id: str) -> Optional[ModuleNPC]:
        """Get an NPC by ID."""
        for npc in self.npcs:
            if npc.id == npc_id:
                return npc
        return None
    
    def get_quest(self, quest_id: str) -> Optional[Quest]:
        """Get a quest by ID."""
        for quest in self.quests:
            if quest.id == quest_id:
                return quest
        return None
    
    def get_story_node(self, node_id: str) -> Optional[StoryNode]:
        """Get a story node by ID."""
        for node in self.story_nodes:
            if node.id == node_id:
                return node
        return None
    
    def get_trigger(self, trigger_id: str) -> Optional[Trigger]:
        """Get a trigger by ID."""
        for trigger in self.triggers:
            if trigger.id == trigger_id:
                return trigger
        return None


# -----------------------------------------------------------------------------
# Module Summary (for list views)
# -----------------------------------------------------------------------------

class ModuleSummary(BaseModel):
    """Summary of a module for listing."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    difficulty: str = "normal"
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Active Module State
# -----------------------------------------------------------------------------

class ActiveModule(BaseModel):
    """Information about the currently active module."""
    id: str
    name: str
    current_node_id: Optional[str] = None
    current_scene_id: Optional[str] = None
    completed_nodes: list[str] = Field(default_factory=list)
    active_flags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Engine Types (used by module_engine.py for story-node progression)
# -----------------------------------------------------------------------------

class StoryTriggerType(str, Enum):
    """Trigger types for engine story-node transitions."""
    ENTER_SCENE = "enter_scene"
    INTERACT_NPC = "interact_npc"
    ACTION_KEYWORD = "action_keyword"


class StoryTrigger(BaseModel):
    """A condition that advances the story node when satisfied."""
    type: StoryTriggerType
    target: str = Field(..., description="Scene ID, NPC ID, or keyword to match")
    next_node_id: str = Field(..., description="Story node to switch to when trigger fires")


class EngineStoryNode(BaseModel):
    """A story node representing a beat in the module narrative (engine version)."""
    id: str
    name: str
    description: str
    scene_id: str = Field(..., description="Scene ID where this node takes place")
    visible_npcs: list[str] = Field(default_factory=list)
    quests: list[Quest] = Field(default_factory=list)
    triggers: list[StoryTrigger] = Field(default_factory=list)


class ModuleDefinition(BaseModel):
    """Static definition of an adventure module (engine version)."""
    id: str
    name: str
    description: str = ""
    starting_node_id: str
    nodes: dict[str, EngineStoryNode] = Field(default_factory=dict)


class ActiveModuleState(BaseModel):
    """Runtime module state attached to a session (engine version)."""
    module_id: str
    current_story_node: str = Field(..., description="ID of the current story node")
    visited_nodes: list[str] = Field(default_factory=list)
    completed_quests: list[str] = Field(default_factory=list)
    active_flags: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Built-in default module for when no module is loaded
# -----------------------------------------------------------------------------

_DEFAULT_MODULE = Module(
    id="default",
    name="自由探索",
    description="无模组模式，由 AI DM 自由创作剧情",
    starting_scene_id=None,
    starting_node_id=None,
)


# -----------------------------------------------------------------------------
# Starter Module: Village & Dungeon
# -----------------------------------------------------------------------------

STARTER_MODULE = ModuleDefinition(
    id="starter-village-dungeon",
    name="村庄与地下城",
    description="一个经典的入门冒险：从村庄出发，探索地下城入口，进入战斗。",
    starting_node_id="node-village-arrival",
    nodes={
        "node-village-arrival": EngineStoryNode(
            id="node-village-arrival",
            name="抵达村庄",
            description="你来到了十字路口村庄。广场上的村民忙碌着，酒馆里传来麦酒的香气。这里是一切冒险的起点。",
            scene_id="village-square-01",
            visible_npcs=["village-elder-01", "blacksmith-01", "merchant-02"],
            quests=[
                Quest(
                    id="quest-explore-village",
                    name="探索村庄",
                    description="熟悉村庄的环境，为即将到来的冒险做准备。",
                    objectives=[
                        QuestObjective(id="obj-visit-tavern", description="前往灯笼酒馆打听消息"),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(type=StoryTriggerType.ENTER_SCENE, target="tavern-01", next_node_id="node-tavern-gossip"),
            ],
        ),
        "node-tavern-gossip": EngineStoryNode(
            id="node-tavern-gossip",
            name="酒馆消息",
            description="灯笼酒馆里，老马库斯一边擦杯子一边低声说：最近地下城方向不太平，有个受伤的矮人从那边逃了回来。银弦艾拉的琴声也带着一丝不安。",
            scene_id="tavern-01",
            visible_npcs=["tavern-keeper-01", "tavern-bard-01", "merchant-01"],
            quests=[
                Quest(
                    id="quest-dungeon-rumors",
                    name="地下城传闻",
                    description="收集关于地下城危险的线索。",
                    objectives=[
                        QuestObjective(id="obj-talk-marcus", description="与老马库斯交谈"),
                        QuestObjective(id="obj-go-dungeon", description="前往遗忘地下城入口"),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(type=StoryTriggerType.ENTER_SCENE, target="dungeon-entrance-01", next_node_id="node-dungeon-entrance"),
                StoryTrigger(type=StoryTriggerType.INTERACT_NPC, target="tavern-keeper-01", next_node_id="node-tavern-gossip"),
            ],
        ),
        "node-dungeon-entrance": EngineStoryNode(
            id="node-dungeon-entrance",
            name="地下城入口",
            description="古老的石门半埋在藤蔓中。受伤的矮人托尔金靠在树干上，神情惊恐。他警告你：地下城通道里有哥布林巡逻队。",
            scene_id="dungeon-entrance-01",
            visible_npcs=["wounded-adventurer-01", "guard-corpse-01"],
            quests=[
                Quest(
                    id="quest-enter-dungeon",
                    name="进入地下城",
                    description="深入地下城，面对潜伏的危险。",
                    objectives=[
                        QuestObjective(id="obj-enter-corridor", description="进入地下城通道"),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(type=StoryTriggerType.ENTER_SCENE, target="combat-encounter-01", next_node_id="node-goblin-encounter"),
                StoryTrigger(type=StoryTriggerType.INTERACT_NPC, target="wounded-adventurer-01", next_node_id="node-dungeon-entrance"),
            ],
        ),
        "node-goblin-encounter": EngineStoryNode(
            id="node-goblin-encounter",
            name="哥布林遭遇",
            description="狭窄的地下通道中，哥布林斥候、萨满和座狼挡住了去路。战斗一触即发。",
            scene_id="combat-encounter-01",
            visible_npcs=["goblin-01", "goblin-shaman-01", "wolf-01"],
            quests=[
                Quest(
                    id="quest-survive-encounter",
                    name="突破遭遇",
                    description="击败或摆脱哥布林巡逻队。",
                    objectives=[
                        QuestObjective(id="obj-survive", description="在地下城通道中生存下来"),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(type=StoryTriggerType.ACTION_KEYWORD, target="战斗", next_node_id="node-goblin-encounter"),
            ],
        ),
    },
)


MODULE_REGISTRY: dict[str, ModuleDefinition] = {
    STARTER_MODULE.id: STARTER_MODULE,
}


def get_module(module_id: str) -> Optional[ModuleDefinition]:
    """Get a module by ID from the registry."""
    return MODULE_REGISTRY.get(module_id)


def get_default_module() -> ModuleDefinition:
    """Return the default starter module."""
    return STARTER_MODULE


def register_module(module: ModuleDefinition) -> None:
    """Register a module in the registry."""
    MODULE_REGISTRY[module.id] = module

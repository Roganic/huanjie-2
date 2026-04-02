"""Module (adventure module) data models for story node progression."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    ENTER_SCENE = "enter_scene"
    INTERACT_NPC = "interact_npc"
    ACTION_KEYWORD = "action_keyword"


class StoryTrigger(BaseModel):
    """A condition that advances the story node when satisfied."""

    type: TriggerType
    target: str = Field(
        ...,
        description="Scene ID, NPC ID, or keyword to match",
    )
    next_node_id: str = Field(
        ...,
        description="Story node to switch to when trigger fires",
    )


class QuestObjective(BaseModel):
    """A single objective within a quest."""

    id: str
    description: str
    completed: bool = False


class Quest(BaseModel):
    """An active quest in the module."""

    id: str
    name: str
    description: str = ""
    objectives: list[QuestObjective] = Field(default_factory=list)


class StoryNode(BaseModel):
    """A story node representing a beat in the module narrative."""

    id: str
    name: str
    description: str
    scene_id: str = Field(
        ...,
        description="Scene ID where this node takes place",
    )
    visible_npcs: list[str] = Field(
        default_factory=list,
        description="NPC IDs that should be present/narratively relevant",
    )
    quests: list[Quest] = Field(default_factory=list)
    triggers: list[StoryTrigger] = Field(default_factory=list)


class ModuleDefinition(BaseModel):
    """Static definition of an adventure module."""

    id: str
    name: str
    description: str = ""
    starting_node_id: str
    nodes: dict[str, StoryNode] = Field(default_factory=dict)


class ActiveModuleState(BaseModel):
    """Runtime module state attached to a session."""

    module_id: str
    current_story_node: str = Field(
        ...,
        description="ID of the current story node",
    )
    visited_nodes: list[str] = Field(default_factory=list)
    completed_quests: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Starter Module: Village & Dungeon
# -----------------------------------------------------------------------------

STARTER_MODULE = ModuleDefinition(
    id="starter-village-dungeon",
    name="村庄与地下城",
    description="一个经典的入门冒险：从村庄出发，探索地下城入口，进入战斗。",
    starting_node_id="node-village-arrival",
    nodes={
        "node-village-arrival": StoryNode(
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
                        QuestObjective(
                            id="obj-visit-tavern",
                            description="前往灯笼酒馆打听消息",
                        ),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(
                    type=TriggerType.ENTER_SCENE,
                    target="tavern-01",
                    next_node_id="node-tavern-gossip",
                ),
            ],
        ),
        "node-tavern-gossip": StoryNode(
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
                        QuestObjective(
                            id="obj-talk-marcus",
                            description="与老马库斯交谈",
                        ),
                        QuestObjective(
                            id="obj-go-dungeon",
                            description="前往遗忘地下城入口",
                        ),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(
                    type=TriggerType.ENTER_SCENE,
                    target="dungeon-entrance-01",
                    next_node_id="node-dungeon-entrance",
                ),
                StoryTrigger(
                    type=TriggerType.INTERACT_NPC,
                    target="tavern-keeper-01",
                    next_node_id="node-tavern-gossip",
                ),
            ],
        ),
        "node-dungeon-entrance": StoryNode(
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
                        QuestObjective(
                            id="obj-enter-corridor",
                            description="进入地下城通道",
                        ),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(
                    type=TriggerType.ENTER_SCENE,
                    target="combat-encounter-01",
                    next_node_id="node-goblin-encounter",
                ),
                StoryTrigger(
                    type=TriggerType.INTERACT_NPC,
                    target="wounded-adventurer-01",
                    next_node_id="node-dungeon-entrance",
                ),
            ],
        ),
        "node-goblin-encounter": StoryNode(
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
                        QuestObjective(
                            id="obj-survive",
                            description="在地下城通道中生存下来",
                        ),
                    ],
                ),
            ],
            triggers=[
                StoryTrigger(
                    type=TriggerType.ACTION_KEYWORD,
                    target="战斗",
                    next_node_id="node-goblin-encounter",
                ),
            ],
        ),
    },
)

MODULE_REGISTRY: dict[str, ModuleDefinition] = {
    STARTER_MODULE.id: STARTER_MODULE,
}


def get_module(module_id: str) -> Optional[ModuleDefinition]:
    return MODULE_REGISTRY.get(module_id)


def get_default_module() -> ModuleDefinition:
    return STARTER_MODULE

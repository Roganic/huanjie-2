"""NPC (Non-Player Character) system for scene content."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NPCType(str, Enum):
    """NPC disposition types."""
    FRIENDLY = "friendly"
    NEUTRAL = "neutral"
    HOSTILE = "hostile"


class NPC(BaseModel):
    """Non-player character data model.
    
    NPCs populate scenes and provide interaction opportunities for players.
    """
    id: str
    name: str
    type: NPCType = Field(default=NPCType.NEUTRAL, description="NPC disposition type")
    description: str = Field(default="", description="Brief description of the NPC")
    race: Optional[str] = Field(default=None, description="NPC race/species")
    occupation: Optional[str] = Field(default=None, description="NPC occupation or role")
    
    model_config = {"populate_by_name": True}


# -----------------------------------------------------------------------------
# Pre-defined NPCs for scenes
# -----------------------------------------------------------------------------

# Tavern NPCs
TAVERN_KEEPER = NPC(
    id="tavern-keeper-01",
    name="老马库斯",
    type=NPCType.FRIENDLY,
    description="灯笼酒馆的老板，一位白发苍苍的老兵，瞎了一只眼但笑容温暖。",
    race="人类",
    occupation="酒馆老板",
    hp=12,
    hp_max=12,
    ac=14,
    attributes={"str": 14, "dex": 12, "con": 14, "int": 10, "wis": 12, "cha": 12},
)

TAVERN_BARD = NPC(
    id="tavern-bard-01",
    name="银弦艾拉",
    type=NPCType.NEUTRAL,
    description="在角落演奏竖琴的吟游诗人，据说知道很多古老传说。",
    race="精灵",
    occupation="吟游诗人",
    hp=8,
    hp_max=8,
    ac=12,
    attributes={"str": 8, "dex": 14, "con": 10, "int": 12, "wis": 12, "cha": 16},
)

SUSPICIOUS_MERCHANT = NPC(
    id="merchant-01",
    name="戴兜帽的商人",
    type=NPCType.NEUTRAL,
    description="独自坐在阴影中的神秘商人，时不时打量着进出的客人。",
    race="未知",
    occupation="商人",
    hp=10,
    hp_max=10,
    ac=13,
    attributes={"str": 10, "dex": 14, "con": 12, "int": 14, "wis": 12, "cha": 12},
)

# Dungeon entrance NPCs
WOUNDED_ADVENTURER = NPC(
    id="wounded-adventurer-01",
    name="托尔金",
    type=NPCType.FRIENDLY,
    description="从地下城逃出来的受伤冒险者，神情惊恐。",
    race="矮人",
    occupation="冒险者",
    hp=6,
    hp_max=10,
    ac=15,
    attributes={"str": 14, "dex": 10, "con": 14, "int": 8, "wis": 10, "cha": 8},
)

GUARD_CORPSE = NPC(
    id="guard-corpse-01",
    name="死去的守卫",
    type=NPCType.NEUTRAL,
    description="倒在地下城入口旁的石像守卫，身上布满了战斗的痕迹。",
    race="构造体",
    occupation="守卫",
    hp=0,
    hp_max=15,
    ac=16,
    attributes={"str": 16, "dex": 8, "con": 16, "int": 3, "wis": 10, "cha": 1},
)

# Forest path / Combat encounter NPCs (enemies)
GOBLIN_SCOUT = NPC(
    id="goblin-01",
    name="哥布林斥候",
    type=NPCType.HOSTILE,
    description="一只瘦小的哥布林，手持锈迹斑斑的匕首，眼中闪烁着贪婪的光芒。",
    race="哥布林",
    occupation="斥候",
    hp=7,
    hp_max=7,
    ac=12,
    attributes={"str": 8, "dex": 14, "con": 10, "int": 10, "wis": 8, "cha": 8},
)

GOBLIN_SHAMAN = NPC(
    id="goblin-shaman-01",
    name="哥布林萨满",
    type=NPCType.HOSTILE,
    description="头戴骨饰的哥布林施法者，正在低声念诵某种咒语。",
    race="哥布林",
    occupation="萨满",
    hp=9,
    hp_max=9,
    ac=13,
    attributes={"str": 8, "dex": 12, "con": 12, "int": 12, "wis": 14, "cha": 10},
)

WOLF_COMPANION = NPC(
    id="wolf-01",
    name="座狼",
    type=NPCType.HOSTILE,
    description="一只体型巨大的灰狼，獠牙外露，口水滴落在地上。",
    race="野兽",
    occupation="战斗伙伴",
    hp=11,
    hp_max=11,
    ac=13,
    attributes={"str": 14, "dex": 14, "con": 12, "int": 3, "wis": 12, "cha": 6},
)

# NPC collections by scene
TAVERN_NPCS: list[NPC] = [TAVERN_KEEPER, TAVERN_BARD, SUSPICIOUS_MERCHANT]
DUNGEON_ENTRANCE_NPCS: list[NPC] = [WOUNDED_ADVENTURER, GUARD_CORPSE]
COMBAT_ENCOUNTER_NPCS: list[NPC] = [GOBLIN_SCOUT, GOBLIN_SHAMAN, WOLF_COMPANION]

# NPC lookup by ID
NPC_REGISTRY: dict[str, NPC] = {
    npc.id: npc for npc in [
        TAVERN_KEEPER,
        TAVERN_BARD,
        SUSPICIOUS_MERCHANT,
        WOUNDED_ADVENTURER,
        GUARD_CORPSE,
        GOBLIN_SCOUT,
        GOBLIN_SHAMAN,
        WOLF_COMPANION,
    ]
}


def get_npc_by_id(npc_id: str) -> Optional[NPC]:
    """Get an NPC by their ID."""
    return NPC_REGISTRY.get(npc_id)


def get_npcs_by_ids(npc_ids: list[str]) -> list[NPC]:
    """Get multiple NPCs by their IDs."""
    return [npc for npc_id in npc_ids if (npc := get_npc_by_id(npc_id)) is not None]


def get_npc_names_for_scene(npc_ids: list[str]) -> list[str]:
    """Get NPC names for display in a scene."""
    return [npc.name for npc_id in npc_ids if (npc := get_npc_by_id(npc_id)) is not None]

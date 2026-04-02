"""Bootstrap state models: actor, scene, and session narrative memory."""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, validator


# ---------------------------------------------------------------------------
# Equipment and Inventory Models
# ---------------------------------------------------------------------------

class ItemType(str, Enum):
    """Types of items."""
    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"


class Weapon(BaseModel):
    """Weapon item definition."""
    id: str
    name: str
    damage_dice: str  # e.g., "1d8", "1d6"
    attack_ability: str = "str"  # "str" or "dex"
    description: str = ""
    
    model_config = {"populate_by_name": True}


class Armor(BaseModel):
    """Armor item definition."""
    id: str
    name: str
    base_ac: int  # Base AC value (e.g., 16 for chain mail)
    add_dex_modifier: bool = True  # Whether to add DEX modifier
    max_dex_bonus: int | None = None  # Max DEX bonus (None = no limit)
    description: str = ""
    
    model_config = {"populate_by_name": True}


class Consumable(BaseModel):
    """Consumable item definition."""
    id: str
    name: str
    effect_type: str = "heal"  # e.g., "heal", "buff"
    effect_dice: str | None = None  # e.g., "2d4+2"
    description: str = ""
    
    model_config = {"populate_by_name": True}


class InventoryItem(BaseModel):
    """An item in the character's inventory."""
    id: str
    name: str
    type: ItemType
    # For weapons
    damage_dice: str | None = None
    attack_ability: str | None = None
    # For armor
    base_ac: int | None = None
    add_dex_modifier: bool = True
    max_dex_bonus: int | None = None
    description: str = ""
    
    model_config = {"populate_by_name": True}
    
    @classmethod
    def from_weapon(cls, weapon: Weapon) -> "InventoryItem":
        return cls(
            id=weapon.id,
            name=weapon.name,
            type=ItemType.WEAPON,
            damage_dice=weapon.damage_dice,
            attack_ability=weapon.attack_ability,
            description=weapon.description,
        )
    
    @classmethod
    def from_armor(cls, armor: Armor) -> "InventoryItem":
        return cls(
            id=armor.id,
            name=armor.name,
            type=ItemType.ARMOR,
            base_ac=armor.base_ac,
            add_dex_modifier=armor.add_dex_modifier,
            max_dex_bonus=armor.max_dex_bonus,
            description=armor.description,
        )
    
    @classmethod
    def from_consumable(cls, consumable: Consumable) -> "InventoryItem":
        return cls(
            id=consumable.id,
            name=consumable.name,
            type=ItemType.CONSUMABLE,
            description=consumable.description,
        )


class EquippedItems(BaseModel):
    """Currently equipped items."""
    weapon: InventoryItem | None = None
    armor: InventoryItem | None = None
    
    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Default Equipment Definitions
# ---------------------------------------------------------------------------

DEFAULT_WEAPONS: dict[str, Weapon] = {
    "longsword": Weapon(
        id="longsword",
        name="长剑",
        damage_dice="1d8",
        attack_ability="str",
        description="一把标准的长剑，平衡性良好。",
    ),
    "shortsword": Weapon(
        id="shortsword",
        name="短剑",
        damage_dice="1d6",
        attack_ability="dex",
        description="一把轻便的短剑，适合快速攻击。",
    ),
    "quarterstaff": Weapon(
        id="quarterstaff",
        name="法杖",
        damage_dice="1d6",
        attack_ability="str",
        description="一根结实的木质法杖，可用于施法和自卫。",
    ),
}

DEFAULT_ARMORS: dict[str, Armor] = {
    "chain_mail": Armor(
        id="chain_mail",
        name="锁甲",
        base_ac=16,
        add_dex_modifier=False,
        description="由金属环编织而成的重甲。",
    ),
    "leather": Armor(
        id="leather",
        name="皮甲",
        base_ac=11,
        add_dex_modifier=True,
        max_dex_bonus=None,
        description="轻便的皮革护甲，不影响灵活性。",
    ),
    "robe": Armor(
        id="robe",
        name="布袍",
        base_ac=10,
        add_dex_modifier=True,
        max_dex_bonus=None,
        description="普通的布制长袍，几乎没有防护能力。",
    ),
}

DEFAULT_CONSUMABLES: dict[str, Consumable] = {
    "healing_potion": Consumable(
        id="healing_potion",
        name="治疗药水",
        effect_type="heal",
        effect_dice="2d4+2",
        description="一瓶红色的治疗药水，饮用后可恢复生命值。",
    ),
}


class AbilityScores(BaseModel):
    str_: int = Field(..., alias="str")
    dex: int
    con: int
    int_: int = Field(..., alias="int")
    wis: int
    cha: int

    model_config = {"populate_by_name": True}

    @field_validator("str_", "dex", "con", "int_", "wis", "cha")
    @classmethod
    def _ability_score_range(cls, v: int) -> int:
        if not 3 <= v <= 18:
            raise ValueError("ability score must be between 3 and 18")
        return v

    def modifier(self, ability: str) -> int:
        """Return the D&D-style modifier for a given ability abbreviation."""
        score = self.by_abbr(ability)
        return (score - 10) // 2

    def by_abbr(self, ability: str) -> int:
        mapping = {
            "str": self.str_,
            "dex": self.dex,
            "con": self.con,
            "int": self.int_,
            "wis": self.wis,
            "cha": self.cha,
        }
        return mapping[ability]


class CharacterClass(str, Enum):
    WARRIOR = "warrior"
    MAGE = "mage"
    ROGUE = "rogue"


class GamePhase(str, Enum):
    CHARACTER_CREATION = "character_creation"
    ADVENTURE = "adventure"


class AdventurePhase(str, Enum):
    """Sub-phase within adventure: exploration, combat, or ended."""
    EXPLORATION = "exploration"
    COMBAT = "combat"
    ENDED = "ended"


class Skill(BaseModel):
    name: str
    ability: str
    proficient: bool
    modifier: int


class SpellSlot(BaseModel):
    """Spell slot for spellcasting classes."""
    level: int           # Spell level (1-9)
    max: int             # Maximum slots at this level
    current: int         # Current available slots
    
    model_config = {"populate_by_name": True}


class Actor(BaseModel):
    id: str
    name: str
    character_class: CharacterClass | None = None
    abilities: AbilityScores
    proficiency_bonus: int = 2
    level: int = 1
    hp: int
    hp_max: int
    ac: int = 10  # Armor Class, default 10 + DEX modifier
    conditions: list[str] = Field(default_factory=list)
    description: str = ""
    skills: list[Skill] = Field(default_factory=list)
    # Inventory and equipment
    inventory: list[InventoryItem] = Field(default_factory=list)
    equipped: EquippedItems = Field(default_factory=EquippedItems)
    # Spell slots for spellcasting classes
    spell_slots: list[SpellSlot] = Field(default_factory=list)


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
    dialogue_count: int = Field(default=0, description="Number of dialogue interactions with this NPC")


class SceneExit(BaseModel):
    """A scene exit direction and target."""
    direction: str = Field(description="Display name for the exit direction")
    target_scene_id: str = Field(description="ID of the target scene")
    
    model_config = {"populate_by_name": True}


class Scene(BaseModel):
    id: str
    name: str
    description: str
    actors: list[str] = Field(default_factory=list, description="Actor IDs present")
    npcs: list[NPC] = Field(default_factory=list, description="NPCs present in this scene")
    time: int = Field(default=0, description="Abstract time ticks elapsed")
    flags: list[str] = Field(default_factory=list, description="Mutable scene state flags")
    exits: list[SceneExit] = Field(default_factory=list, description="Available exits from this scene")
    visited_count: int = Field(default=1, description="Number of times this scene has been visited")


class NarrativeHistoryEntry(BaseModel):
    action_summary: str
    resolution_summary: dict[str, Any] = Field(default_factory=dict)
    narration_summary: str
    narration: str = ""
    scene_progression: str = ""
    gm_prompt: str = ""
    created_at: int = Field(default=0, description="Client-friendly creation timestamp in ms")


class SceneHistoryEntry(BaseModel):
    action_type: str
    check_result: dict[str, Any] = Field(default_factory=dict)
    narrative_keywords: list[str] = Field(default_factory=list)
    npc_changes: list[str] = Field(default_factory=list)


class BootstrapState(BaseModel):
    session_id: str
    phase: GamePhase
    game_phase: AdventurePhase = Field(default=AdventurePhase.EXPLORATION, description="Current adventure phase: exploration, combat, or ended")
    actor: Actor | None = None
    scene: Scene
    narrative_history: list[NarrativeHistoryEntry] = Field(default_factory=list)
    scene_history: list[SceneHistoryEntry] = Field(default_factory=list)


class AttributeWithModifier(BaseModel):
    score: int
    modifier: int


class HP(BaseModel):
    current: int
    max: int


class CharacterSkill(BaseModel):
    name: str
    ability: str
    proficient: bool
    modifier: int


class CharacterEquipped(BaseModel):
    """Equipped items for CharacterCard response."""
    weapon: dict[str, Any] | None = None
    armor: dict[str, Any] | None = None


class CharacterCard(BaseModel):
    name: str
    class_: str = Field(..., alias="class")
    level: int
    proficiency_bonus: int
    attributes: dict[str, AttributeWithModifier]
    hp: HP
    ac: int
    skills: list[CharacterSkill]
    inventory: list[dict[str, Any]] = Field(default_factory=list)
    equipped: CharacterEquipped = Field(default_factory=CharacterEquipped)
    # Spell slots for spellcasting classes
    spell_slots: list[dict[str, int]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class CharacterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    character_class: CharacterClass
    ability_generation: str = Field(
        default="standard_array",
        description="Ability generation method: standard_array, random_4d6, or manual.",
    )
    abilities: AbilityScores | None = Field(
        default=None,
        description="Custom ability scores when ability_generation is 'manual'.",
    )

    @validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @validator("ability_generation")
    @classmethod
    def ability_generation_must_be_supported(cls, value: str) -> str:
        allowed = {"standard_array", "random_4d6", "manual"}
        if value not in allowed:
            raise ValueError(f"ability_generation must be one of {allowed}")
        return value

"""Bootstrap state models: actor, scene, and session narrative memory."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, validator


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


class Scene(BaseModel):
    id: str
    name: str
    description: str
    actors: list[str] = Field(default_factory=list, description="Actor IDs present")
    time: int = Field(default=0, description="Abstract time ticks elapsed")
    flags: list[str] = Field(default_factory=list, description="Mutable scene state flags")


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


class CharacterCard(BaseModel):
    name: str
    class_: str = Field(..., alias="class")
    level: int
    proficiency_bonus: int
    attributes: dict[str, AttributeWithModifier]
    hp: HP
    ac: int
    skills: list[CharacterSkill]

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

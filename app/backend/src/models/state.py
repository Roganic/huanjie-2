"""Bootstrap state models: actor, scene, and session narrative memory."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


class AbilityScores(BaseModel):
    str_: int = Field(..., alias="str")
    dex: int
    con: int
    int_: int = Field(..., alias="int")
    wis: int
    cha: int

    model_config = {"populate_by_name": True}

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


class Actor(BaseModel):
    id: str
    name: str
    character_class: CharacterClass | None = None
    abilities: AbilityScores
    proficiency_bonus: int = 2
    hp: int
    hp_max: int
    ac: int = 10  # Armor Class, default 10 + DEX modifier
    conditions: list[str] = Field(default_factory=list)
    description: str = ""


class Scene(BaseModel):
    id: str
    name: str
    description: str
    actors: list[str] = Field(default_factory=list, description="Actor IDs present")
    time: int = Field(default=0, description="Abstract time ticks elapsed")


class NarrativeHistoryEntry(BaseModel):
    action_summary: str
    resolution_summary: dict[str, Any] = Field(default_factory=dict)
    narration_summary: str
    narration: str = ""
    scene_progression: str = ""
    gm_prompt: str = ""
    created_at: int = Field(default=0, description="Client-friendly creation timestamp in ms")


class BootstrapState(BaseModel):
    session_id: str
    phase: GamePhase
    actor: Actor | None = None
    scene: Scene
    narrative_history: list[NarrativeHistoryEntry] = Field(default_factory=list)


class CharacterCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=40)
    character_class: CharacterClass
    ability_generation: str = Field(
        default="standard_array",
        description="Current prototype supports only standard_array.",
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
        if value != "standard_array":
            raise ValueError("only standard_array is supported")
        return value

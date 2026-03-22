"""Bootstrap state models: actor and scene."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class Actor(BaseModel):
    id: str
    name: str
    abilities: AbilityScores
    proficiency_bonus: int = 2
    hp: int
    hp_max: int
    conditions: list[str] = Field(default_factory=list)
    description: str = ""


class Scene(BaseModel):
    id: str
    name: str
    description: str
    actors: list[str] = Field(default_factory=list, description="Actor IDs present")
    time: int = Field(default=0, description="Abstract time ticks elapsed")


class BootstrapState(BaseModel):
    actor: Actor
    scene: Scene

"""D&D 5e Character data model with derived values computed via rules engine."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator

from src.rules.calculations import (
    ability_modifier,
    calculate_ac as calc_ac,
    calculate_max_hp as calc_max_hp,
    calculate_skill_modifier as calc_skill_modifier,
    CharacterClass,
    proficiency_bonus as calc_proficiency_bonus,
)


class AbilityScores(BaseModel):
    """Six D&D ability scores with modifier calculation."""
    
    str_: int = Field(..., alias="str", ge=3, le=18)
    dex: int = Field(..., ge=3, le=18)
    con: int = Field(..., ge=3, le=18)
    int_: int = Field(..., alias="int", ge=3, le=18)
    wis: int = Field(..., ge=3, le=18)
    cha: int = Field(..., ge=3, le=18)
    
    model_config = {"populate_by_name": True}
    
    def modifier(self, ability: str) -> int:
        """Get the modifier for a specific ability by abbreviation."""
        score = self.by_abbr(ability)
        return ability_modifier(score)
    
    def by_abbr(self, ability: str) -> int:
        """Get ability score by abbreviation."""
        mapping = {
            "str": self.str_,
            "dex": self.dex,
            "con": self.con,
            "int": self.int_,
            "wis": self.wis,
            "cha": self.cha,
        }
        return mapping[ability.lower()]


class SkillDefinition(BaseModel):
    """Definition of a skill and its governing ability."""
    
    name: str
    ability: str


class Skill(BaseModel):
    """A skill with proficiency status and computed modifier."""
    
    name: str
    ability: str
    proficient: bool
    modifier: int


class Equipment(BaseModel):
    """Character equipment affecting calculations."""
    
    has_shield: bool = False
    armor_base_ac: int | None = None  # None = unarmored (base 10)


class Character(BaseModel):
    """Complete D&D 5e character model with computed properties.
    
    All derived values (modifiers, HP, AC, skill modifiers) are computed
    via the rules engine rather than stored directly.
    """
    
    # Core identity
    name: str
    character_class: CharacterClass
    level: int = Field(default=1, ge=1, le=20)
    
    # Base attributes
    abilities: AbilityScores
    
    # Equipment affecting calculations
    equipment: Equipment = Field(default_factory=Equipment)
    
    # Skill proficiencies (skill names)
    skill_proficiencies: set[str] = Field(default_factory=set)
    
    # HP tracking (current can change, max is computed)
    hp_current: int | None = None
    
    model_config = {"populate_by_name": True}
    
    @field_validator("hp_current")
    @classmethod
    def set_initial_hp(cls, v: int | None, info: Any) -> int | None:
        """Set initial HP to max if not provided."""
        if v is None:
            # Will be set to max_hp after initialization
            return None
        return v
    
    @computed_field
    @property
    def str_modifier(self) -> int:
        """Strength modifier computed from score."""
        return self.abilities.modifier("str")
    
    @computed_field
    @property
    def dex_modifier(self) -> int:
        """Dexterity modifier computed from score."""
        return self.abilities.modifier("dex")
    
    @computed_field
    @property
    def con_modifier(self) -> int:
        """Constitution modifier computed from score."""
        return self.abilities.modifier("con")
    
    @computed_field
    @property
    def int_modifier(self) -> int:
        """Intelligence modifier computed from score."""
        return self.abilities.modifier("int")
    
    @computed_field
    @property
    def wis_modifier(self) -> int:
        """Wisdom modifier computed from score."""
        return self.abilities.modifier("wis")
    
    @computed_field
    @property
    def cha_modifier(self) -> int:
        """Charisma modifier computed from score."""
        return self.abilities.modifier("cha")
    
    @computed_field
    @property
    def proficiency_bonus(self) -> int:
        """Proficiency bonus computed from level."""
        return calc_proficiency_bonus(self.level)
    
    @computed_field
    @property
    def max_hp(self) -> int:
        """Maximum HP computed from class hit die and CON modifier."""
        return calc_max_hp(
            self.character_class,
            self.con_modifier,
            self.level
        )
    
    @computed_field
    @property
    def current_hp(self) -> int:
        """Current HP (defaults to max if not set)."""
        return self.hp_current if self.hp_current is not None else self.max_hp
    
    @computed_field
    @property
    def ac(self) -> int:
        """Armor Class computed from equipment and DEX modifier."""
        base_ac = self.equipment.armor_base_ac or 10
        
        # For heavy armor (base AC 16+ typically), DEX modifier doesn't apply
        # This is simplified - in a full system, armor type would be explicit
        if self.character_class == CharacterClass.WARRIOR and base_ac >= 16:
            # Heavy armor: use base AC only, no DEX
            dex_mod = 0
        else:
            # Light armor or unarmored: apply DEX modifier
            dex_mod = self.dex_modifier
        
        return calc_ac(
            dex_modifier=dex_mod,
            base_ac=base_ac,
            has_shield=self.equipment.has_shield
        )
    
    @computed_field
    @property
    def skills(self) -> list[Skill]:
        """Computed skill list with modifiers."""
        from src.state import _SKILL_DEFINITIONS  # Avoid circular import
        
        result = []
        for definition in _SKILL_DEFINITIONS:
            ability = definition["ability"]
            name = definition["name"]
            proficient = name in self.skill_proficiencies
            ability_mod = self.abilities.modifier(ability)
            modifier = calc_skill_modifier(
                ability_modifier=ability_mod,
                is_proficient=proficient,
                prof_bonus=self.proficiency_bonus
            )
            result.append(Skill(
                name=name,
                ability=ability,
                proficient=proficient,
                modifier=modifier
            ))
        return result
    
    def get_skill_modifier(self, skill_name: str) -> int:
        """Get the modifier for a specific skill by name."""
        for skill in self.skills:
            if skill.name == skill_name:
                return skill.modifier
        raise ValueError(f"Unknown skill: {skill_name}")
    
    def to_card(self) -> dict[str, Any]:
        """Convert to character card format for API responses."""
        return {
            "name": self.name,
            "class": self.character_class.value,
            "level": self.level,
            "proficiency_bonus": self.proficiency_bonus,
            "attributes": {
                "str": {"score": self.abilities.str_, "modifier": self.str_modifier},
                "dex": {"score": self.abilities.dex, "modifier": self.dex_modifier},
                "con": {"score": self.abilities.con, "modifier": self.con_modifier},
                "int": {"score": self.abilities.int_, "modifier": self.int_modifier},
                "wis": {"score": self.abilities.wis, "modifier": self.wis_modifier},
                "cha": {"score": self.abilities.cha, "modifier": self.cha_modifier},
            },
            "hp": {"current": self.current_hp, "max": self.max_hp},
            "ac": self.ac,
            "skills": [
                {
                    "name": skill.name,
                    "ability": skill.ability,
                    "proficient": skill.proficient,
                    "modifier": skill.modifier
                }
                for skill in self.skills
            ]
        }

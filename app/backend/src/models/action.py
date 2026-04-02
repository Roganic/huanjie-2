"""Action request and resolution response models."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    """Type of action being performed."""
    GENERIC = "generic"
    ATTACK = "attack"
    SPELL_ATTACK = "spell_attack"  # Attack that may require saving throw
    SKILL_CHECK = "skill_check"    # Skill check (proficiency-based)


class ActionRequest(BaseModel):
    """Minimal player action input."""

    scene_id: str = Field(..., description="Current scene identifier")
    actor: str = Field(..., description="Who is acting")
    intent: str = Field(..., description="What the actor wants to achieve")
    approach: str = Field(..., description="How they attempt it")
    provider: Optional[str] = Field(
        default=None,
        description="Narration provider override (e.g. kimi/openai)",
    )
    action_type: ActionType = Field(
        default=ActionType.GENERIC,
        description="Type of action (generic, attack, or spell_attack)",
    )
    ability: Optional[str] = Field(
        None,
        description="Ability score used for the check (str/dex/con/int/wis/cha)",
    )

    @validator("ability")
    @classmethod
    def ability_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        valid = {"str", "dex", "con", "int", "wis", "cha"}
        if v is not None and v not in valid:
            raise ValueError(
                f"ability must be one of {sorted(valid)}, got '{v}'"
            )
        return v
    dc: Optional[int] = Field(
        None,
        description="Override difficulty class; auto-assigned if omitted",
    )
    advantage: Optional[bool] = Field(
        None,
        description="True = advantage, False = disadvantage, None = normal",
    )
    # Combat-specific fields
    target: Optional[str] = Field(
        None,
        description="Target actor ID or name (for attack actions)",
    )
    weapon: Optional[str] = Field(
        None,
        description="Weapon type being used (e.g., longsword, shortbow)",
    )
    damage_dice: Optional[str] = Field(
        None,
        description="Override damage dice expression (e.g., 1d8, 2d6+1)",
    )
    # Skill check field
    skill: Optional[str] = Field(
        None,
        description="Skill name for skill checks (e.g., athletics, perception, stealth)",
    )
    # Multi-step action fields
    requires_saving_throw: bool = Field(
        default=False,
        description="If true, target must make a saving throw (for spell attacks)",
    )
    saving_throw_ability: Optional[str] = Field(
        None,
        description="Ability for saving throw (str/dex/con/int/wis/cha)",
    )
    saving_throw_dc: Optional[int] = Field(
        None,
        description="DC for saving throw; uses spell DC if omitted",
    )


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ResolutionType(str, Enum):
    AUTO_SUCCESS = "auto_success"
    CHECK = "check"


class Outcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class CheckDetail(BaseModel):
    ability: str
    modifier: int
    proficiency_bonus: int
    advantage: Optional[bool] = None
    roll: int
    total: int
    dc: int
    skill_name: Optional[str] = None  # For skill checks, e.g., "athletics", "perception"


class DamageDetail(BaseModel):
    """Details of damage dealt in an attack."""
    dice_expression: str
    rolls: list[int]
    modifier: int = 0
    total: int


class AttackDetail(BaseModel):
    """Details of an attack resolution."""
    target: str
    weapon: str
    hit_roll: int
    total_attack: int
    target_ac: int
    damage: Optional[DamageDetail] = None


class SavingThrowDetail(BaseModel):
    """Details of a saving throw (for multi-step actions)."""
    target: str
    ability: str
    dc: int
    roll: int
    modifier: int
    total: int
    outcome: Outcome


class SkillCheckDetail(BaseModel):
    """Simplified skill check summary for frontend display."""
    skill: Optional[str] = None
    roll: int
    modifier: int
    total: int
    dc: int
    success: bool


class Effect(BaseModel):
    target: str
    field: str
    delta: Union[int, str]
    description: str


class ActionResponse(BaseModel):
    action_summary: str
    resolution_type: ResolutionType
    check: Optional[CheckDetail] = None
    skill_check: Optional[SkillCheckDetail] = None
    attack: Optional[AttackDetail] = None
    saving_throw: Optional[SavingThrowDetail] = None
    outcome: Outcome
    effects: list[Effect] = Field(default_factory=list)
    narration: str
    scene_progression: str
    gm_prompt: str

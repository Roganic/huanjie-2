"""Action request and resolution response models."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, Field, validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ActionRequest(BaseModel):
    """Minimal player action input."""

    scene_id: str = Field(..., description="Current scene identifier")
    actor: str = Field(..., description="Who is acting")
    intent: str = Field(..., description="What the actor wants to achieve")
    approach: str = Field(..., description="How they attempt it")
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


class Effect(BaseModel):
    target: str
    field: str
    delta: Union[int, str]
    description: str


class ActionResponse(BaseModel):
    action_summary: str
    resolution_type: ResolutionType
    check: Optional[CheckDetail] = None
    outcome: Outcome
    effects: list[Effect] = Field(default_factory=list)
    narration: str

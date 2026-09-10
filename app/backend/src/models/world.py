"""Persistent encounter state, independent of screen layout."""
from pydantic import BaseModel, Field
from .state import Actor


class WorldSceneState(BaseModel):
    enemies: dict[str, Actor] = Field(default_factory=dict)
    dangerous: bool = False
    aggression: bool = False
    rewarded_ids: list[str] = Field(default_factory=list)

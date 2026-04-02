"""Data models for game persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..models.state import (
    Actor,
    AdventurePhase,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
)


class CombatStateData(BaseModel):
    """Combat state snapshot for persistence."""

    combat_id: str = ""
    round_number: int = 0
    turn_index: int = 0
    status: str = "active"  # active, victory, defeat, escaped
    log: list[dict] = Field(default_factory=list)


class SaveData(BaseModel):
    """Complete game save data structure."""

    version: int = 1
    saved_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    save_id: str = ""  # Unique save ID (filename without extension)
    save_name: str = ""  # Display name for the save
    session_id: str = ""
    phase: GamePhase = GamePhase.CHARACTER_CREATION
    game_phase: AdventurePhase = AdventurePhase.EXPLORATION
    character: Actor | None = None
    enemy: Actor | None = None
    scene: Scene | None = None
    combat_state: CombatStateData | None = None
    action_history: list[NarrativeHistoryEntry] = Field(default_factory=list)
    scene_history: list[SceneHistoryEntry] = Field(default_factory=list)


class SaveSummary(BaseModel):
    """Summary of a save file for listing."""

    save_id: str
    save_name: str
    character_name: str | None = None
    character_class: str | None = None
    character_level: int | None = None
    hp: int | None = None
    hp_max: int | None = None
    scene_name: str | None = None
    saved_at: str

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override model_dump to handle the reserved 'class' keyword."""
        data = super().model_dump(**kwargs)
        # Handle class field separately to avoid issues with 'class' keyword
        if hasattr(self, 'character_class'):
            data['class'] = self.character_class
            del data['character_class']
        return data

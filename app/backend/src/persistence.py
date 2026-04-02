"""Game session persistence module for saving/loading game state to local JSON file."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .models.state import (
    AbilityScores,
    Actor,
    AdventurePhase,
    BootstrapState,
    CharacterClass,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
    Skill,
)


# Default save file path (can be overridden via environment variable)
DEFAULT_SAVE_PATH = Path(__file__).parent.parent / "saves" / "session.json"
SAVE_FILE_PATH = Path(os.getenv("SAVE_FILE_PATH", DEFAULT_SAVE_PATH))


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
    session_id: str = ""
    phase: GamePhase = GamePhase.CHARACTER_CREATION
    game_phase: AdventurePhase = AdventurePhase.EXPLORATION
    character: Actor | None = None
    enemy: Actor | None = None
    scene: Scene | None = None
    combat_state: CombatStateData | None = None
    action_history: list[NarrativeHistoryEntry] = Field(default_factory=list)
    scene_history: list[SceneHistoryEntry] = Field(default_factory=list)


def get_save_file_path() -> Path:
    """Get the configured save file path."""
    path = SAVE_FILE_PATH
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def has_save_file() -> bool:
    """Check if a save file exists."""
    return get_save_file_path().exists()


def save_game(
    session_id: str,
    phase: GamePhase,
    game_phase: AdventurePhase,
    character: Actor | None,
    enemy: Actor | None,
    scene: Scene,
    combat_state: CombatStateData | None,
    action_history: list[NarrativeHistoryEntry],
    scene_history: list[SceneHistoryEntry],
) -> dict[str, Any]:
    """Save the current game state to the save file.
    
    Returns:
        Dict with save metadata including timestamp.
    """
    save_data = SaveData(
        saved_at=datetime.now().isoformat(),
        session_id=session_id,
        phase=phase,
        game_phase=game_phase,
        character=character,
        enemy=enemy,
        scene=scene,
        combat_state=combat_state,
        action_history=action_history,
        scene_history=scene_history,
    )
    
    save_path = get_save_file_path()
    save_path.write_text(
        json.dumps(save_data.model_dump(mode="json", by_alias=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    return {
        "success": True,
        "timestamp": save_data.saved_at,
        "path": str(save_path),
    }


def load_game() -> SaveData | None:
    """Load game state from the save file.
    
    Returns:
        SaveData if save exists and is valid, None otherwise.
    """
    save_path = get_save_file_path()
    if not save_path.exists():
        return None
    
    try:
        data = json.loads(save_path.read_text(encoding="utf-8"))
        return SaveData.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        # Invalid save file, remove it
        save_path.unlink(missing_ok=True)
        return None


def clear_save() -> bool:
    """Delete the save file if it exists.
    
    Returns:
        True if file was deleted, False if it didn't exist.
    """
    save_path = get_save_file_path()
    if save_path.exists():
        save_path.unlink()
        return True
    return False


def create_fresh_character_creation_scene() -> Scene:
    """Create the initial character creation scene."""
    return Scene(
        id="character-creation-01",
        name="命运启程",
        description="你站在冒险开始前的门槛上。先决定自己的姓名、道路与天赋，随后故事才会真正展开。",
        actors=[],
        time=0,
    )


def create_fresh_adventure_scene() -> Scene:
    """Create the initial adventure scene."""
    from .models.state import SceneExit
    return Scene(
        id="tavern-01",
        name="锈迹斑斑的灯笼酒馆",
        description="十字路口村庄的一家昏暗酒馆。陈年麦酒的气味混合着木柴烟雾。几个当地人默默地喝着酒。",
        actors=[],
        time=0,
        exits=[
            SceneExit(direction="村庄广场", target_scene_id="village-square-01"),
            SceneExit(direction="森林入口", target_scene_id="dungeon-entrance-01"),
        ],
    )

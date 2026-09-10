"""Persistence manager for game save/load operations."""

from __future__ import annotations

import json
import os
import re
import uuid
import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..models.state import (
    Actor,
    AdventurePhase,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
)
from .models import CombatStateData, SaveData, SaveSummary

# Default save directory (can be overridden via environment variable)
DEFAULT_SAVE_DIR = Path(__file__).parent.parent.parent / "saves"
SAVE_DIR = Path(os.getenv("SAVE_DIR", DEFAULT_SAVE_DIR))
DEFAULT_SAVE_FILENAME = "session.json"

# Valid save ID pattern (alphanumeric, dash, underscore)
SAVE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _ensure_save_dir() -> Path:
    """Ensure save directory exists."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    return SAVE_DIR


def _generate_save_id() -> str:
    """Generate a unique save ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = uuid.uuid4().hex[:6]
    return f"save_{timestamp}_{random_suffix}"


def _get_save_path(save_id: str | None = None) -> Path:
    """Get the file path for a save.
    
    Args:
        save_id: Save ID. If None, uses the default save file.
        
    Returns:
        Path to the save file.
    """
    _ensure_save_dir()
    if save_id is None:
        return SAVE_DIR / DEFAULT_SAVE_FILENAME
    return SAVE_DIR / f"{save_id}.json"


def _is_valid_save_id(save_id: str) -> bool:
    """Check if a save ID is valid."""
    if not save_id:
        return False
    return bool(SAVE_ID_PATTERN.match(save_id))


def get_save_file_path(save_id: str | None = None) -> Path:
    """Get the configured save file path.
    
    Args:
        save_id: Optional save ID. If None, returns default save path.
        
    Returns:
        Path to the save file.
    """
    return _get_save_path(save_id)


def get_save_path_by_id(save_id: str) -> Path | None:
    """Get the file path for a save ID if it exists.
    
    Args:
        save_id: Save ID to look up.
        
    Returns:
        Path if save exists, None otherwise.
    """
    if not _is_valid_save_id(save_id):
        return None
    path = _get_save_path(save_id)
    return path if path.exists() else None


def has_save_file(save_id: str | None = None) -> bool:
    """Check if a save file exists.
    
    Args:
        save_id: Optional save ID. If None, checks default save.
        
    Returns:
        True if save file exists, False otherwise.
    """
    return _get_save_path(save_id).exists()


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
    """Save the current game state to the default save file.
    
    This maintains backward compatibility with existing code.
    
    Returns:
        Dict with save metadata including timestamp.
    """
    return save_game_with_id(
        save_id=None,  # Uses default save
        save_name="",
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


def save_game_with_id(
    save_id: str | None,
    save_name: str,
    session_id: str,
    phase: GamePhase,
    game_phase: AdventurePhase,
    character: Actor | None,
    enemy: Actor | None,
    scene: Scene,
    combat_state: CombatStateData | None,
    action_history: list[NarrativeHistoryEntry],
    scene_history: list[SceneHistoryEntry],
    session_snapshot: dict[str, Any] | None = None,
    combat_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Save the current game state to a specific save file.
    
    Args:
        save_id: Save ID. If None, uses default save.
        save_name: Display name for the save.
        session_id: Session ID.
        phase: Game phase.
        game_phase: Adventure phase.
        character: Player character.
        enemy: Enemy actor.
        scene: Current scene.
        combat_state: Combat state data.
        action_history: Narrative history.
        scene_history: Scene history.
        
    Returns:
        Dict with save metadata including timestamp.
    """
    # Generate save_id if not provided
    if save_id is None:
        save_id = _generate_save_id()
    
    save_data = SaveData(
        version=2 if session_snapshot is not None else 1,
        saved_at=datetime.now().isoformat(),
        save_id=save_id,
        save_name=save_name or f"存档 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        session_id=session_id,
        phase=phase,
        game_phase=game_phase,
        character=character,
        enemy=enemy,
        scene=scene,
        combat_state=combat_state,
        action_history=action_history,
        scene_history=scene_history,
        session_snapshot=session_snapshot,
        combat_snapshot=combat_snapshot,
    )
    
    save_path = _get_save_path(save_id)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=save_path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(save_data.model_dump(mode="json", by_alias=True), stream, ensure_ascii=False, indent=2)
        os.replace(temporary, save_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    
    return {
        "success": True,
        "save_id": save_id,
        "save_name": save_data.save_name,
        "timestamp": save_data.saved_at,
        "path": str(save_path),
    }


def load_game(save_id: str | None = None) -> SaveData | None:
    """Load game state from a save file.
    
    Args:
        save_id: Save ID. If None, loads from default save.
        
    Returns:
        SaveData if save exists and is valid, None otherwise.
    """
    if save_id is not None and not _is_valid_save_id(save_id):
        raise ValueError("Invalid save ID")
    save_path = _get_save_path(save_id)
    if save_id is None and not save_path.exists():
        saves = list_saves()
        if saves:
            save_path = _get_save_path(saves[0].save_id)
    if not save_path.exists():
        return None
    
    try:
        data = json.loads(save_path.read_text(encoding="utf-8"))
        return SaveData.model_validate(data)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError("存档损坏或格式不兼容。") from e


def load_game_by_id(save_id: str) -> SaveData | None:
    """Load game state from a specific save ID.
    
    Args:
        save_id: Save ID to load.
        
    Returns:
        SaveData if save exists and is valid, None otherwise.
    """
    if not _is_valid_save_id(save_id):
        return None
    return load_game(save_id)


def list_saves() -> list[SaveSummary]:
    """List all available saves.
    
    Returns:
        List of save summaries, sorted by save time (newest first).
    """
    _ensure_save_dir()
    saves = []
    
    for file_path in SAVE_DIR.glob("*.json"):
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            save_data = SaveData.model_validate(data)
            
            # Extract character info
            character = save_data.character
            scene = save_data.scene
            
            saves.append(SaveSummary(
                save_id=save_data.save_id or file_path.stem,
                save_name=save_data.save_name or file_path.stem,
                character_name=character.name if character else None,
                character_class=character.character_class.value if character and character.character_class else None,
                character_level=character.level if character else None,
                hp=character.hp if character else None,
                hp_max=character.hp_max if character else None,
                scene_name=scene.name if scene else None,
                saved_at=save_data.saved_at,
            ))
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # Skip invalid save files
            print(f"[Persistence] Skipping invalid save file {file_path.name}: {e}")
            continue
    
    # Sort by saved_at (newest first)
    saves.sort(key=lambda x: x.saved_at, reverse=True)
    return saves


def delete_save(save_id: str) -> bool:
    """Delete a save file.
    
    Args:
        save_id: Save ID to delete.
        
    Returns:
        True if file was deleted, False if it didn't exist or was invalid.
    """
    if not _is_valid_save_id(save_id):
        return False
    
    save_path = _get_save_path(save_id)
    if save_path.exists():
        save_path.unlink()
        return True
    return False


def clear_save(save_id: str | None = None) -> bool:
    """Delete the save file if it exists.
    
    Args:
        save_id: Optional save ID. If None, clears default save.
        
    Returns:
        True if file was deleted, False if it didn't exist.
    """
    save_path = _get_save_path(save_id)
    if save_path.exists():
        save_path.unlink()
        return True
    return False


def reset_session(session_id: str) -> dict[str, Any]:
    """Clear the save file and return initial state info.
    
    This is used when the player wants to start a completely new game.
    It clears the save file and returns the session to character creation phase.
    
    Args:
        session_id: The session ID to reset.
        
    Returns:
        Dict with reset status and initial phase.
    """
    from ..models.state import GamePhase, AdventurePhase
    
    # Resetting live progress does not delete manual saves or another session's legacy save.
    was_deleted = False
    legacy_path = _get_save_path()
    if legacy_path.exists():
        try:
            legacy = SaveData.model_validate_json(legacy_path.read_text(encoding="utf-8"))
            if legacy.session_id == session_id:
                was_deleted = clear_save()
        except ValueError:
            pass

    
    return {
        "success": True,
        "session_id": session_id,
        "phase": GamePhase.CHARACTER_CREATION.value,
        "game_phase": AdventurePhase.EXPLORATION.value,
        "save_file_deleted": was_deleted,
    }


def get_save_info(save_id: str | None = None) -> dict[str, Any] | None:
    """Get information about a saved game if it exists.
    
    Args:
        save_id: Optional save ID. If None, gets info for default save.
        
    Returns:
        Dict with save metadata if save exists, None otherwise.
    """
    save_data = load_game(save_id)
    if save_data is None:
        return None
    
    return {
        "save_id": save_data.save_id,
        "save_name": save_data.save_name,
        "saved_at": save_data.saved_at,
        "session_id": save_data.session_id,
        "phase": save_data.phase.value,
        "game_phase": save_data.game_phase.value,
        "has_character": save_data.character is not None,
        "character_name": save_data.character.name if save_data.character else None,
        "character_class": save_data.character.character_class.value if save_data.character and save_data.character.character_class else None,
        "character_level": save_data.character.level if save_data.character else None,
        "hp": save_data.character.hp if save_data.character else None,
        "hp_max": save_data.character.hp_max if save_data.character else None,
        "scene_name": save_data.scene.name if save_data.scene else None,
    }


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
    from ..scenes.data import SceneExit
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

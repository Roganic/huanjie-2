"""Save/Load manager: core persistence logic for game state.

Save files are stored in app/backend/saves/ as JSON.
Each save file contains character, scene, inventory, and map_state.
Max 3 save slots; oldest is overwritten when full.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
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

# Save directory: app/backend/saves/
_BACKEND_DIR = Path(__file__).parent.parent.parent
SAVE_DIR = _BACKEND_DIR / "saves"
MAX_SAVE_SLOTS = 3


class SaveLoadError(Exception):
    """Base error for save/load operations."""


class CombatSaveError(SaveLoadError):
    """Raised when trying to save during combat."""


def get_save_dir() -> Path:
    """Return the save directory, creating it if needed."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    return SAVE_DIR


def _save_file_path(save_id: str) -> Path:
    return get_save_dir() / f"{save_id}.json"


def _generate_save_id() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"save_{ts}_{suffix}"


def _read_save_file(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_save_files() -> list[dict[str, Any]]:
    """Return all valid save summaries sorted by timestamp (newest first).

    Each entry contains: id, timestamp, character_name, level, current_scene.
    """
    saves = []
    for path in get_save_dir().glob("*.json"):
        data = _read_save_file(path)
        if data is None:
            continue
        saves.append({
            "id": data.get("save_id", path.stem),
            "timestamp": data.get("saved_at", ""),
            "character_name": (data.get("character") or {}).get("name"),
            "level": (data.get("character") or {}).get("level"),
            "current_scene": (data.get("scene") or {}).get("name"),
            # Keep extra metadata for internal use
            "_path": str(path),
            "_saved_at": data.get("saved_at", ""),
        })
    saves.sort(key=lambda x: x["_saved_at"], reverse=True)
    # Strip internal keys before returning
    return [
        {k: v for k, v in s.items() if not k.startswith("_")}
        for s in saves
    ]


def _purge_oldest_if_needed() -> None:
    """If >= MAX_SAVE_SLOTS saves exist, delete the oldest one."""
    paths = sorted(
        get_save_dir().glob("*.json"),
        key=lambda p: (_read_save_file(p) or {}).get("saved_at", ""),
    )
    while len(paths) >= MAX_SAVE_SLOTS:
        paths[0].unlink(missing_ok=True)
        paths = paths[1:]


def save_game_state(
    session_id: str,
    game_phase: AdventurePhase,
    phase: GamePhase,
    character: Actor | None,
    scene: Scene | None,
    explored_nodes: list[str],
    narrative_history: list[NarrativeHistoryEntry],
    scene_history: list[SceneHistoryEntry],
    enemy: Actor | None = None,
    save_name: str = "",
) -> dict[str, Any]:
    """Persist the current game state to a new save file.

    Raises CombatSaveError if game_phase is COMBAT.
    Returns metadata dict: save_id, timestamp, path.
    """
    if game_phase == AdventurePhase.COMBAT:
        raise CombatSaveError("战斗中无法存档")

    _purge_oldest_if_needed()

    save_id = _generate_save_id()
    now = datetime.now(timezone.utc).isoformat()

    # Build canonical save document
    doc: dict[str, Any] = {
        "version": 1,
        "save_id": save_id,
        "save_name": save_name or f"存档 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "saved_at": now,
        "session_id": session_id,
        "phase": phase.value if hasattr(phase, "value") else phase,
        "game_phase": game_phase.value if hasattr(game_phase, "value") else game_phase,
        # Required top-level fields per acceptance criteria
        "character": character.model_dump(mode="json") if character else None,
        "scene": scene.model_dump(mode="json", by_alias=True) if scene else None,
        "inventory": (
            [item.model_dump(mode="json") for item in character.inventory]
            if character
            else []
        ),
        "map_state": {
            "explored_nodes": explored_nodes,
        },
        # Additional state for full restoration
        "enemy": enemy.model_dump(mode="json") if enemy else None,
        "narrative_history": [e.model_dump(mode="json") for e in narrative_history],
        "scene_history": [e.model_dump(mode="json") for e in scene_history],
    }

    path = _save_file_path(save_id)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "success": True,
        "save_id": save_id,
        "save_name": doc["save_name"],
        "timestamp": now,
        "path": str(path),
    }


def load_game_state(save_id: str) -> dict[str, Any]:
    """Load a save file by ID.

    Returns the raw save document dict.
    Raises SaveLoadError if not found or invalid.
    """
    path = _save_file_path(save_id)
    if not path.exists():
        raise SaveLoadError(f"存档不存在: {save_id}")
    data = _read_save_file(path)
    if data is None:
        raise SaveLoadError(f"存档文件损坏: {save_id}")
    return data

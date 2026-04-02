"""Save/Load system for game state persistence.

This module provides the core save/load functionality:
- Save game state to JSON files in app/backend/saves/
- Load game state from save files
- List available saves
- Enforce save constraints (no saving during combat)
- Manage save slots (max 3, overwrite oldest when full)
"""

from .manager import (
    SaveLoadError,
    CombatSaveError,
    save_game_state,
    load_game_state,
    list_save_files,
    get_save_dir,
    MAX_SAVE_SLOTS,
)

__all__ = [
    "SaveLoadError",
    "CombatSaveError",
    "save_game_state",
    "load_game_state",
    "list_save_files",
    "get_save_dir",
    "MAX_SAVE_SLOTS",
]

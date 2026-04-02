"""Game session persistence module for saving/loading game state to local JSON files.

This module provides multi-save support with automatic persistence to local JSON files.
Each save is stored as a separate file in the saves directory.
"""

from __future__ import annotations

from .models import CombatStateData, SaveData, SaveSummary
from .manager import (
    clear_save,
    create_fresh_adventure_scene,
    create_fresh_character_creation_scene,
    delete_save,
    get_save_file_path,
    get_save_info,
    get_save_path_by_id,
    has_save_file,
    list_saves,
    load_game,
    load_game_by_id,
    reset_session,
    save_game,
    save_game_with_id,
)

__all__ = [
    "CombatStateData",
    "SaveData",
    "SaveSummary",
    "clear_save",
    "create_fresh_adventure_scene",
    "create_fresh_character_creation_scene",
    "delete_save",
    "get_save_file_path",
    "get_save_info",
    "get_save_path_by_id",
    "has_save_file",
    "list_saves",
    "load_game",
    "load_game_by_id",
    "reset_session",
    "save_game",
    "save_game_with_id",
]

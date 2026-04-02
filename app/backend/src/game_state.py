"""Game state management with persistence support.

This module provides high-level functions for managing game state
with automatic persistence to local JSON file.
"""

from __future__ import annotations

from typing import Any

from . import persistence
from .models.state import (
    Actor,
    AdventurePhase,
    BootstrapState,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
)
from .persistence.models import CombatStateData, SaveSummary
from .state import (
    SessionData,
    _bootstrap_from_session,
    _create_fresh_session,
    _get_session,
    _resolve_session_id,
    _SESSION_LOCK,
    _save_session,
    create_session,
    get_bootstrap_state,
    reset_state,
)


def save_current_game(session_id: str | None = None, save_name: str = "") -> dict[str, Any]:
    """Save the current game state to a new save file.
    
    Args:
        session_id: Optional session ID to save. Uses current session if not provided.
        save_name: Optional display name for the save.
        
    Returns:
        Dict with save metadata including save_id, timestamp, etc.
    """
    resolved_session_id = _resolve_session_id(session_id)
    
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        
        # Build combat state data if in combat
        combat_state_data = None
        if session.game_phase == AdventurePhase.COMBAT:
            combat_state_data = CombatStateData(
                combat_id="combat-01",
                round_number=1,
                turn_index=0,
                status="active",
            )
        
        return persistence.save_game_with_id(
            save_id=None,  # Auto-generate save_id
            save_name=save_name,
            session_id=session.session_id,
            phase=session.phase,
            game_phase=session.game_phase,
            character=session.actor,
            enemy=session.enemy,
            scene=session.scene,
            combat_state=combat_state_data,
            action_history=list(session.narrative_history),
            scene_history=list(session.scene_history),
        )


def load_saved_game(save_id: str | None = None) -> BootstrapState | None:
    """Load game from save file and restore session state.
    
    Args:
        save_id: Optional save ID to load. If None, loads the most recent save.
        
    Also copies the saved state to the default session so that
    clients without a session_id will get the saved state.
    
    Returns:
        BootstrapState if save exists and was loaded successfully, None otherwise.
    """
    # If no save_id specified, try to load the default save or most recent
    save_data = persistence.load_game(save_id)
    if save_data is None:
        return None
    
    with _SESSION_LOCK:
        # Restore to the saved session
        session = _get_session(save_data.session_id, create_if_missing=True)
        session.phase = save_data.phase
        session.game_phase = save_data.game_phase
        session.actor = save_data.character
        session.enemy = save_data.enemy
        session.scene = save_data.scene if save_data.scene else persistence.create_fresh_character_creation_scene()
        session.narrative_history = save_data.action_history
        session.scene_history = save_data.scene_history
        # Initialize visited_scenes from loaded scene if not present in save
        if session.scene and session.scene.id:
            session.visited_scenes = {session.scene.id: session.scene.visited_count}
        _save_session(session)
        
        # Also copy to default session so clients without session_id get the saved state
        from .state import DEFAULT_SESSION_ID
        default_session = _get_session(DEFAULT_SESSION_ID, create_if_missing=True)
        default_session.phase = save_data.phase
        default_session.game_phase = save_data.game_phase
        default_session.actor = save_data.character
        default_session.enemy = save_data.enemy
        default_session.scene = save_data.scene if save_data.scene else persistence.create_fresh_character_creation_scene()
        default_session.narrative_history = save_data.action_history
        default_session.scene_history = save_data.scene_history
        if default_session.scene and default_session.scene.id:
            default_session.visited_scenes = {default_session.scene.id: default_session.scene.visited_count}
        _save_session(default_session)
    
    return get_bootstrap_state(session_id=save_data.session_id)


def load_game_by_id(save_id: str) -> BootstrapState | None:
    """Load a specific save by ID.
    
    Args:
        save_id: The save ID to load.
        
    Returns:
        BootstrapState if save exists and was loaded successfully, None otherwise.
    """
    return load_saved_game(save_id)


def reset_and_clear_save(session_id: str | None = None) -> BootstrapState:
    """Reset game state and clear the save file.
    
    Args:
        session_id: Optional session ID to reset. Uses current session if not provided.
        
    Returns:
        Fresh BootstrapState after reset.
    """
    # Clear the save file
    persistence.clear_save()
    
    # Reset the session state
    return reset_state(session_id=session_id)


def has_saved_game() -> bool:
    """Check if a saved game exists.
    
    Returns:
        True if save file exists, False otherwise.
    """
    return persistence.has_save_file()


def get_save_info(save_id: str | None = None) -> dict[str, Any] | None:
    """Get information about the saved game if it exists.
    
    Args:
        save_id: Optional save ID. If None, gets info for default save.
        
    Returns:
        Dict with save metadata if save exists, None otherwise.
    """
    return persistence.get_save_info(save_id)


def list_all_saves() -> list[SaveSummary]:
    """List all available saves.
    
    Returns:
        List of save summaries, sorted by save time (newest first).
    """
    return persistence.list_saves()


def delete_save_by_id(save_id: str) -> bool:
    """Delete a specific save.
    
    Args:
        save_id: The save ID to delete.
        
    Returns:
        True if save was deleted, False otherwise.
    """
    return persistence.delete_save(save_id)


def try_auto_load_on_startup() -> BootstrapState | None:
    """Try to load saved game on server startup.
    
    Also copies the saved state to the default session so that
    clients without a session_id will get the saved state.
    
    Returns:
        BootstrapState if save was loaded, None if no save exists.
    """
    if not persistence.has_save_file():
        return None
    
    save_data = persistence.load_game()
    if save_data is None:
        return None
    
    with _SESSION_LOCK:
        # Restore to the saved session
        saved_session = _get_session(save_data.session_id, create_if_missing=True)
        saved_session.phase = save_data.phase
        saved_session.game_phase = save_data.game_phase
        saved_session.actor = save_data.character
        saved_session.enemy = save_data.enemy
        saved_session.scene = save_data.scene if save_data.scene else persistence.create_fresh_character_creation_scene()
        saved_session.narrative_history = save_data.action_history
        saved_session.scene_history = save_data.scene_history
        _save_session(saved_session)
        
        # Also copy to default session so clients without session_id get the saved state
        from .state import DEFAULT_SESSION_ID
        default_session = _get_session(DEFAULT_SESSION_ID, create_if_missing=True)
        default_session.phase = save_data.phase
        default_session.game_phase = save_data.game_phase
        default_session.actor = save_data.character
        default_session.enemy = save_data.enemy
        default_session.scene = save_data.scene if save_data.scene else persistence.create_fresh_character_creation_scene()
        default_session.narrative_history = save_data.action_history
        default_session.scene_history = save_data.scene_history
        _save_session(default_session)
    
    return _bootstrap_from_session(saved_session)

"""Game state management with persistence support.

This module provides high-level functions for managing game state
with automatic persistence to local JSON file.
"""

from __future__ import annotations

from typing import Any
from contextvars import ContextVar
import uuid

DEFER_AUTOSAVE = ContextVar("defer_autosave", default=False)

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


def save_current_game(session_id: str | None = None, save_name: str = "", *, automatic: bool = False) -> dict[str, Any]:
    """Save the current game state to a new save file.
    
    Args:
        session_id: Optional session ID to save. Uses current session if not provided.
        save_name: Optional display name for the save.
        
    Returns:
        Dict with save metadata including save_id, timestamp, etc.
    """
    if automatic and DEFER_AUTOSAVE.get():
        return {"deferred": True}
    resolved_session_id = _resolve_session_id(session_id)
    
    with _SESSION_LOCK:
        session = _get_session(resolved_session_id, create_if_missing=True)
        
        from routes.combat import _get_combat_state
        live_combat = _get_combat_state(resolved_session_id)
        combat_state_data = CombatStateData.model_validate(live_combat.model_dump(mode="json")) if live_combat else None
        return persistence.save_game_with_id(
            save_id=f"auto_{uuid.uuid5(uuid.NAMESPACE_URL, resolved_session_id).hex}" if automatic else None,
            save_name="自动存档 · " + (session.actor.name if session.actor else "准备冒险") if automatic else save_name,
            session_id=session.session_id,
            phase=session.phase,
            game_phase=session.game_phase,
            character=session.actor,
            enemy=session.enemy,
            scene=session.scene,
            combat_state=combat_state_data,
            action_history=list(session.narrative_history),
            scene_history=list(session.scene_history),
            session_snapshot=session.model_dump(mode="json", by_alias=True),
            combat_snapshot=live_combat.model_dump(mode="json") if live_combat else None,
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
    
    from .state import _sessions, DEFAULT_SESSION_ID
    from routes.combat import CombatState, _set_combat_state, _clear_combat_state

    # Validate the entire snapshot before replacing any live state.
    if save_data.session_snapshot is not None:
        restored = SessionData.model_validate(save_data.session_snapshot)
        if restored.session_id != save_data.session_id:
            raise ValueError("存档会话信息不一致")
    else:
        restored = SessionData(
            session_id=save_data.session_id,
            phase=save_data.phase,
            game_phase=save_data.game_phase,
            actor=save_data.character,
            enemy=save_data.enemy or _create_fresh_session(save_data.session_id).enemy,
            scene=save_data.scene or persistence.create_fresh_character_creation_scene(),
            narrative_history=save_data.action_history,
            scene_history=save_data.scene_history,
            explored_nodes=[save_data.scene.id] if save_data.scene else [],
        )
    combat = CombatState.model_validate(save_data.combat_snapshot) if save_data.combat_snapshot else None
    if restored.game_phase == AdventurePhase.COMBAT and combat is None:
        # Legacy saves do not contain enough information to resume combat.
        restored.game_phase = AdventurePhase.EXPLORATION

    with _SESSION_LOCK:
        for sid in {restored.session_id, DEFAULT_SESSION_ID}:
            copy = restored.model_copy(deep=True, update={"session_id": sid})
            _sessions[sid] = copy
            _save_session(copy)
            _clear_combat_state(sid)
            if combat is not None:
                _set_combat_state(sid, combat.model_copy(deep=True))
    return get_bootstrap_state(session_id=restored.session_id)


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
    persistence.reset_session(_resolve_session_id(session_id))
    
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
    # A persisted default adventure is independent of other named saves. Never
    # replace it implicitly just because another adventure was saved later.
    from .state import _load_session, _sessions, DEFAULT_SESSION_ID
    current_default = _load_session(DEFAULT_SESSION_ID)
    if current_default is not None and current_default.actor is not None:
        with _SESSION_LOCK:
            _sessions[DEFAULT_SESSION_ID] = current_default
        return get_bootstrap_state(DEFAULT_SESSION_ID)
    # Automatic startup resumes the latest live session; it must not roll back
    # a newly started encounter to an older manual/automatic save.
    try:
        saved = persistence.load_game()
    except ValueError:
        return None
    if saved is not None:
        from .state import _load_session, _sessions, DEFAULT_SESSION_ID
        current = _load_session(saved.session_id)
        snapshot_time = (saved.session_snapshot or {}).get("updated_at", 0)
        if current is not None and current.actor is not None and current.updated_at >= snapshot_time:
            with _SESSION_LOCK:
                for sid in {current.session_id, DEFAULT_SESSION_ID}:
                    restored = current.model_copy(deep=True, update={"session_id": sid})
                    _sessions[sid] = restored
                    _save_session(restored)
            return get_bootstrap_state(current.session_id)
    return load_saved_game()

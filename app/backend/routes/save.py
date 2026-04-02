"""Save/Load API routes.

Endpoints:
  POST /save              – save current game state (blocked during combat)
  GET  /saves             – list all save files
  POST /load/{save_id}    – restore game state from a specific save
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.models.state import (
    Actor,
    AdventurePhase,
    GamePhase,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
)
from src.save_load import (
    CombatSaveError,
    SaveLoadError,
    list_save_files,
    load_game_state,
    save_game_state,
)
from src.state import (
    DEFAULT_SESSION_ID,
    _SESSION_LOCK,
    _get_session,
    _resolve_session_id,
    _save_session,
    get_bootstrap_state,
    get_explored_nodes,
)

router = APIRouter(tags=["save-load"])


def _get_session_id(request: Request) -> str:
    sid = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    return sid if sid else DEFAULT_SESSION_ID


# ---------------------------------------------------------------------------
# POST /save
# ---------------------------------------------------------------------------

@router.post("/save")
async def save_game(request: Request):
    """Save the current game state.

    Returns 400 if called during combat.
    """
    session_id = _get_session_id(request)

    save_name = ""
    try:
        body = await request.json()
        if isinstance(body, dict):
            save_name = body.get("save_name", "")
    except Exception:
        pass

    with _SESSION_LOCK:
        session = _get_session(session_id, create_if_missing=True)
        try:
            result = save_game_state(
                session_id=session.session_id,
                game_phase=session.game_phase,
                phase=session.phase,
                character=session.actor,
                scene=session.scene,
                explored_nodes=list(session.explored_nodes),
                narrative_history=list(session.narrative_history),
                scene_history=list(session.scene_history),
                enemy=session.enemy,
                save_name=save_name,
            )
        except CombatSaveError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except SaveLoadError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result


# ---------------------------------------------------------------------------
# GET /saves
# ---------------------------------------------------------------------------

@router.get("/saves")
async def list_saves():
    """Return all save file summaries.

    Each entry: id, timestamp, character_name, level, current_scene.
    """
    saves = list_save_files()
    return {"saves": saves, "total": len(saves)}


# ---------------------------------------------------------------------------
# POST /load/{save_id}
# ---------------------------------------------------------------------------

@router.post("/load/{save_id}")
async def load_save(save_id: str, request: Request):
    """Restore game state from a specific save file.

    After loading, GET /state and GET /map reflect the saved state.
    """
    try:
        data = load_game_state(save_id)
    except SaveLoadError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Restore session state
    restored_session_id = data.get("session_id") or DEFAULT_SESSION_ID

    with _SESSION_LOCK:
        # Restore to the saved session
        session = _get_session(restored_session_id, create_if_missing=True)
        _apply_save_data_to_session(session, data)
        _save_session(session)

        # Also mirror to default session so header-less clients work
        if restored_session_id != DEFAULT_SESSION_ID:
            default_session = _get_session(DEFAULT_SESSION_ID, create_if_missing=True)
            _apply_save_data_to_session(default_session, data)
            _save_session(default_session)

    return get_bootstrap_state(session_id=restored_session_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apply_save_data_to_session(session, data: dict) -> None:
    """Populate a SessionData object from a raw save document."""
    from src.persistence.manager import create_fresh_character_creation_scene

    # Phase
    try:
        session.phase = GamePhase(data["phase"])
    except (KeyError, ValueError):
        session.phase = GamePhase.CHARACTER_CREATION

    try:
        session.game_phase = AdventurePhase(data["game_phase"])
    except (KeyError, ValueError):
        session.game_phase = AdventurePhase.EXPLORATION

    # Character
    char_data = data.get("character")
    if char_data:
        try:
            session.actor = Actor.model_validate(char_data)
        except Exception:
            session.actor = None
    else:
        session.actor = None

    # Scene
    scene_data = data.get("scene")
    if scene_data:
        try:
            session.scene = Scene.model_validate(scene_data)
        except Exception:
            session.scene = create_fresh_character_creation_scene()
    else:
        session.scene = create_fresh_character_creation_scene()

    # Map state: explored_nodes
    map_state = data.get("map_state") or {}
    session.explored_nodes = list(map_state.get("explored_nodes", []))

    # Enemy
    enemy_data = data.get("enemy")
    if enemy_data:
        try:
            from src.models.state import Actor as _Actor
            session.enemy = _Actor.model_validate(enemy_data)
        except Exception:
            pass

    # History
    raw_narrative = data.get("narrative_history", [])
    try:
        session.narrative_history = [
            NarrativeHistoryEntry.model_validate(e) for e in raw_narrative
        ]
    except Exception:
        session.narrative_history = []

    raw_scene = data.get("scene_history", [])
    try:
        session.scene_history = [
            SceneHistoryEntry.model_validate(e) for e in raw_scene
        ]
    except Exception:
        session.scene_history = []

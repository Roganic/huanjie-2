"""幻界 2.0 后端入口"""

import os

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from . import game_state as gs
from .models.state import BootstrapState
from .state import get_bootstrap_state, has_character


def _get_allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins = [origin.strip() for origin in configured.split(",") if origin.strip()]
    if origins:
        return origins
    return ["http://localhost:5173"]


app = FastAPI(title="幻界 2.0", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_origin_regex=r"https://.*\.github\.io",
    allow_methods=["*"],
    allow_headers=["*"],
)


# Define persistence endpoints BEFORE including routers
# This ensures these endpoints take precedence over any in routers
@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}


@app.post("/save")
async def save_game(request: Request):
    """Save the current game state to a new save file.
    
    Request body (optional):
        - save_name: Display name for the save
    
    Returns:
        JSON with success status, save_id, timestamp, and file path.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    
    # Parse optional request body
    save_name = ""
    try:
        body = await request.json()
        if body and isinstance(body, dict):
            save_name = body.get("save_name", "")
    except Exception:
        # No body or invalid body is fine
        pass
    
    try:
        result = gs.save_current_game(session_id=session_id, save_name=save_name)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save game: {str(exc)}") from exc


@app.get("/saves")
async def list_saves():
    """List all available save files.
    
    Returns:
        JSON with list of saves, each containing:
        - save_id: Unique save identifier
        - save_name: Display name
        - character_name: Character name if exists
        - class: Character class if exists
        - character_level: Character level if exists
        - hp: Current HP if exists
        - hp_max: Max HP if exists
        - scene_name: Current scene name if exists
        - saved_at: ISO timestamp
    """
    try:
        saves = gs.list_all_saves()
        # Convert to dict, handling the 'class' field properly
        saves_list = []
        for save in saves:
            save_dict = {
                "save_id": save.save_id,
                "save_name": save.save_name,
                "character_name": save.character_name,
                "class": save.character_class,
                "character_level": save.character_level,
                "hp": save.hp,
                "hp_max": save.hp_max,
                "scene_name": save.scene_name,
                "saved_at": save.saved_at,
            }
            saves_list.append(save_dict)
        return {"saves": saves_list, "total": len(saves_list)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list saves: {str(exc)}") from exc


@app.post("/load")
async def load_game(request: Request):
    """Load game state from a save file.
    
    Request body (optional):
        - save_id: Save ID to load. If not provided, loads the default/most recent save.
    
    Returns:
        BootstrapState if save exists and was loaded successfully.
        
    Raises:
        HTTPException 400: If save file is corrupted or invalid.
        HTTPException 404: If no save file found.
    """
    # Parse optional request body for save_id
    save_id = None
    try:
        body = await request.json()
        if body and isinstance(body, dict):
            save_id = body.get("save_id")
    except Exception:
        # No body or invalid body is fine
        pass
    
    try:
        result = gs.load_saved_game(save_id=save_id)
        if result is None:
            raise HTTPException(status_code=404, detail="No save file found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        # Save file exists but is corrupted or invalid
        raise HTTPException(status_code=400, detail=f"Failed to load save: {str(exc)}") from exc


@app.post("/reset")
async def reset_game(request: Request):
    """Reset game state and clear save file.
    
    Returns:
        Fresh BootstrapState after reset.
    """
    from .state import (
        set_current_session,
        reset_current_session,
        DEFAULT_SESSION_ID,
        create_character,
    )
    from .models.state import CharacterCreateRequest

    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    provided_session_id = session_id
    
    # Resolve session ID (will use default if not provided)
    if session_id is None:
        session_id = DEFAULT_SESSION_ID
    
    token = set_current_session(session_id)
    try:
        result = gs.reset_and_clear_save(session_id=session_id)
        
        # For the implicit default session, recreate the default character
        # to maintain backward compatibility with legacy tests
        if not provided_session_id and not has_character(session_id=session_id):
            create_character(
                CharacterCreateRequest(name="Aldric", character_class="warrior"),
                session_id=session_id,
            )
            result = get_bootstrap_state(session_id=session_id)
        
        return result
    finally:
        reset_current_session(token)


@app.get("/save/info")
async def get_save_info():
    """Get information about the saved game if it exists.
    
    Returns:
        Save metadata if exists, 404 otherwise.
    """
    info = gs.get_save_info()
    if info is None:
        raise HTTPException(status_code=404, detail="No save file found")
    return info


@app.get("/state")
async def state(request: Request):
    """Return the current game state with XP progress."""
    from .state import (
        get_action_history,
        get_bootstrap_state,
        require_bootstrap_state,
        get_enemy,
        DEFAULT_SESSION_ID,
    )
    from .rules.experience import get_xp_progress
    from .game.state import get_character_rest_status

    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    provided_session_id = session_id
    if session_id is None:
        session_id = DEFAULT_SESSION_ID

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    bootstrap = get_bootstrap_state(session_id)
    result = bootstrap.model_dump(mode="json")
    result["action_history"] = get_action_history(session_id)

    if result.get("actor"):
        actor = result["actor"]
        xp = actor.get("experience_points", 0)
        level = actor.get("level", 1)
        progress = get_xp_progress(xp, level)
        actor["xp"] = xp
        actor["xp_to_next_level"] = progress.get("xp_for_next_level", 0)

        # Include character rest status (spell_slots)
        rest_status = get_character_rest_status(session_id)
        if rest_status:
            actor["hit_dice_remaining"] = rest_status["hit_dice_remaining"]
            actor["hit_dice_total"] = rest_status["hit_dice_total"]
            actor["spell_slots"] = rest_status["spell_slots"]
            actor["spell_slots_max"] = rest_status["spell_slots_max"]

    # Include enemy state for combat tracking
    try:
        enemy = get_enemy(session_id=session_id)
        result["enemy"] = enemy.model_dump(mode="json")
    except Exception:
        pass

    return result


# Include routers AFTER defining persistence endpoints
from .routers import action, character, combat as combat_router, health, map as map_router, modules as modules_router, state

app.include_router(health.router)
app.include_router(action.router)
app.include_router(character.router)
app.include_router(state.router)
app.include_router(map_router.router)
app.include_router(modules_router.router)

# Include routes modules (these take precedence for combat endpoints)
from routes import combat as combat_routes
from routes import save as save_routes

app.include_router(combat_routes.router)
# Register /load/{save_id} and the save-load routes from routes/save.py
# Note: /save and /saves in main.py above take precedence over the router versions;
# only /load/{save_id} (with path param) is new and not conflicting.
app.include_router(save_routes.router)


# Auto-load saved game on startup (if exists)
@app.on_event("startup")
async def startup_event():
    """Try to load saved game on server startup."""
    loaded = gs.try_auto_load_on_startup()
    if loaded:
        print(f"[Startup] Loaded saved game: session_id={loaded.session_id}, phase={loaded.phase.value}")
    else:
        print("[Startup] No saved game found, starting fresh")


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )

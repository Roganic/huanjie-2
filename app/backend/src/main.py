"""幻界 2.0 后端入口"""

import os

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from .routers import action, character, combat, health, state
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

app.include_router(health.router)
app.include_router(action.router)
app.include_router(character.router)
app.include_router(state.router)
app.include_router(combat.router)


@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}


@app.post("/save")
async def save_game(request: Request):
    """Save the current game state to local file.
    
    Returns:
        JSON with success status, timestamp, and file path.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    
    try:
        result = gs.save_current_game(session_id=session_id)
        return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save game: {str(exc)}") from exc


@app.post("/load")
async def load_game():
    """Load game state from local save file.
    
    Returns:
        BootstrapState if save exists, 404 if no save found.
    """
    result = gs.load_saved_game()
    if result is None:
        raise HTTPException(status_code=404, detail="No save file found")
    return result


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

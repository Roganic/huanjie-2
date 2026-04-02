"""Bootstrap state endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..memory_manager import get_recent_event_memories
from ..models.state import BootstrapState
from ..persistence import reset_session as persistence_reset_session
from ..state import (
    create_session,
    get_action_history,
    get_bootstrap_state,
    get_map_state,
    get_narrative_history,
    require_bootstrap_state,
    reset_current_session,
    reset_state,
    set_current_session,
)

router = APIRouter(tags=["state"])


def _request_session_id(request: Request) -> str | None:
    return request.headers.get("X-Session-Id") or request.query_params.get("session_id")


def _resolve_session(request: Request, create_if_missing: bool) -> tuple[str, object]:
    provided_session_id = _request_session_id(request)
    if provided_session_id is None:
        # Use default session for backward compatibility with legacy tests
        from ..state import DEFAULT_SESSION_ID
        bootstrap = get_bootstrap_state(DEFAULT_SESSION_ID)
        return DEFAULT_SESSION_ID, bootstrap

    try:
        return provided_session_id, require_bootstrap_state(provided_session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc


@router.get("/state")
async def state(request: Request):
    """Return the current game state for clients, including action_history."""
    from ..game.state import get_character_rest_status
    from ..state import get_enemy

    session_id, bootstrap = _resolve_session(request, create_if_missing=True)
    result = bootstrap.model_dump(mode="json")
    # Include action_history from session storage
    provided_session_id = _request_session_id(request)
    resolved_id = provided_session_id or session_id
    result["action_history"] = get_action_history(resolved_id)

    # Include character rest status (hit_dice_remaining, spell_slots)
    if bootstrap.actor is not None:
        rest_status = get_character_rest_status(resolved_id)
        if rest_status:
            # Add to character object in response
            if "actor" in result and result["actor"] is not None:
                result["actor"]["hit_dice_remaining"] = rest_status["hit_dice_remaining"]
                result["actor"]["hit_dice_total"] = rest_status["hit_dice_total"]
                result["actor"]["spell_slots"] = rest_status["spell_slots"]
                result["actor"]["spell_slots_max"] = rest_status["spell_slots_max"]

    # Include enemy state for combat tracking
    enemy = get_enemy(session_id=resolved_id)
    result["enemy"] = enemy.model_dump(mode="json")

    return result


@router.get("/scene")
async def get_scene_info(request: Request):
    """Return current scene information with NPCs."""
    from ..state import get_scene
    session_id = _request_session_id(request)
    if session_id is None:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    scene = get_scene(session_id)
    return {
        "scene_name": scene.name,
        "description": scene.description,
        "npcs": [
            {
                "id": npc.id,
                "name": npc.name,
                "type": npc.type.value,
                "description": npc.description,
                "hp": getattr(npc, "hp", None),
                "ac": getattr(npc, "ac", None),
                "attributes": getattr(npc, "attributes", None),
            }
            for npc in scene.npcs
        ],
    }


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap(request: Request):
    """Return the current fixed actor and scene for client initialisation."""
    provided_session_id = _request_session_id(request)
    if provided_session_id is None:
        # Create a new session for each bootstrap request without explicit session_id
        # This ensures proper isolation between different clients/tests
        bootstrap_state = create_session()
    else:
        try:
            _, bootstrap_state = provided_session_id, require_bootstrap_state(provided_session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    return bootstrap_state


@router.post("/state/reset", response_model=BootstrapState)
@router.post("/reset", response_model=BootstrapState)
async def reset(request: Request):
    """Reset actor and scene to initial values, return fresh bootstrap state."""
    from ..state import create_character, get_bootstrap_state, has_character, DEFAULT_SESSION_ID
    from ..models.state import CharacterCreateRequest

    provided_session_id = _request_session_id(request)
    session_id, _ = _resolve_session(request, create_if_missing=True)
    
    token = set_current_session(session_id)
    try:
        result = reset_state(session_id=session_id)
        # For the implicit default session (no session_id provided),
        # recreate the default character to maintain backward compatibility
        # with legacy tests that expect Aldric to exist after reset.
        if not provided_session_id and not has_character(session_id=session_id):
            create_character(
                CharacterCreateRequest(name="Aldric", character_class="warrior"),
                session_id=session_id,
            )
            result = get_bootstrap_state(session_id=session_id)
        return result
    finally:
        reset_current_session(token)


@router.post("/session/reset", response_model=BootstrapState)
async def session_reset(request: Request):
    """Clear persistence file and reset to initial character creation state.
    
    This endpoint is used when the player wants to start a completely new game.
    It clears the save file and returns the session to character creation phase.
    """
    from ..state import DEFAULT_SESSION_ID
    
    provided_session_id = _request_session_id(request)
    session_id = provided_session_id or DEFAULT_SESSION_ID
    
    # Clear the persistence file
    persistence_reset_session(session_id)
    
    token = set_current_session(session_id)
    try:
        # Reset the session state to fresh
        result = reset_state(session_id=session_id)
        return result
    finally:
        reset_current_session(token)


@router.get("/map")
async def map_endpoint(request: Request):
    """Return the full map topology, current node, and explored nodes."""
    session_id = _request_session_id(request)
    if session_id is None:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    return get_map_state(session_id)


@router.get("/memory")
async def get_memory(request: Request):
    """Get recent event memories for the current session.
    
    Returns a list of recent event memory entries including:
    - timestamp: Event timestamp in milliseconds
    - scene_name: Name of the scene where the action occurred
    - action_type: Type of action (attack, skill_check, etc.)
    - action_description: Brief description of the action
    - result_summary: Summary of the action result
    - outcome: "success" or "failure"
    
    Query parameters:
    - limit: Maximum number of events to return (default: 10, max: 50)
    """
    session_id = _request_session_id(request)
    
    # Resolve session - requires explicit session_id or uses default
    if session_id is None:
        from ..state import DEFAULT_SESSION_ID
        session_id = DEFAULT_SESSION_ID
    
    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    # Get limit from query params
    try:
        limit = int(request.query_params.get("limit", 10))
        limit = max(1, min(50, limit))  # Clamp between 1 and 50
    except ValueError:
        limit = 10
    
    # Get narrative history and convert to memory entries
    narrative_history = get_narrative_history(session_id)
    events = get_recent_event_memories(narrative_history, max_events=limit)
    
    return {
        "events": events,
        "total": len(events),
        "session_id": session_id,
    }

"""Combat endpoint for turn-based combat actions."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request

from ..agent.orchestrator import resolve_action_with_agent
from ..models.action import ActionRequest, ActionResponse, ActionType
from ..state import (
    get_combat_state,
    has_character,
    require_bootstrap_state,
    reset_current_session,
    set_current_session,
    start_combat_session,
)

router = APIRouter(tags=["combat"])


@router.post("/combat/start")
async def start_combat(request: Request):
    """Initialize combat for the current session."""
    from ..state import DEFAULT_SESSION_ID

    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID

    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    token = set_current_session(session_id)
    try:
        if not has_character(session_id=session_id):
            raise HTTPException(status_code=400, detail="No character found. Please create a character before starting combat.")

        combat_state = start_combat_session(session_id=session_id)
        return {
            "message": "Combat started",
            "combat_state": combat_state.model_dump(mode="json"),
        }
    finally:
        reset_current_session(token)


@router.post("/combat/action")
async def combat_action(req: ActionRequest, request: Request):
    """Execute a combat action and return the result with narrative."""
    from ..state import DEFAULT_SESSION_ID, create_character
    from ..models.state import CharacterCreateRequest

    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID

    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    token = set_current_session(session_id)
    try:
        if not has_character(session_id=session_id):
            if explicit_session_id:
                raise HTTPException(status_code=400, detail="No character found. Please create a character before taking actions.")
            # Auto-create a default character for the implicit default session
            create_character(
                CharacterCreateRequest(name="Aldric", character_class="warrior"),
                session_id=session_id,
            )

        # Ensure combat is active; auto-start if needed
        combat_state = get_combat_state(session_id=session_id)
        if not combat_state.is_active:
            start_combat_session(session_id=session_id)

        # Force action type to attack if weapon is provided
        if req.weapon and req.action_type == ActionType.GENERIC:
            req = req.model_copy(update={"action_type": ActionType.ATTACK})

        result = await asyncio.to_thread(resolve_action_with_agent, req)

        # Attach current combat state to response
        current_combat = get_combat_state(session_id=session_id)
        response_data = result.model_dump(mode="json")
        response_data["combat_state"] = current_combat.model_dump(mode="json")

        return response_data
    finally:
        reset_current_session(token)

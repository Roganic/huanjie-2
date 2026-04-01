"""Character creation endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..models.state import BootstrapState, CharacterCreateRequest
from ..state import (
    create_character,
    create_session,
    require_bootstrap_state,
    reset_current_session,
    set_current_session,
)

router = APIRouter(prefix="/character", tags=["character"])


def _resolve_session_id(request: Request) -> str:
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if session_id is None:
        return create_session().session_id

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    return session_id


@router.post("/create", response_model=BootstrapState)
async def create(req: CharacterCreateRequest, request: Request) -> BootstrapState:
    """Create a new player character and start the adventure."""
    session_id = _resolve_session_id(request)
    token = set_current_session(session_id)
    try:
        return create_character(req, session_id=session_id)
    finally:
        reset_current_session(token)

"""Character creation endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..models.state import CharacterCard, CharacterCreateRequest
from ..state import (
    create_character,
    create_session,
    get_character_card,
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


@router.post("/create", response_model=CharacterCard)
async def create(req: CharacterCreateRequest, request: Request):
    """Create a new player character and start the adventure."""
    session_id = _resolve_session_id(request)
    token = set_current_session(session_id)
    try:
        create_character(req, session_id=session_id)
        card = get_character_card(session_id=session_id)
        if card is None:
            raise HTTPException(status_code=500, detail="Character creation failed.")
        from fastapi.responses import JSONResponse
        return JSONResponse(content=card.model_dump(mode="json", by_alias=True), headers={"X-Session-Id": session_id})
    finally:
        reset_current_session(token)


@router.get("", response_model=CharacterCard)
async def get_character(request: Request) -> CharacterCard:
    """Get the current character card for the session."""
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if session_id is None:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    token = set_current_session(session_id)
    try:
        card = get_character_card(session_id=session_id)
        if card is None:
            raise HTTPException(status_code=404, detail="No character found.")
        return card
    finally:
        reset_current_session(token)

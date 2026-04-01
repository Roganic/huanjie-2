"""Bootstrap state endpoints."""

from fastapi import APIRouter, HTTPException, Request

from ..models.state import BootstrapState, ScenarioPreset
from ..state import (
    create_session,
    get_bootstrap_state,
    list_scenarios,
    require_bootstrap_state,
    reset_current_session,
    reset_state,
    set_current_session,
)

router = APIRouter(tags=["state"])


def _request_session_id(request: Request) -> str | None:
    return request.headers.get("X-Session-Id") or request.query_params.get("session_id")


def _request_scenario_id(request: Request) -> str | None:
    return request.query_params.get("scenario_id")


def _resolve_session(request: Request, create_if_missing: bool) -> tuple[str, object]:
    provided_session_id = _request_session_id(request)
    if provided_session_id is None:
        bootstrap = create_session(scenario_id=_request_scenario_id(request)) if create_if_missing else None
        if bootstrap is None:
            raise HTTPException(status_code=400, detail="Missing session_id.")
        return bootstrap.session_id, bootstrap

    try:
        return provided_session_id, require_bootstrap_state(provided_session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc


@router.get("/state", response_model=BootstrapState)
async def state(request: Request):
    """Return the current game state for clients."""
    _, bootstrap = _resolve_session(request, create_if_missing=True)
    return bootstrap


@router.get("/state/scenarios", response_model=list[ScenarioPreset])
async def scenarios():
    """Return available adventure scenarios for the client picker."""
    return list_scenarios()


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap(request: Request):
    """Return the current fixed actor and scene for client initialisation."""
    _, bootstrap_state = _resolve_session(request, create_if_missing=True)
    return bootstrap_state


@router.post("/state/reset", response_model=BootstrapState)
@router.post("/reset", response_model=BootstrapState)
async def reset(request: Request):
    """Reset actor and scene to initial values, return fresh bootstrap state."""
    session_id, _ = _resolve_session(request, create_if_missing=True)
    token = set_current_session(session_id)
    try:
        return reset_state(session_id=session_id, scenario_id=_request_scenario_id(request))
    finally:
        reset_current_session(token)

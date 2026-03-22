"""Player action endpoint."""

from fastapi import APIRouter

from ..engine.resolver import resolve_action
from ..models.action import ActionRequest, ActionResponse
from ..state import apply_effects

router = APIRouter(tags=["game"])


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest) -> ActionResponse:
    result = resolve_action(req)
    apply_effects(result.effects)
    return result

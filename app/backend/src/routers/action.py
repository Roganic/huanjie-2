"""Player action endpoint."""

from fastapi import APIRouter

from ..engine.resolver import resolve_action
from ..models.action import ActionRequest, ActionResponse

router = APIRouter(tags=["game"])


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest) -> ActionResponse:
    return resolve_action(req)

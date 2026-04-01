"""Player action endpoint.

This endpoint is orchestrated by the GM Agent, which:
1. Analyzes the action request and current state
2. Decides what checks/rolls are needed
3. Executes tools in sequence (dice rolls, state changes)
4. Generates narrative after all mechanical resolution
5. Returns a consistent ActionResponse with all state changes applied
"""

from fastapi import APIRouter, HTTPException

from ..agent.orchestrator import resolve_action_with_agent
from ..models.action import ActionRequest, ActionResponse
from ..state import has_character

router = APIRouter(tags=["game"])


@router.post("/action", response_model=ActionResponse)
async def submit_action(req: ActionRequest) -> ActionResponse:
    """Submit a player action for GM Agent resolution.
    
    The GM Agent will orchestrate the entire resolution:
    - Determine required rolls (attack, damage, saving throws, etc.)
    - Execute dice rolls
    - Apply state changes
    - Generate narrative
    
    All state changes are applied atomically during orchestration,
    ensuring consistent game state in the response.
    """
    if not has_character():
        raise HTTPException(status_code=409, detail="Create a character before taking actions.")
    return resolve_action_with_agent(req)

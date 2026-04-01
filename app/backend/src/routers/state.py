"""Bootstrap state endpoint — read-only."""

from fastapi import APIRouter

from ..models.state import BootstrapState
from ..state import get_bootstrap_state, reset_state

router = APIRouter(tags=["state"])


@router.get("/state", response_model=BootstrapState)
async def state():
    """Return the current game state for clients."""
    return get_bootstrap_state()


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap():
    """Return the current fixed actor and scene for client initialisation."""
    return get_bootstrap_state()


@router.post("/state/reset", response_model=BootstrapState)
async def reset():
    """Reset actor and scene to initial values, return fresh bootstrap state."""
    reset_state()
    return get_bootstrap_state()

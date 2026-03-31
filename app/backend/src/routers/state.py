"""State endpoints — bootstrap and reset."""

from fastapi import APIRouter

from ..models.state import BootstrapState
from ..state import get_bootstrap_state, reset_state

router = APIRouter(tags=["state"])


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap():
    """Return the current fixed actor and scene for client initialisation."""
    return get_bootstrap_state()


@router.post("/state/reset")
async def reset():
    """Reset mutable state to its initial values and return fresh bootstrap."""
    reset_state()
    return {"status": "ok", "bootstrap": get_bootstrap_state()}

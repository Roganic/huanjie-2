"""Bootstrap state endpoint — read-only."""

from fastapi import APIRouter

from ..models.state import BootstrapState
from ..state import get_bootstrap_state

router = APIRouter(tags=["state"])


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap():
    """Return the current fixed actor and scene for client initialisation."""
    return get_bootstrap_state()

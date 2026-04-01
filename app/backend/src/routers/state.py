"""Bootstrap state endpoint — read-only."""

from fastapi import APIRouter

from ..models.state import BootstrapState, CharacterCreateRequest
from ..state import create_character, get_bootstrap_state, reset_state

router = APIRouter(tags=["state"])


@router.get("/state/bootstrap", response_model=BootstrapState)
async def bootstrap():
    """Return the current fixed actor and scene for client initialisation."""
    return get_bootstrap_state()


@router.post("/state/character", response_model=BootstrapState)
async def create_character_state(req: CharacterCreateRequest):
    """Create a fresh player character and reset scene state."""
    return create_character(req.name, req.archetype)


@router.post("/state/reset", response_model=BootstrapState)
async def reset():
    """Reset actor and scene to initial values, return fresh bootstrap state."""
    reset_state()
    return get_bootstrap_state()

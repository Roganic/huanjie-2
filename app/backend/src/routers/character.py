"""Character creation endpoints."""

from fastapi import APIRouter

from ..models.state import BootstrapState, CharacterCreateRequest
from ..state import create_character

router = APIRouter(prefix="/character", tags=["character"])


@router.post("/create", response_model=BootstrapState)
async def create(req: CharacterCreateRequest) -> BootstrapState:
    """Create a new player character and start the adventure."""
    return create_character(req)

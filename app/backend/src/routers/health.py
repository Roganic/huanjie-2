"""健康检查"""

from fastapi import APIRouter

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check():
    return {"status": "ok"}

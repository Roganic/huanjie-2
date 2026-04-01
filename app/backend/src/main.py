"""幻界 2.0 后端入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import action, health, state
from .settings import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(action.router)
app.include_router(state.router)


@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}

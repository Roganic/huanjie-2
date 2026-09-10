"""幻界服务组装：每条 HTTP 路由只注册一次。"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from . import game_state as gs
from .routers import action, character, gameplay, health, map, modules, persistence, state
from routes import combat
from .gm.settings import router as gm_settings_router


def _get_allowed_origins():
    configured = os.getenv("CORS_ALLOW_ORIGINS", "")
    return [v.strip() for v in configured.split(",") if v.strip()] or ["http://localhost:5173", "http://127.0.0.1:5173"]


app = FastAPI(title="幻界 2.0", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=_get_allowed_origins(), allow_origin_regex=r"https://.*\.github\.io", allow_methods=["*"], allow_headers=["*"])

@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}

for endpoint in (health, character, state, gameplay, action, map, combat, persistence, modules):
    app.include_router(endpoint.router)
app.include_router(gm_settings_router)

@app.on_event("startup")
async def startup_event():
    gs.try_auto_load_on_startup()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=os.getenv("HOST", "0.0.0.0"), port=int(os.getenv("PORT", "8000")))

"""幻界 2.0 后端入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import action, health

app = FastAPI(title="幻界 2.0", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(action.router)


@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}

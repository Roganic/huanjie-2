"""幻界 2.0 后端入口"""

from fastapi import FastAPI

from .routers import action, health

app = FastAPI(title="幻界 2.0", version="0.1.0")

app.include_router(health.router)
app.include_router(action.router)


@app.get("/")
async def root():
    return {"name": "幻界 2.0", "status": "running"}

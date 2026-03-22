"""Tests for the action resolution endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Health check still works
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health(client):
    async with client as c:
        resp = await c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Auto-success path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_success(client):
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around the tavern",
            "approach": "casually look at the patrons",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "auto_success"
    assert data["outcome"] == "success"
    assert data["check"] is None
    assert "narration" in data


# ---------------------------------------------------------------------------
# Check path — verifies structured fields are present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_resolution(client):
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-03",
            "actor": "Bree",
            "intent": "pick the lock on the chest",
            "approach": "carefully pick the lock with thieves tools",
            "dc": 15,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "check"
    assert data["check"] is not None
    check = data["check"]
    assert check["ability"] == "dex"
    assert check["dc"] == 15
    assert "roll" in check
    assert "total" in check
    assert data["outcome"] in ("success", "failure")
    assert isinstance(data["effects"], list)
    assert len(data["narration"]) > 0


# ---------------------------------------------------------------------------
# Explicit ability override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_explicit_ability(client):
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "Cara",
            "intent": "intimidate the bandit leader",
            "approach": "flex muscles menacingly",
            "ability": "str",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["check"]["ability"] == "str"


# ---------------------------------------------------------------------------
# Advantage / disadvantage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advantage(client):
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "ruins-02",
            "actor": "Dex",
            "intent": "sneak past the guards",
            "approach": "sneak through the shadows",
            "advantage": True,
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["check"]["advantage"] is True

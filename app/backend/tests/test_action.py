"""Tests for the action resolution endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_character(client: AsyncClient, name: str = "Aldric") -> str:
    """Create a character and return session_id."""
    resp = await client.post("/character/create", json={
        "name": name,
        "character_class": "warrior",
        "ability_generation": "standard_array",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    if not session_id:
        bootstrap = await client.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
    return session_id


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
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around the tavern",
            "approach": "casually look at the patrons",
        }, headers={"X-Session-Id": session_id})
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
        session_id = await _create_character(c, "Bree")
        resp = await c.post("/action", json={
            "scene_id": "dungeon-03",
            "actor": "Bree",
            "intent": "pick the lock on the chest",
            "approach": "carefully pick the lock with thieves tools",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})
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
        session_id = await _create_character(c, "Cara")
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "Cara",
            "intent": "intimidate the bandit leader",
            "approach": "flex muscles menacingly",
            "ability": "str",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["check"]["ability"] == "str"


# ---------------------------------------------------------------------------
# Advantage / disadvantage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_advantage(client):
    async with client as c:
        session_id = await _create_character(c, "Dex")
        resp = await c.post("/action", json={
            "scene_id": "ruins-02",
            "actor": "Dex",
            "intent": "sneak past the guards",
            "approach": "sneak through the shadows",
            "advantage": True,
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["check"]["advantage"] is True


# ---------------------------------------------------------------------------
# Regression: non-trivial "open" must NOT auto-succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_open_locked_chest_requires_check(client):
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "open the locked chest",
            "approach": "try to force it open",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "check", (
        "Opening a locked chest should require a check, not auto-succeed"
    )


# ---------------------------------------------------------------------------
# Regression: social "talk" / "say" with persuasion must NOT auto-succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_talk_guard_requires_check(client):
    async with client as c:
        session_id = await _create_character(c, "Bree")
        resp = await c.post("/action", json={
            "scene_id": "gate-01",
            "actor": "Bree",
            "intent": "talk the guard into letting us pass",
            "approach": "convince him we are merchants",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "check", (
        "Persuading a guard should require a check, not auto-succeed"
    )


@pytest.mark.asyncio
async def test_say_convincing_lie_requires_check(client):
    async with client as c:
        session_id = await _create_character(c, "Cara")
        resp = await c.post("/action", json={
            "scene_id": "court-01",
            "actor": "Cara",
            "intent": "say a convincing lie to the magistrate",
            "approach": "deceive him about our origins",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert data["resolution_type"] == "check", (
        "Telling a convincing lie should require a check, not auto-succeed"
    )


# ---------------------------------------------------------------------------
# Regression: invalid ability must be rejected at API level
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_ability_rejected(client):
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle the bartender",
            "approach": "use brute strength",
            "ability": "athletics",
        })
    assert resp.status_code == 422, (
        "Invalid ability value should return 422 validation error"
    )

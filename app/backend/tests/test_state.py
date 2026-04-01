"""Tests for the bootstrap state endpoint."""

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


# ---------------------------------------------------------------------------
# GET /state/bootstrap returns expected shape
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_returns_actor_and_scene(client):
    async with client as c:
        resp = await c.get("/state/bootstrap")
    assert resp.status_code == 200
    data = resp.json()
    assert "actor" in data
    assert "scene" in data
    assert "narrative_history" in data
    assert data["narrative_history"] == []


@pytest.mark.asyncio
async def test_bootstrap_actor_has_abilities(client):
    async with client as c:
        resp = await c.get("/state/bootstrap")
    actor = resp.json()["actor"]
    assert actor["name"] == "Aldric"
    assert actor["id"] == "aldric-01"
    abilities = actor["abilities"]
    for key in ("str", "dex", "con", "int", "wis", "cha"):
        assert key in abilities
        assert isinstance(abilities[key], int)
    assert actor["hp"] == actor["hp_max"]
    assert actor["proficiency_bonus"] == 2


@pytest.mark.asyncio
async def test_bootstrap_scene_has_required_fields(client):
    async with client as c:
        resp = await c.get("/state/bootstrap")
    scene = resp.json()["scene"]
    assert scene["id"] == "tavern-01"
    assert len(scene["name"]) > 0
    assert len(scene["description"]) > 0
    assert "aldric-01" in scene["actors"]


# ---------------------------------------------------------------------------
# Ability modifier math
# ---------------------------------------------------------------------------

def test_ability_modifier_calculation():
    from src.models.state import AbilityScores

    scores = AbilityScores(**{
        "str": 16, "dex": 12, "con": 13, "int": 10, "wis": 12, "cha": 8,
    })
    assert scores.modifier("str") == 3   # (16 - 10) // 2
    assert scores.modifier("dex") == 1   # (12 - 10) // 2
    assert scores.modifier("con") == 1   # (13 - 10) // 2
    assert scores.modifier("int") == 0   # (10 - 10) // 2
    assert scores.modifier("wis") == 1   # (12 - 10) // 2
    assert scores.modifier("cha") == -1  # (8 - 10) // 2


# ---------------------------------------------------------------------------
# Resolver uses bootstrap actor stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_resolver_uses_bootstrap_actor_modifier(client):
    """The check modifier should match the bootstrap actor's ability scores."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle the barkeep",
            "approach": "use brute force to push his arm down",
            "ability": "str",
            "dc": 10,
        })
    data = resp.json()
    assert data["resolution_type"] == "check"
    # STR 16 -> modifier 3
    assert data["check"]["modifier"] == 3
    assert data["check"]["proficiency_bonus"] == 2

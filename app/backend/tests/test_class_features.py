"""Tests for warrior and rogue class features."""

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


async def _create_character(client: AsyncClient, name: str = "TestHero", character_class: str = "warrior") -> str:
    resp = await client.post("/character/create", json={
        "name": name,
        "character_class": character_class,
        "ability_generation": "standard_array",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    if not session_id:
        bootstrap = await client.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
    return session_id


@pytest.mark.asyncio
async def test_second_wind_heals_and_marks_used(client):
    async with client as c:
        session_id = await _create_character(c, name="WarriorTest", character_class="warrior")
        
        # Damage the warrior first via effects so healing is observable
        from src.state import apply_effects
        from src.models.action import Effect
        apply_effects([
            Effect(target="WarriorTest", field="hp", delta=-5, description="测试伤害")
        ], session_id=session_id)
        
        # Verify initial state
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        initial_data = state_resp.json()
        initial_hp = initial_data["actor"]["hp"]
        assert initial_hp < initial_data["actor"]["hp_max"]
        assert initial_data["actor"]["class_features"]["second_wind_used"] is False
        
        # Use second wind
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "WarriorTest",
            "intent": "second_wind",
            "approach": "",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "success"
        
        # Verify HP increased and feature is marked used
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["actor"]["hp"] > initial_hp
        assert state_data["actor"]["class_features"]["second_wind_used"] is True


@pytest.mark.asyncio
async def test_action_surge_marks_used_and_returns_extra_action(client):
    async with client as c:
        session_id = await _create_character(c, name="WarriorTest", character_class="warrior")
        
        # Verify initial state
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["actor"]["class_features"]["action_surge_used"] is False
        
        # Use action surge
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "WarriorTest",
            "intent": "action_surge",
            "approach": "",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "success"
        assert data["extra_action_available"] is True
        
        # Verify feature is marked used
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["actor"]["class_features"]["action_surge_used"] is True


@pytest.mark.asyncio
async def test_state_returns_rogue_class_features(client):
    async with client as c:
        session_id = await _create_character(c, name="RogueTest", character_class="rogue")
        
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        
        assert "class_features" in state_data["actor"]
        assert state_data["actor"]["class_features"]["sneak_attack_available"] is True


@pytest.mark.asyncio
async def test_second_wind_cannot_be_used_twice(client):
    async with client as c:
        session_id = await _create_character(c, name="WarriorTest", character_class="warrior")
        
        # Use second wind first time
        resp1 = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "WarriorTest",
            "intent": "second_wind",
            "approach": "",
        }, headers={"X-Session-Id": session_id})
        assert resp1.status_code == 200
        
        # Try to use second wind again
        resp2 = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "WarriorTest",
            "intent": "second_wind",
            "approach": "",
        }, headers={"X-Session-Id": session_id})
        assert resp2.status_code == 400

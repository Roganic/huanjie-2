"""Tests for AI narrative generation."""

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
# Narrative generation structure tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_returns_narration_field(client):
    """Action response should include a narrative field."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around",
            "approach": "casually observe the room",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "narration" in data
    assert isinstance(data["narration"], str)
    assert len(data["narration"]) > 0


@pytest.mark.asyncio
async def test_narration_is_not_template_format(client):
    """Narration should be immersive text, not system logs."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "pick the lock",
            "approach": "use my thieves tools",
            "ability": "dex",
        })
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"].lower()
    
    # Should not contain system/mechanical terms
    assert "dc" not in narration
    assert "modifier" not in narration
    assert "roll" not in narration
    assert "check" not in narration or "checking" in narration  # "check" might appear in normal text
    assert "— and it works" not in data["narration"]
    assert "— but it doesn't" not in data["narration"]


@pytest.mark.asyncio
async def test_narration_includes_character_and_scene_context(client):
    """Narration should reference character and scene context."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "examine the room",
            "approach": "look around carefully",
        })
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"]
    
    # Should mention the character
    assert "Aldric" in narration


@pytest.mark.asyncio
async def test_authored_success_and_failure_have_distinct_narration(client,monkeypatch):
    from tests.conftest import create_session_and_character
    sid=await create_session_and_character(client)
    h={"X-Session-Id":sid}
    await client.post("/map/move",headers=h,json={"target_scene_id":"dungeon-entrance-01"})
    payload=dict(scene_id="ignored",actor="ignored",intent="检查废弃补给箱",approach="")
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:1)
    failure=(await client.post("/action",headers=h,json=payload)).json()
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:20)
    success=(await client.post("/action",headers=h,json=payload)).json()
    assert failure["outcome"]=="failure" and success["outcome"]=="success"
    assert failure["narration"] != success["narration"]
    assert "药水" in success["narration"]


@pytest.mark.asyncio
async def test_combat_narrative_includes_action_details(client, predictable_combat):
    from tests.conftest import create_session_and_character, enter_passage
    sid = await create_session_and_character(client)
    await enter_passage(client,sid)
    response = await client.post("/combat/action",headers={"X-Session-Id":sid},json={"action_type":"attack","target_id":"goblin-01"})
    assert response.status_code == 200,response.text
    data = response.json()
    assert data["hit"] is True
    assert not any(e["type"] == "saving_throw" for e in data["events"])
    assert "长剑" in data["narrative"] and "哥布林" in data["narrative"]


@pytest.mark.asyncio
async def test_auto_success_has_narration(client):
    """Auto-success actions should still have narrative."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around",
            "approach": "walk around and look at things",
        })
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["resolution_type"] == "auto_success"
    assert len(data["narration"]) > 0
    assert "Aldric" in data["narration"]


# ---------------------------------------------------------------------------
# Narrative content quality tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narration_reasonable_length(client):
    """Narration should be a reasonable length (not too short, not too long)."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "persuade the bartender",
            "approach": "offer a charming smile and friendly words",
            "ability": "cha",
        })
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"]
    
    # Should be at least a sentence or two (fallback is ~100-200 chars)
    assert len(narration) > 50
    # Should not be excessively long (AI max is 500 tokens, but fallback is shorter)
    assert len(narration) < 2000

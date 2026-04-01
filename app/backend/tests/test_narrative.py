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
# Narrative generation structure tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_returns_narration_field(client):
    """Action response should include a narrative field."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around",
            "approach": "casually observe the room",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    assert "narration" in data
    assert isinstance(data["narration"], str)
    assert len(data["narration"]) > 0


@pytest.mark.asyncio
async def test_narration_is_not_template_format(client):
    """Narration should be immersive text, not system logs."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "pick the lock",
            "approach": "use my thieves tools",
            "ability": "dex",
        }, headers={"X-Session-Id": session_id})
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
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "examine the room",
            "approach": "look around carefully",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"]
    
    # Should mention the character
    assert "Aldric" in narration


@pytest.mark.asyncio
async def test_narration_reflects_success_vs_failure(client):
    """Success and failure should produce different narrative tones."""
    # This test verifies the fallback narrative at least differentiates outcomes
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "climb the wall",
            "approach": "scale it quickly",
            "ability": "str",
            "dc": 5,  # Low DC to likely succeed
        }, headers={"X-Session-Id": session_id})
        success_data = resp.json()
        
        # Reset state between requests
        from src.state import reset_state
        reset_state()
        session_id2 = await _create_character(c)
        
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "climb the wall",
            "approach": "scale it quickly",
            "ability": "str",
            "dc": 30,  # Impossibly high DC to likely fail
        }, headers={"X-Session-Id": session_id2})
        failure_data = resp.json()
    
    # Both should have narration
    assert len(success_data["narration"]) > 0
    assert len(failure_data["narration"]) > 0
    
    # Success should have positive language, failure negative
    # (Exact words depend on fallback vs AI, but they should differ)
    assert success_data["narration"] != failure_data["narration"]


@pytest.mark.asyncio
async def test_combat_narrative_includes_action_details(client):
    """Combat narration should reference weapon and target."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my longsword",
            "weapon": "longsword",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"].lower()
    
    # Should mention combat elements
    assert "longsword" in narration or "sword" in narration
    # Target might be mentioned in Chinese (哥布林斥候) or English
    assert "goblin" in narration.lower() or "斥候" in narration or "scout" in narration


@pytest.mark.asyncio
async def test_auto_success_has_narration(client):
    """Auto-success actions should still have narrative."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around",
            "approach": "walk around and look at things",
        }, headers={"X-Session-Id": session_id})
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
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "persuade the bartender",
            "approach": "offer a charming smile and friendly words",
            "ability": "cha",
        }, headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    data = resp.json()
    narration = data["narration"]
    
    # Should be at least a sentence or two (fallback is ~100-200 chars)
    assert len(narration) > 50
    # Should not be excessively long (AI max is 500 tokens, but fallback is shorter)
    assert len(narration) < 2000

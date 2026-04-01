"""Tests for combat API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_character(client: AsyncClient, name: str = "TestHero") -> str:
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
# POST /combat/start
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combat_start_requires_session(client):
    """Starting combat requires a session."""
    async with client as c:
        resp = await c.post("/combat/start", json={})
    assert resp.status_code == 400
    assert "session_id" in resp.text.lower()


@pytest.mark.asyncio
async def test_combat_start_requires_character(client):
    """Starting combat requires a character to be created."""
    async with client as c:
        # Get a session without creating a character
        bootstrap = await c.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
        
        resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
    assert resp.status_code == 400
    assert "character" in resp.text.lower()


@pytest.mark.asyncio
async def test_combat_start_returns_initiative_order(client):
    """Starting combat returns initiative order and participants."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Verify combat_id
    assert "combat_id" in data
    assert data["combat_id"].startswith("combat-")
    
    # Verify status
    assert data["status"] == "active"
    
    # Verify round number
    assert data["round_number"] == 1
    
    # Verify participants exist
    assert "participants" in data
    assert len(data["participants"]) >= 2  # Player + at least one enemy
    
    # Verify initiative order
    assert "initiative_order" in data
    assert len(data["initiative_order"]) == len(data["participants"])
    
    # Verify current actor is set
    assert "current_actor_id" in data
    assert data["current_actor_id"] in data["initiative_order"]
    
    # Verify participant structure
    for p in data["participants"]:
        assert "id" in p
        assert "name" in p
        assert "hp" in p
        assert "hp_max" in p
        assert "ac" in p
        assert "initiative" in p
        assert "is_player" in p


# ---------------------------------------------------------------------------
# POST /combat/action
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combat_action_requires_active_combat(client):
    """Combat action requires an active combat."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/combat/action", json={
            "action_type": "attack",
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 400
    assert "no active combat" in resp.text.lower()


@pytest.mark.asyncio
async def test_combat_action_attack_returns_hit_and_damage(client):
    """Attack action returns hit status and damage."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        start_resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        assert start_resp.status_code == 200
        combat_data = start_resp.json()
        
        # Find player and enemy
        player = next((p for p in combat_data["participants"] if p["is_player"]), None)
        enemy = next((p for p in combat_data["participants"] if not p["is_player"]), None)
        assert player is not None
        assert enemy is not None
        
        # If it's not player's turn, we might not be able to act
        # But the API should still return a valid response
        resp = await c.post("/combat/action", json={
            "action_type": "attack",
            "target_id": enemy["id"],
            "weapon": "longsword",
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Verify action response structure
    assert "action_type" in data
    assert data["action_type"] == "attack"
    
    assert "actor_id" in data
    assert "hit" in data
    
    # Verify combat_state is returned
    assert "combat_state" in data
    assert data["combat_state"]["status"] in ["active", "victory", "defeat", "escaped"]
    
    # Verify narrative exists
    assert "narrative" in data
    assert len(data["narrative"]) > 0


@pytest.mark.asyncio
async def test_combat_action_streaming_response(client):
    """Combat action supports streaming response."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        
        # Get combat state to find enemy
        state_resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
        combat_data = state_resp.json()
        enemy = next((p for p in combat_data["participants"] if not p["is_player"]), None)
        
        # Request streaming response
        resp = await c.post("/combat/action", json={
            "action_type": "attack",
            "target_id": enemy["id"],
            "weapon": "longsword",
        }, headers={
            "X-Session-Id": session_id,
            "Accept": "text/event-stream",
        })
    
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /combat/state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_combat_state_returns_current_state(client):
    """Getting combat state returns current combat status."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        
        # Get state
        resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Verify state structure
    assert "combat_id" in data
    assert "status" in data
    assert "round_number" in data
    assert "turn_index" in data
    assert "current_actor_id" in data
    assert "initiative_order" in data
    assert "participants" in data
    assert "log" in data


@pytest.mark.asyncio
async def test_get_combat_state_returns_404_when_no_combat(client):
    """Getting combat state returns 404 when no combat is active."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 404
    assert "no active combat" in resp.text.lower()


# ---------------------------------------------------------------------------
# POST /combat/end
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combat_end_flee_sets_status(client):
    """Ending combat with flee reason sets status to escaped."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        
        # End combat by fleeing
        resp = await c.post("/combat/end", json={
            "reason": "flee",
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "escaped"
    assert "final_round" in data


@pytest.mark.asyncio
async def test_combat_end_victory_sets_status(client):
    """Ending combat with victory reason sets status to victory."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        
        # End combat by victory
        resp = await c.post("/combat/end", json={
            "reason": "victory",
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "victory"


@pytest.mark.asyncio
async def test_combat_end_defeat_sets_status(client):
    """Ending combat with defeat reason sets status to defeat."""
    async with client as c:
        session_id = await _create_character(c)
        
        # Start combat
        await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        
        # End combat by defeat
        resp = await c.post("/combat/end", json={
            "reason": "defeat",
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    assert data["status"] == "defeat"


# ---------------------------------------------------------------------------
# Full Combat Flow
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_combat_flow(client):
    """Test the complete combat flow from start to end."""
    async with client as c:
        session_id = await _create_character(c)
        
        # 1. Start combat
        start_resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        assert start_resp.status_code == 200
        combat_data = start_resp.json()
        assert combat_data["status"] == "active"
        
        # 2. Get combat state
        state_resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        state_data = state_resp.json()
        assert state_data["status"] == "active"
        
        # 3. Perform combat actions until combat ends or max actions
        enemy = next((p for p in state_data["participants"] if not p["is_player"]), None)
        assert enemy is not None
        
        for _ in range(10):  # Max 10 actions to prevent infinite loop
            action_resp = await c.post("/combat/action", json={
                "action_type": "attack",
                "target_id": enemy["id"],
                "weapon": "longsword",
            }, headers={"X-Session-Id": session_id})
            
            assert action_resp.status_code == 200
            action_data = action_resp.json()
            
            # Verify response has required fields
            assert "hit" in action_data
            assert "combat_state" in action_data
            assert "narrative" in action_data
            
            # Check if combat ended
            if action_data["combat_state"]["status"] != "active":
                break
        
        # 4. End combat
        end_resp = await c.post("/combat/end", json={
            "reason": "victory",
        }, headers={"X-Session-Id": session_id})
        
        assert end_resp.status_code == 200
        end_data = end_resp.json()
        assert end_data["status"] == "victory"

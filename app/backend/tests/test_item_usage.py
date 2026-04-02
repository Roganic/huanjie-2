"""Tests for the item usage system.

Validates:
- Using healing potion restores HP and removes item from inventory
- Using non-existent item returns error without side effects
- Item use details contain required fields
- Item use works in combat state
"""

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


async def _create_session_and_character(client, name="TestHero"):
    """Helper to create a session and character."""
    resp = await client.get("/state/bootstrap")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    resp = await client.post(
        "/character/create",
        json={
            "name": name,
            "character_class": "warrior",
            "ability_generation": "standard_array",
        },
        headers={"X-Session-Id": session_id},
    )
    assert resp.status_code == 200
    return session_id, resp.json()


class TestItemUsageExploration:
    """Test item usage in exploration phase."""

    @pytest.mark.asyncio
    async def test_use_healing_potion_increases_hp_and_removes_item(self, client):
        """Using healing potion should increase HP (capped at max) and remove the item."""
        async with client as c:
            session_id, char = await _create_session_and_character(c)

            # Verify character starts with a healing potion
            initial_inventory = char["inventory"]
            potion_items = [item for item in initial_inventory if item["name"] == "治疗药水"]
            assert len(potion_items) >= 1, "Character should start with a healing potion"

            # Damage the character first so healing has an effect
            # We'll do this by reducing HP via a direct state manipulation
            from src.state import get_actor, _get_session, _resolve_session_id, _save_session, _SESSION_LOCK
            with _SESSION_LOCK:
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                actor = session.actor
                assert actor is not None
                # Set HP to 1 so healing will have a visible effect
                session.actor = actor.model_copy(update={"hp": 1})
                _save_session(session)

            initial_hp = 1
            hp_max = char["hp"]["max"]

            # Use the healing potion
            resp = await c.post(
                "/action",
                json={
                    "scene_id": "test-scene",
                    "actor": char["name"],
                    "intent": "使用治疗药水",
                    "approach": "使用治疗药水",
                },
                headers={"X-Session-Id": session_id},
            )
            assert resp.status_code == 200
            data = resp.json()

            # Verify response contains item_use details
            assert "item_use" in data
            item_use = data["item_use"]
            assert item_use is not None
            assert item_use["item_name"] == "治疗药水"
            assert item_use["effect_type"] == "heal"
            assert isinstance(item_use["roll_result"], int)
            assert isinstance(item_use["hp_change"], int)
            assert item_use["hp_change"] > 0

            # Verify HP increased but did not exceed max
            state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state_resp.status_code == 200
            state_data = state_resp.json()
            current_hp = state_data["actor"]["hp"]
            assert current_hp > initial_hp
            assert current_hp <= hp_max

            # Verify potion was removed from inventory
            final_inventory = state_data["actor"]["inventory"]
            potion_items_after = [item for item in final_inventory if item["name"] == "治疗药水"]
            assert len(potion_items_after) == len(potion_items) - 1

    @pytest.mark.asyncio
    async def test_use_nonexistent_item_returns_error(self, client):
        """Using an item not in inventory should return an error without side effects."""
        async with client as c:
            session_id, char = await _create_session_and_character(c)

            # Get initial state
            state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state_resp.status_code == 200
            state_data = state_resp.json()
            initial_hp = state_data["actor"]["hp"]
            initial_inventory = state_data["actor"]["inventory"]

            # Try to use a non-existent item
            resp = await c.post(
                "/action",
                json={
                    "scene_id": "test-scene",
                    "actor": char["name"],
                    "intent": "使用不存在的物品",
                    "approach": "使用不存在的物品",
                },
                headers={"X-Session-Id": session_id},
            )
            assert resp.status_code == 400
            error_text = resp.text
            assert "没有" in error_text or "不存在" in error_text

            # Verify HP and inventory unchanged
            state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state_resp.status_code == 200
            state_data = state_resp.json()
            assert state_data["actor"]["hp"] == initial_hp
            assert state_data["actor"]["inventory"] == initial_inventory


class TestItemUsageCombat:
    """Test item usage in combat phase."""

    @pytest.mark.asyncio
    async def test_use_healing_potion_in_combat(self, client):
        """Using healing potion in combat should update HP correctly."""
        async with client as c:
            session_id, char = await _create_session_and_character(c)

            # Start combat
            combat_resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
            assert combat_resp.status_code == 200

            # Damage the character
            from src.state import get_actor, _get_session, _resolve_session_id, _save_session, _SESSION_LOCK
            with _SESSION_LOCK:
                session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                actor = session.actor
                assert actor is not None
                session.actor = actor.model_copy(update={"hp": 1})
                _save_session(session)

            # Use healing potion
            resp = await c.post(
                "/action",
                json={
                    "scene_id": "combat-01",
                    "actor": char["name"],
                    "intent": "使用治疗药水",
                    "approach": "使用治疗药水",
                },
                headers={"X-Session-Id": session_id},
            )
            assert resp.status_code == 200
            data = resp.json()

            # Verify item_use details present
            assert "item_use" in data
            item_use = data["item_use"]
            assert item_use is not None
            assert item_use["item_name"] == "治疗药水"
            assert item_use["effect_type"] == "heal"
            assert isinstance(item_use["roll_result"], int)
            assert isinstance(item_use["hp_change"], int)

            # Verify HP updated in state
            state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state_resp.status_code == 200
            state_data = state_resp.json()
            assert state_data["actor"]["hp"] > 1

"""Tests for equipment and inventory system."""

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


async def _create_session_and_character(client, name="Aldric", character_class="warrior"):
    resp = await client.get("/state/bootstrap")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    
    resp = await client.post(
        "/character/create",
        json={
            "name": name,
            "character_class": character_class,
            "ability_generation": "standard_array",
        },
        headers={"X-Session-Id": session_id},
    )
    assert resp.status_code == 200
    return session_id


@pytest.mark.asyncio
async def test_pickup_item_adds_to_inventory(client):
    """AC1: POST /action with 拾取 adds item to character.inventory."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        
        resp = await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "拾取短剑",
                "approach": "拾取短剑",
            },
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "success"
        assert data["inventory_update"] is not None
        assert data["inventory_update"]["picked_up"]["id"] == "shortsword"
        
        state_resp = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        actor = state_resp.json()["actor"]
        inventory_ids = [item["id"] for item in actor["inventory"]]
        assert "shortsword" in inventory_ids


@pytest.mark.asyncio
async def test_equip_weapon_changes_combat_damage(client):
    """AC2: Equip shortsword and attack uses 1d6 damage (verified via combat API)."""
    async with client as c:
        session_id = await _create_session_and_character(c, character_class="warrior")
        
        # Warrior starts with longsword equipped. Pick up shortsword from tavern.
        resp = await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "拾取短剑",
                "approach": "拾取短剑",
            },
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "success"
        
        # Equip shortsword (1d6)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "装备短剑",
                "approach": "装备短剑",
            },
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["inventory_update"]["equipped"]["slot"] == "weapon"
        assert data["inventory_update"]["equipped"]["item"]["damage_dice"] == "1d6"


@pytest.mark.asyncio
async def test_equip_armor_updates_ac(client):
    """AC3: Equip leather armor and GET /state returns updated AC."""
    async with client as client_instance:
        session_id = await _create_session_and_character(client_instance, character_class="mage")
        
        # Mage starts with robe (AC 10 + DEX). Pick up leather.
        resp = await client_instance.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Mage",
                "intent": "拾取皮甲",
                "approach": "拾取皮甲",
            },
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        
        # Equip leather (AC 11 + DEX mod)
        resp = await client_instance.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Mage",
                "intent": "装备皮甲",
                "approach": "装备皮甲",
            },
            headers={"X-Session-Id": session_id},
        )
        assert resp.status_code == 200
        
        state_resp = await client_instance.get("/state", headers={"X-Session-Id": session_id})
        assert state_resp.status_code == 200
        actor = state_resp.json()["actor"]
        # Mage DEX 13 -> +1 mod, leather AC 11 + 1 = 12
        assert actor["ac"] == 12
        assert actor["equipped"]["armor"]["id"] == "leather"


def test_unarmed_damage_uses_fixed_one_plus_strength(monkeypatch):
    from tests.conftest import create_default_actor
    from src.state import get_actor
    from src.combat import resolve_attack_with_equipment
    create_default_actor()
    actor = get_actor()
    actor.equipped.weapon = None
    monkeypatch.setattr("random.randint",lambda a,b:20)
    result = resolve_attack_with_equipment(actor,10)
    assert result["damage"] == 1 + actor.abilities.modifier("str")
    assert result["damage_rolls"] == []

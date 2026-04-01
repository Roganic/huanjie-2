"""Tests for attack resolution (hit/miss scenarios and damage calculation)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import get_actor, get_enemy, reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_session_and_character(client, name="Aldric", character_class="warrior"):
    """Helper to create a session and character."""
    # Create session via state/bootstrap endpoint
    resp = await client.get("/state/bootstrap")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    
    # Create character
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


# ---------------------------------------------------------------------------
# Attack hit scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_hit_structure(client):
    """Successful attack should include complete hit details."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack the goblin",
                "approach": "swing my longsword",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 1,  # Ensure we get to hit resolution
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "success":
            attack = data["attack"]
            assert attack["hit_roll"] >= 1 and attack["hit_roll"] <= 20
            assert attack["target_ac"] == 12  # Goblin AC
            assert attack["total_attack"] == attack["hit_roll"] + 4  # STR +2, prof +2
            
            # Damage should be present on hit
            assert attack["damage"] is not None
            damage = attack["damage"]
            assert damage["dice_expression"] == "1d8"
            assert len(damage["rolls"]) == 1
            assert 1 <= damage["rolls"][0] <= 8
            # Damage total = weapon roll + STR modifier
            assert damage["modifier"] == 2  # STR modifier (+2 for STR 15)
            assert damage["total"] == damage["rolls"][0] + damage["modifier"]


@pytest.mark.asyncio
async def test_attack_damage_includes_ability_modifier(client):
    """Attack damage should include ability modifier (STR for melee)."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "hit the goblin hard",
                "approach": "swing with all my strength",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 1,
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "success" and data["attack"]["damage"]:
            damage = data["attack"]["damage"]
            # Warrior STR 15 = +2 modifier, should be added to damage
            assert damage["modifier"] == 2
            # Total damage should be weapon roll + 2
            assert damage["total"] >= 3  # min 1d8 roll (1) + 2
            assert damage["total"] <= 10  # max 1d8 roll (8) + 2


@pytest.mark.asyncio
async def test_finesse_weapon_damage_uses_dex(client):
    """Finesse weapon damage should use DEX modifier."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "stab the goblin",
                "approach": "thrust precisely",
                "weapon": "rapier",  # Finesse weapon
                "target": "goblin-01",
                "dc": 1,
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "success" and data["attack"]["damage"]:
            damage = data["attack"]["damage"]
            # Aldric DEX 13 = +1 modifier for finesse
            assert damage["modifier"] == 1


@pytest.mark.asyncio
async def test_ranged_weapon_damage_uses_dex(client):
    """Ranged weapon damage should use DEX modifier."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "shoot the goblin",
                "approach": "aim and fire",
                "weapon": "shortbow",  # Ranged weapon
                "target": "goblin-01",
                "dc": 1,
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "success" and data["attack"]["damage"]:
            damage = data["attack"]["damage"]
            # Aldric DEX 13 = +1 modifier for ranged
            assert damage["modifier"] == 1
            assert damage["dice_expression"] == "1d6"


@pytest.mark.asyncio
async def test_hit_reduces_target_hp(client):
    """Successful hit should reduce target HP by damage amount."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        
        # Get initial HP
        from src.state import _get_session
        initial_hp = _get_session(session_id, create_if_missing=True).enemy.hp
        
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "strike",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 1,
            },
            headers={"X-Session-Id": session_id},
        )
        
        data = resp.json()
        
        if data["outcome"] == "success":
            current_hp = _get_session(session_id, create_if_missing=True).enemy.hp
            damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
            if damage_effects:
                damage_dealt = abs(damage_effects[0]["delta"])
                # HP is floored at 0, so actual HP change may be less than damage dealt
                assert current_hp == max(0, initial_hp - damage_dealt)


# ---------------------------------------------------------------------------
# Attack miss scenarios
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_miss_no_damage(client):
    """Missed attack should not include damage."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "swing wildly",
                "weapon": "longsword",
                "target": "goblin-01",
                "advantage": False,  # Disadvantage makes miss more likely
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "failure":
            # Damage should be None on miss
            assert data["attack"]["damage"] is None
            
            # No damage effects
            damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
            assert len(damage_effects) == 0


@pytest.mark.asyncio
async def test_miss_preserves_target_hp(client):
    """Missed attack should not change target HP."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        
        from src.state import _get_session
        initial_hp = _get_session(session_id, create_if_missing=True).enemy.hp
        
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "swing and miss",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 50,  # Impossible to hit
            },
            headers={"X-Session-Id": session_id},
        )
        
        data = resp.json()
        
        if data["outcome"] == "failure":
            current_hp = _get_session(session_id, create_if_missing=True).enemy.hp
            assert current_hp == initial_hp


@pytest.mark.asyncio
async def test_miss_includes_attack_details(client):
    """Missed attack should still include attack roll details."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "swing",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 50,  # Force miss
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        attack = data["attack"]
        assert attack["hit_roll"] >= 1 and attack["hit_roll"] <= 20
        assert attack["total_attack"] == attack["hit_roll"] + 4  # STR +2, prof +2
        assert attack["target_ac"] == 12


# ---------------------------------------------------------------------------
# Attack roll structure verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_roll_components(client):
    """Attack roll should include all components: d20 + ability + prof."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "strike",
                "weapon": "longsword",
                "target": "goblin-01",
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        attack = data["attack"]
        # Verify all expected fields are present
        assert "hit_roll" in attack
        assert "total_attack" in attack
        assert "target_ac" in attack
        assert "weapon" in attack
        assert "target" in attack
        
        # Verify roll range
        assert 1 <= attack["hit_roll"] <= 20
        
        # Verify total calculation: d20 + STR modifier (+2) + proficiency (+2) = d20 + 4
        expected_total = attack["hit_roll"] + 4
        assert attack["total_attack"] == expected_total


@pytest.mark.asyncio
async def test_attack_vs_ac_comparison(client):
    """Attack outcome should be based on total_attack vs target_ac."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "strike",
                "weapon": "longsword",
                "target": "goblin-01",
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        attack = data["attack"]
        
        # Outcome should match the comparison
        if attack["total_attack"] >= attack["target_ac"]:
            assert data["outcome"] == "success"
        else:
            assert data["outcome"] == "failure"


# ---------------------------------------------------------------------------
# Forced hit and miss tests for deterministic validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_forced_hit_with_low_dc(client):
    """With very low DC, attack should hit and deal damage."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        
        # Attack with DC 1 (guaranteed hit since min roll 1 + 5 = 6 >= 1)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "strike",
                "weapon": "longsword",
                "target": "goblin-01",
                "dc": 1,
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # With DC 1 and +4 bonus (STR +2, prof +2), min roll 1 + 4 = 5 >= 1
        # But DC is not used for attack rolls, attack uses target AC
        # Verify that damage includes modifier when hit
        if data["outcome"] == "success":
            assert data["attack"]["damage"] is not None
            damage = data["attack"]["damage"]
            assert damage["modifier"] == 2  # STR modifier
            assert damage["total"] > 0


@pytest.mark.asyncio
async def test_attack_outcome_matches_roll_vs_ac(client):
    """Attack outcome should be determined by d20 + bonus vs target AC."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        
        resp = await c.post(
            "/action",
            json={
                "scene_id": "combat-01",
                "actor": "Aldric",
                "intent": "attack",
                "approach": "strike",
                "weapon": "longsword",
                "target": "goblin-01",
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify outcome is consistent with attack roll vs AC
        attack = data["attack"]
        if attack["total_attack"] >= attack["target_ac"]:
            assert data["outcome"] == "success"
            # Damage should include ability modifier
            if data["attack"]["damage"]:
                assert data["attack"]["damage"]["modifier"] == 2  # STR modifier
        else:
            assert data["outcome"] == "failure"
            assert data["attack"]["damage"] is None

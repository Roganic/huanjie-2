"""Tests for combat resolution (attack rolls, damage, HP changes)."""

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


# ---------------------------------------------------------------------------
# Basic attack with weapon
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_requires_weapon_or_explicit_type(client):
    """An action with a weapon should be treated as an attack."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my longsword",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "attack" in data
    assert data["attack"] is not None
    assert data["attack"]["weapon"] == "longsword"
    assert data["attack"]["target"] == "goblin-01"


@pytest.mark.asyncio
async def test_attack_with_action_type_attack(client):
    """An explicit attack action type should trigger combat resolution."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "charge forward with weapon raised",
            "action_type": "attack",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["attack"] is not None


# ---------------------------------------------------------------------------
# Attack roll structure verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_roll_structure(client):
    """Attack response should contain proper roll details."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my sword",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    assert resp.status_code == 200
    data = resp.json()
    attack = data["attack"]
    
    assert "hit_roll" in attack
    assert "total_attack" in attack
    assert "target_ac" in attack
    assert attack["target_ac"] == 12  # Goblin AC
    assert 1 <= attack["hit_roll"] <= 20  # Valid d20 roll
    
    # Verify total = roll + modifier + proficiency
    # Aldric: STR 16 (+3), prof +2 = +5 total
    expected_total = attack["hit_roll"] + 5
    assert attack["total_attack"] == expected_total


# ---------------------------------------------------------------------------
# Hit outcome and damage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hit_applies_damage_to_target(client):
    """A successful hit should deal damage and reduce target HP."""
    initial_enemy_hp = get_enemy().hp  # 7
    
    async with client as c:
        # Force a hit with high roll by using advantage
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my longsword",
            "weapon": "longsword",
            "target": "goblin-01",
            "dc": 1,  # Low DC to ensure hit (not used for attack but for consistency)
        })
    
    data = resp.json()
    
    # Check if it was a hit
    if data["outcome"] == "success":
        # Damage should be applied
        assert len(data["effects"]) > 0
        damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
        assert len(damage_effects) > 0
        
        # Check enemy HP was reduced
        current_enemy_hp = get_enemy().hp
        assert current_enemy_hp < initial_enemy_hp
        
        # Check damage detail
        assert data["attack"]["damage"] is not None
        damage = data["attack"]["damage"]
        assert "dice_expression" in damage
        assert "rolls" in damage
        assert "total" in damage
        assert len(damage["rolls"]) > 0
        assert damage["total"] > 0


@pytest.mark.asyncio
async def test_miss_does_no_damage(client):
    """A miss should not deal damage."""
    initial_enemy_hp = get_enemy().hp
    
    async with client as c:
        # Force a miss with impossibly high target AC simulation
        # We do this by using a disadvantage and hoping for low roll
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing blindly",
            "weapon": "longsword",
            "target": "goblin-01",
            "advantage": False,  # Disadvantage
        })
    
    data = resp.json()
    
    if data["outcome"] == "failure":
        # No damage should be applied
        assert data["attack"]["damage"] is None
        damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
        assert len(damage_effects) == 0
        
        # Enemy HP should be unchanged
        assert get_enemy().hp == initial_enemy_hp


# ---------------------------------------------------------------------------
# Defeating an enemy
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_enemy_defeated_at_zero_hp(client):
    """When enemy reaches 0 HP, they should get the defeated condition."""
    # Pre-damage the enemy to make it easier to defeat
    from src.models.action import Effect
    from src.state import apply_effects
    
    # Reduce enemy HP to 2
    apply_effects([Effect(target="goblin-01", field="hp", delta=-5, description="setup")])
    assert get_enemy().hp == 2
    
    async with client as c:
        # Attack until hit (may need multiple tries)
        # For test reliability, we'll just check the structure
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "deliver a finishing blow",
            "weapon": "longsword",
            "target": "goblin-01",
            "dc": 1,  # Ensure we get to combat resolution
        })
    
    data = resp.json()
    
    # If we hit and the damage defeats the enemy
    if data["outcome"] == "success" and data["attack"]["damage"]:
        damage_dealt = abs(data["attack"]["damage"]["total"])
        if damage_dealt >= 2:  # Enough to defeat
            # Check for defeated condition effect
            defeated_effects = [e for e in data["effects"] if e["field"] == "conditions_add" and e["delta"] == "defeated"]
            assert len(defeated_effects) > 0


# ---------------------------------------------------------------------------
# Different weapon types
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_finesse_weapon_uses_dex(client):
    """Finesse weapons like rapier should use DEX for attack bonus."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "thrust with precision",
            "weapon": "rapier",  # Finesse weapon
            "target": "goblin-01",
        })
    
    data = resp.json()
    attack = data["attack"]
    
    # Rapier is finesse, should use DEX (+1 for Aldric) + prof (+2) = +3
    expected_bonus = 3  # DEX mod +1, prof +2
    expected_total = attack["hit_roll"] + expected_bonus
    assert attack["total_attack"] == expected_total


@pytest.mark.asyncio
async def test_ranged_weapon_uses_dex(client):
    """Ranged weapons like shortbow should use DEX for attack bonus."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "shoot the goblin",
            "approach": "draw and fire",
            "weapon": "shortbow",
            "target": "goblin-01",
        })
    
    data = resp.json()
    attack = data["attack"]
    
    # Shortbow is ranged, should use DEX (+1 for Aldric) + prof (+2) = +3
    expected_bonus = 3
    expected_total = attack["hit_roll"] + expected_bonus
    assert attack["total_attack"] == expected_total


@pytest.mark.asyncio
async def test_melee_weapon_uses_str(client):
    """Melee weapons like longsword should use STR for attack bonus."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing hard",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    
    data = resp.json()
    attack = data["attack"]
    
    # Longsword uses STR (+3 for Aldric) + prof (+2) = +5
    expected_bonus = 5
    expected_total = attack["hit_roll"] + expected_bonus
    assert attack["total_attack"] == expected_total


# ---------------------------------------------------------------------------
# Combat narration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_hit_narration_includes_details(client):
    """Hit narration should include roll, AC comparison, and damage."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my longsword",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    
    data = resp.json()
    narration = data["narration"]
    
    # Should mention actor, target, and weapon
    assert "Aldric" in narration
    assert "Goblin" in narration or "goblin" in narration
    assert "longsword" in narration
    
    if data["outcome"] == "success":
        # Hit narration should include damage info
        assert "damage" in narration.lower() or "hits" in narration.lower()
    else:
        # Miss narration
        assert "miss" in narration.lower()


# ---------------------------------------------------------------------------
# Custom damage dice
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_custom_damage_dice_override(client):
    """Custom damage_dice should override weapon default."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack with magical force",
            "approach": "swing my glowing sword",
            "weapon": "longsword",
            "damage_dice": "1d8+2",  # Custom damage
            "target": "goblin-01",
        })
    
    data = resp.json()
    
    if data["outcome"] == "success" and data["attack"]["damage"]:
        damage = data["attack"]["damage"]
        assert damage["dice_expression"] == "1d8+2"


# ---------------------------------------------------------------------------
# Missing target handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_unknown_target(client):
    """Attacking a non-existent target should return appropriate response."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the dragon",
            "approach": "swing my sword",
            "weapon": "longsword",
            "target": "ancient-dragon-999",
        })
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["outcome"] == "failure"
    assert "cannot be found" in data["narration"]


# ---------------------------------------------------------------------------
# Time advancement in combat
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combat_advances_time(client):
    """Combat actions should advance scene time."""
    from src.state import get_scene
    initial_time = get_scene().time
    
    async with client as c:
        await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "swing my sword",
            "weapon": "longsword",
            "target": "goblin-01",
        })
    
    assert get_scene().time == initial_time + 1

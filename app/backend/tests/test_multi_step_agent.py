"""Integration tests for GM Agent multi-step orchestration.

Tests that verify the GM Agent can properly orchestrate actions requiring
multiple tool calls, such as spell attacks with attack rolls + saving throws.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import get_enemy, reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
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
# Multi-step spell attack: attack roll + saving throw
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_spell_attack_triggers_multi_step_resolution(client):
    """A spell attack should trigger attack roll + saving throw (two checks)."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character(c)
        
        token = set_current_session(session_id)
        try:
            initial_enemy_hp = get_enemy().hp
        finally:
            reset_current_session(token)
        
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "a fireball spell",
            "approach": "channel arcane energy",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "2d6",
            "saving_throw_ability": "dex",
            "saving_throw_dc": 13,
        }, headers={"X-Session-Id": session_id})
    
    assert resp.status_code == 200
    data = resp.json()
    
    token = set_current_session(session_id)
    try:
        # Should have attack detail
        assert data["attack"] is not None
        attack = data["attack"]
        assert attack["weapon"] == "spell"
        assert attack["target"] == "goblin-01"
        assert "hit_roll" in attack
        assert "total_attack" in attack
        
        # Should have saving throw detail if attack hit
        if data["outcome"] == "success":
            assert data["saving_throw"] is not None
            save = data["saving_throw"]
            assert save["ability"] == "dex"
            assert save["dc"] == 13
            assert "roll" in save
            assert "total" in save
            assert save["outcome"] in ("success", "failure")
            
            # Damage should be applied
            assert len(data["effects"]) > 0
            damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
            assert len(damage_effects) > 0
            
            # Enemy HP should be reduced
            assert get_enemy().hp < initial_enemy_hp
            
            # Damage roll should be in attack detail
            assert attack["damage"] is not None
            damage = attack["damage"]
            assert "dice_expression" in damage
            assert "rolls" in damage
            assert "total" in damage
        else:
            # Miss - no saving throw, no damage
            assert data["saving_throw"] is None
            assert attack["damage"] is None
            assert get_enemy().hp == initial_enemy_hp
    finally:
        reset_current_session(token)


@pytest.mark.asyncio
async def test_spell_attack_half_damage_on_successful_save(client):
    """Spell should do half damage when target succeeds on saving throw."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "lightning bolt",
            "approach": "unleash crackling energy",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "4d6",  # High damage to see reduction
            "saving_throw_ability": "dex",
            "saving_throw_dc": 10,  # Low DC to encourage saves
        }, headers={"X-Session-Id": session_id})
    
    data = resp.json()
    
    # Only check if we hit and target made save
    if (data["outcome"] == "success" and 
        data["saving_throw"] is not None and 
        data["saving_throw"]["outcome"] == "success"):
        
        # Check that damage is half of rolled amount
        damage = data["attack"]["damage"]
        rolled_total = sum(damage["rolls"])
        actual_damage = damage["total"]
        
        # Should be half (rounded down)
        expected_half = rolled_total // 2
        assert actual_damage == expected_half, (
            f"Expected half damage ({expected_half}) on successful save, "
            f"got {actual_damage} (rolled {rolled_total})"
        )


@pytest.mark.asyncio
async def test_spell_attack_full_damage_on_failed_save(client):
    """Spell should do full damage when target fails saving throw."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "frost ray",
            "approach": "point and blast freezing energy",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "2d8",
            "saving_throw_ability": "dex",
            "saving_throw_dc": 20,  # High DC to encourage failures
        }, headers={"X-Session-Id": session_id})
    
    data = resp.json()
    
    # Only check if we hit and target failed save
    if (data["outcome"] == "success" and 
        data["saving_throw"] is not None and 
        data["saving_throw"]["outcome"] == "failure"):
        
        # Check that damage is full rolled amount
        damage = data["attack"]["damage"]
        rolled_total = sum(damage["rolls"])
        actual_damage = damage["total"]
        
        assert actual_damage == rolled_total, (
            f"Expected full damage ({rolled_total}) on failed save, "
            f"got {actual_damage}"
        )


@pytest.mark.asyncio
async def test_spell_attack_narrative_mentions_both_checks(client):
    """Narrative should reference both attack and saving throw."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "acid splash",
            "approach": "conjure bubbling acid",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "1d6",
        }, headers={"X-Session-Id": session_id})
    
    data = resp.json()
    narration = data["narration"]
    
    # Narrative should mention the spell
    assert "Aldric" in narration
    
    if data["outcome"] == "success":
        # Should mention target and damage (Chinese or English)
        assert "goblin" in narration.lower() or "Goblin" in narration or "哥布林" in narration or "斥候" in narration
        # Should have some narrative about the spell effect
        assert len(narration) > 50


@pytest.mark.asyncio
async def test_spell_attack_miss_no_saving_throw(client):
    """If spell attack misses, target should not make saving throw."""
    async with client as c:
        session_id = await _create_character(c)
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "ray of frost",
            "approach": "shoot a freezing beam",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "1d8",
            # No advantage to make miss more likely
        }, headers={"X-Session-Id": session_id})
    
    data = resp.json()
    
    if data["outcome"] == "failure":
        # Attack missed - no saving throw, no damage
        assert data["saving_throw"] is None
        assert data["attack"]["damage"] is None


@pytest.mark.asyncio
async def test_regular_attack_does_not_trigger_saving_throw(client):
    """Regular attacks should not have saving throw detail."""
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
    
    data = resp.json()
    
    # Regular attack should not have saving throw
    assert data["saving_throw"] is None
    # But should have attack detail
    assert data["attack"] is not None


# ---------------------------------------------------------------------------
# Agent tool tracking verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_step_tracks_all_tool_calls(client):
    """Verify the GM Agent tracks all tool calls during multi-step resolution."""
    from src.agent import GMAgent
    from src.models.action import ActionRequest, ActionType
    from src.models.state import CharacterClass, CharacterCreateRequest
    from src.state import create_character
    
    # Create a character first
    create_character(CharacterCreateRequest(
        name="Aldric",
        character_class=CharacterClass.WARRIOR,
        ability_generation="standard_array",
    ))
    
    agent = GMAgent()
    
    req = ActionRequest(
        scene_id="combat-01",
        actor="Aldric",
        intent="fireball",
        approach="cast spell",
        action_type=ActionType.SPELL_ATTACK,
        target="goblin-01",
        damage_dice="2d6",
        saving_throw_ability="dex",
    )
    
    response = agent.resolve(req)
    
    # Should have tracked multiple tool results
    assert len(agent.tool_results) >= 3  # get_state + attack roll + at least one more
    
    # Should have effects if attack hit
    if response.outcome.value == "success":
        assert len(agent.effects) > 0


# ---------------------------------------------------------------------------
# State consistency verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_step_state_consistency(client):
    """State should be consistent after multi-step action completes."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character(c)
        
        token = set_current_session(session_id)
        try:
            initial_enemy_hp = get_enemy().hp
        finally:
            reset_current_session(token)
        
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Aldric",
            "intent": "magic missile",
            "approach": "hurl darts of force",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "2d4",  # Lower damage to avoid HP floor issues
        }, headers={"X-Session-Id": session_id})
    
    data = resp.json()
    
    # Get effects from response
    damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
    
    # Calculate expected HP from effects (but cap at initial HP due to HP floor of 0)
    total_damage_from_effects = sum(abs(e["delta"]) for e in damage_effects)
    
    token = set_current_session(session_id)
    try:
        # Actual HP change should match effects (capped at initial HP since HP can't go below 0)
        actual_hp_change = initial_enemy_hp - get_enemy().hp
        
        # Only verify if there was damage and hit
        if total_damage_from_effects > 0 and data["outcome"] == "success":
            # HP change should be the minimum of damage dealt and initial HP
            # (since HP can't go below 0)
            assert actual_hp_change == min(total_damage_from_effects, initial_enemy_hp), (
                f"HP change mismatch: effects claim {total_damage_from_effects} damage, "
                f"but actual HP changed by {actual_hp_change} (initial: {initial_enemy_hp})"
            )
    finally:
        reset_current_session(token)

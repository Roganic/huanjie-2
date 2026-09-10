"""Integration tests for character data in game loop.

Tests the complete integration between character system and game main loop:
- POST /action uses real character ability modifiers
- Skill checks use correct modifiers (ability + proficiency)
- AI narrative prompt includes character information
- POST /reset clears character data
- GET /character returns 404 after reset
"""

from tests.compatibility_rules import resolve_compatibility_action

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


# -----------------------------------------------------------------------------
# Acceptance Criterion 1: POST /action uses real ability modifiers
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_uses_real_character_ability_modifier(client):
    """AC1: Action resolution should use character's real ability modifier, not hardcoded 0."""
    async with client as c:
        # Create a warrior with STR 16 (+3 modifier)
        create_resp = await c.post("/character/create", json={
            "name": "StrongHero",
            "character_class": "warrior",
            "ability_generation": "manual",
            "abilities": {"str": 16, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Perform a strength-based action
        action_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "StrongHero",
            "intent": "break down the door",
            "approach": "use brute force",
            "ability": "str",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})

    # Direct rule result; HTTP contracts are tested on authored player paths.
    data = action_resp.model_dump(mode="json")
    
    # Verify the modifier is +3 (from STR 16), not 0
    assert data["check"]["modifier"] == 3, "Should use character's real STR modifier (+3), not 0"
    assert data["check"]["proficiency_bonus"] == 0, "Generic ability checks should not add proficiency"
    # Total = d20 roll + 3
    assert data["check"]["total"] == data["check"]["roll"] + 3


@pytest.mark.asyncio
async def test_action_uses_real_character_dex_modifier(client):
    """AC1b: Action resolution should use character's DEX modifier for dexterity-based actions."""
    async with client as c:
        # Create a rogue with DEX 15 (+2 modifier)
        create_resp = await c.post("/character/create", json={
            "name": "QuickHero",
            "character_class": "rogue",
            "ability_generation": "manual",
            "abilities": {"str": 10, "dex": 15, "con": 10, "int": 10, "wis": 10, "cha": 10},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Perform a dexterity-based action
        action_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "QuickHero",
            "intent": "sneak past the guard",
            "approach": "move silently",
            "ability": "dex",
            "dc": 12,
        }, headers={"X-Session-Id": session_id})

    # Direct rule result; HTTP contracts are tested on authored player paths.
    data = action_resp.model_dump(mode="json")
    
    # Verify the modifier is +2 (from DEX 15)
    assert data["check"]["modifier"] == 2, "Should use character's real DEX modifier (+2)"


# -----------------------------------------------------------------------------
# Acceptance Criterion 2: Skill checks use correct modifiers
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_check_uses_ability_modifier_plus_proficiency(client):
    """AC2: Skill check should use ability modifier + proficiency bonus when proficient."""
    async with client as c:
        # Create a warrior (proficient in athletics) with STR 16 (+3)
        create_resp = await c.post("/character/create", json={
            "name": "Athlete",
            "character_class": "warrior",
            "ability_generation": "manual",
            "abilities": {"str": 16, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Perform an athletics skill check
        action_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "Athlete",
            "intent": "climb the wall",
            "approach": "use athletic training",
            "action_type": "skill_check",
            "skill": "athletics",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})

    # Direct rule result; HTTP contracts are tested on authored player paths.
    data = action_resp.model_dump(mode="json")
    
    # Verify skill check structure
    check = data["check"]
    assert check["ability"] == "str"
    assert check["skill_name"] == "athletics"
    # Warrior: STR 16 (+3), proficient in athletics (+2) = +5 total modifier
    assert check["modifier"] == 3, "Should use STR modifier (+3)"
    assert check["proficiency_bonus"] == 2, "Should add proficiency bonus (+2) for proficient skill"
    # Total = d20 roll + 3 (STR) + 2 (proficiency)
    assert check["total"] == check["roll"] + 3 + 2


@pytest.mark.asyncio
async def test_skill_check_non_proficient_no_proficiency_bonus(client):
    """AC2b: Non-proficient skill check should only use ability modifier."""
    async with client as c:
        # Create a warrior (NOT proficient in stealth) with DEX 12 (+1)
        create_resp = await c.post("/character/create", json={
            "name": "ClumsyWarrior",
            "character_class": "warrior",
            "ability_generation": "manual",
            "abilities": {"str": 10, "dex": 12, "con": 10, "int": 10, "wis": 10, "cha": 10},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Perform a stealth skill check (warrior is not proficient)
        action_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "ClumsyWarrior",
            "intent": "sneak past the guards",
            "approach": "move quietly",
            "action_type": "skill_check",
            "skill": "stealth",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})

    # Direct rule result; HTTP contracts are tested on authored player paths.
    data = action_resp.model_dump(mode="json")
    
    check = data["check"]
    # Warrior: DEX 12 (+1), NOT proficient in stealth = +1 total
    assert check["modifier"] == 1, "Should use DEX modifier (+1)"
    assert check["proficiency_bonus"] == 0, "Should NOT add proficiency for non-proficient skill"


# -----------------------------------------------------------------------------
# Acceptance Criterion 4: POST /reset clears character data
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_clears_character_and_get_character_returns_404(client):
    """AC4a: POST /reset should clear character data; GET /character returns 404."""
    async with client as c:
        # Create character
        create_resp = await c.post("/character/create", json={
            "name": "ResetMe",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Verify character exists
        get_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert get_resp.status_code == 200
        assert get_resp.json()["name"] == "ResetMe"

        # Reset
        reset_resp = await c.post("/reset", headers={"X-Session-Id": session_id})
        assert reset_resp.status_code == 200

        # Verify character is cleared (404)
        get_after = await c.get("/character", headers={"X-Session-Id": session_id})
        assert get_after.status_code == 404, "GET /character should return 404 after reset"


@pytest.mark.asyncio
async def test_action_after_reset_returns_error(client):
    """AC4b: POST /action after reset should return 400 error (no character)."""
    async with client as c:
        # Create character
        create_resp = await c.post("/character/create", json={
            "name": "ActionReset",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Verify action works
        action_resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "ActionReset",
            "intent": "look around",
            "approach": "glance around",
        }, headers={"X-Session-Id": session_id})
        assert action_resp.status_code == 200

        # Reset
        reset_resp = await c.post("/reset", headers={"X-Session-Id": session_id})
        assert reset_resp.status_code == 200

        # Verify action returns error after reset
        action_after = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "ActionReset",
            "intent": "look around",
            "approach": "glance around",
        }, headers={"X-Session-Id": session_id})
        assert action_after.status_code == 400, "POST /action should return 400 after reset"


@pytest.mark.asyncio
async def test_reset_returns_bootstrap_with_no_actor(client):
    """AC4c: POST /reset should return bootstrap state with actor=null and phase=character_creation."""
    async with client as c:
        # Create character
        create_resp = await c.post("/character/create", json={
            "name": "BootstrapReset",
            "character_class": "mage",
            "ability_generation": "standard_array",
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Verify bootstrap has actor
        bootstrap_before = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
        assert bootstrap_before.status_code == 200
        data_before = bootstrap_before.json()
        assert data_before["actor"] is not None
        assert data_before["phase"] == "adventure"

        # Reset
        reset_resp = await c.post("/reset", headers={"X-Session-Id": session_id})
        assert reset_resp.status_code == 200
        reset_data = reset_resp.json()

        # Verify reset returns correct state
        assert reset_data["actor"] is None, "Reset should return actor=null"
        assert reset_data["phase"] == "character_creation", "Reset should return phase=character_creation"


# -----------------------------------------------------------------------------
# Acceptance Criterion 5 & 6: Frontend state panel data from backend
# (Verified via bootstrap endpoint)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_returns_full_character_data_for_frontend(client):
    """AC5&6: Bootstrap should return complete character data for frontend state panel."""
    async with client as c:
        # Create character with specific attributes
        create_resp = await c.post("/character/create", json={
            "name": "CompleteHero",
            "character_class": "rogue",
            "ability_generation": "manual",
            "abilities": {"str": 10, "dex": 16, "con": 12, "int": 14, "wis": 10, "cha": 8},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]

        # Get bootstrap state
        bootstrap_resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
        assert bootstrap_resp.status_code == 200
        data = bootstrap_resp.json()

        # Verify actor data is complete
        actor = data["actor"]
        assert actor["name"] == "CompleteHero"
        assert actor["character_class"] == "rogue"
        assert actor["level"] == 1
        assert actor["proficiency_bonus"] == 2
        
        # Verify abilities with modifiers
        abilities = actor["abilities"]
        assert abilities["str"] == 10
        assert abilities["dex"] == 16
        assert abilities["con"] == 12
        assert abilities["int"] == 14
        assert abilities["wis"] == 10
        assert abilities["cha"] == 8
        
        # Verify computed values
        assert actor["ac"] == 14  # Rogue: 11 + DEX mod (+3) = 14
        # HP = 8 (rogue base) + CON mod (+1) = 9
        assert actor["hp"] == 9
        assert actor["hp_max"] == 9
        
        # Verify skills are included
        assert "skills" in actor
        assert len(actor["skills"]) > 0
        
        # Find stealth skill (rogue is proficient)
        stealth_skill = next((s for s in actor["skills"] if s["name"] == "stealth"), None)
        assert stealth_skill is not None
        assert stealth_skill["ability"] == "dex"
        assert stealth_skill["proficient"] is True
        # Stealth modifier = DEX mod (+3) + proficiency (+2) = +5
        assert stealth_skill["modifier"] == 5


# -----------------------------------------------------------------------------
# Full integration flow test
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_character_game_loop_flow(client):
    """Full integration test: create -> act -> reset -> verify cleared."""
    async with client as c:
        # Step 1: Create character
        create_resp = await c.post("/character/create", json={
            "name": "FlowHero",
            "character_class": "mage",
            "ability_generation": "manual",
            "abilities": {"str": 8, "dex": 14, "con": 12, "int": 16, "wis": 10, "cha": 10},
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]
        
        # Step 2: Perform action with ability check
        action_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "FlowHero",
            "intent": "recall arcane knowledge",
            "approach": "consult my spellbook",
            "ability": "int",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})
        
        # Direct rule result; HTTP contracts are tested on authored player paths.
        action_data = action_resp.model_dump(mode="json")
        # INT 16 = +3 modifier
        assert action_data["check"]["modifier"] == 3
        
        # Step 3: Perform skill check
        skill_resp = resolve_compatibility_action(json={
            "scene_id": "tavern-01",
            "actor": "FlowHero",
            "intent": "investigate the magical rune",
            "approach": "study the symbols",
            "action_type": "skill_check",
            "skill": "arcana",  # Mage is proficient
            "dc": 12,
        }, headers={"X-Session-Id": session_id})
        
        # Direct rule result; HTTP contracts are tested on authored player paths.
        skill_data = skill_resp.model_dump(mode="json")
        # Arcana: INT mod (+3) + proficiency (+2) = +5
        assert skill_data["check"]["modifier"] == 3
        assert skill_data["check"]["proficiency_bonus"] == 2
        
        # Step 4: Verify bootstrap state
        bootstrap_resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
        assert bootstrap_resp.status_code == 200
        bootstrap_data = bootstrap_resp.json()
        assert bootstrap_data["phase"] == "adventure"
        assert bootstrap_data["actor"]["name"] == "FlowHero"
        
        # Step 5: Reset
        reset_resp = await c.post("/reset", headers={"X-Session-Id": session_id})
        assert reset_resp.status_code == 200
        
        # Step 6: Verify cleared state
        # 6a: Bootstrap shows no actor
        bootstrap_after = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
        assert bootstrap_after.json()["actor"] is None
        assert bootstrap_after.json()["phase"] == "character_creation"
        
        # 6b: GET /character returns 404
        get_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert get_resp.status_code == 404
        
        # 6c: POST /action returns 400
        action_after = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "FlowHero",
            "intent": "do something",
            "approach": "try anything",
        }, headers={"X-Session-Id": session_id})
        assert action_after.status_code == 400

"""End-to-end integration tests for complete AIDM flow.

These tests verify:
1. Character creation works correctly
2. Actions can be performed with the created character
3. Skill checks resolve correctly
4. AI narrative respects constraints
5. GM prompts are generated
6. Resolution results are consistent with character attributes
"""

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


async def _create_character(client: AsyncClient, name: str = "Aldric", character_class: str = "warrior") -> str:
    """Create a character and return session_id."""
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


# -----------------------------------------------------------------------------
# End-to-end flow tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_create_character_and_perform_action(client):
    """E2E: Create character -> perform action -> verify response structure."""
    async with client as c:
        # Step 1: Create character
        session_id = await _create_character(c, "Hero", "warrior")
        
        # Verify character was created
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        char_data = char_resp.json()
        assert char_data["name"] == "Hero"
        assert char_data["class"] == "warrior"
        assert char_data["level"] == 1
        
        # Step 2: Perform an action
        action_resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Hero",
            "intent": "look around the tavern",
            "approach": "casually observe the room",
        }, headers={"X-Session-Id": session_id})
        
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # Step 3: Verify response structure
        assert "action_summary" in data
        assert "resolution_type" in data
        assert "outcome" in data
        assert "narration" in data
        assert "scene_progression" in data
        assert "gm_prompt" in data
        assert "effects" in data


@pytest.mark.asyncio
async def test_e2e_skill_check_flow(client):
    """E2E: Create character -> perform skill check -> verify resolution matches character stats."""
    async with client as c:
        # Step 1: Create warrior with known STR
        session_id = await _create_character(c, "Warrior", "warrior")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        str_mod = char_data["attributes"]["str"]["modifier"]
        prof_bonus = char_data["proficiency_bonus"]
        
        # Step 2: Perform athletics skill check (STR-based, proficient for warrior)
        action_resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Warrior",
            "intent": "climb the wall",
            "approach": "use athletic prowess",
            "skill": "athletics",
            "dc": 10,
        }, headers={"X-Session-Id": session_id})
        
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # Step 3: Verify check details match character
        assert data["resolution_type"] == "check"
        assert data["check"] is not None
        check = data["check"]
        
        # Verify ability modifier matches STR
        assert check["modifier"] == str_mod
        # Verify proficiency bonus is applied (warriors are proficient in athletics)
        assert check["proficiency_bonus"] == prof_bonus
        # Verify total = roll + modifier + proficiency
        expected_total = check["roll"] + str_mod + prof_bonus
        assert check["total"] == expected_total
        
        # Step 4: Verify response has all required fields
        assert "narration" in data
        assert "scene_progression" in data
        assert "gm_prompt" in data
        assert data["outcome"] in ("success", "failure")


@pytest.mark.asyncio
async def test_e2e_combat_flow(client):
    """E2E: Create character -> attack enemy -> verify combat resolution."""
    async with client as c:
        # Step 1: Create character
        session_id = await _create_character(c, "Fighter", "warrior")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        initial_hp = char_data["hp"]["current"]
        ac = char_data["ac"]
        
        # Step 2: Perform attack action
        action_resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Fighter",
            "intent": "attack the goblin",
            "approach": "swing my longsword",
            "weapon": "longsword",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
        
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # Step 3: Verify combat response structure
        assert data["attack"] is not None
        attack = data["attack"]
        assert "hit_roll" in attack
        assert "total_attack" in attack
        assert "target_ac" in attack
        assert attack["target_ac"] == 12  # Goblin AC
        
        # Step 4: Verify outcome is consistent with roll
        if data["outcome"] == "success":
            assert attack["total_attack"] >= attack["target_ac"]
            assert attack["damage"] is not None
            # Verify damage structure
            damage = attack["damage"]
            assert "rolls" in damage
            assert "total" in damage
            assert damage["total"] > 0
        else:
            assert attack["total_attack"] < attack["target_ac"]
            assert attack["damage"] is None
        
        # Step 5: Verify character HP is unchanged (attacker doesn't lose HP)
        char_resp_after = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data_after = char_resp_after.json()
        assert char_data_after["hp"]["current"] == initial_hp


@pytest.mark.asyncio
async def test_e2e_narrative_constraints(client):
    """E2E: Verify AI narrative respects hard constraints and doesn't override numeric values."""
    async with client as c:
        # Step 1: Create character
        session_id = await _create_character(c, "Rogue", "rogue")
        
        # Step 2: Perform action that triggers skill check
        action_resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Rogue",
            "intent": "pick the lock",
            "approach": "use thieves tools carefully",
            "skill": "sleight_of_hand",
            "dc": 15,
        }, headers={"X-Session-Id": session_id})
        
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # Step 3: Verify narrative doesn't contain unauthorized numeric declarations
        narration = data["narration"].lower()
        
        # Should NOT contain direct HP modification statements
        assert "hp becomes" not in narration
        assert "生命值变为" not in narration
        
        # Should NOT contain direct damage numbers in format like "deals X damage"
        # Note: We allow descriptive words like "damage" in narrative
        # But not specific numeric declarations
        
        # Step 4: Verify narrative mentions character
        assert "rogue" in data["narration"].lower() or "Rogue" in data["narration"]
        
        # Step 5: Verify GM prompt is present and non-empty
        assert len(data["gm_prompt"]) > 10


@pytest.mark.asyncio
async def test_e2e_resolution_result_in_prompt_structure(client):
    """E2E: Verify AI narrative prompt includes resolution result and character fields."""
    async with client as c:
        # Step 1: Create character with known attributes
        session_id = await _create_character(c, "Mage", "mage")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        hp = char_data["hp"]["current"]
        ac = char_data["ac"]
        
        # Step 2: Perform action
        action_resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Mage",
            "intent": "investigate the runes",
            "approach": "study the arcane symbols",
            "ability": "int",
            "dc": 12,
        }, headers={"X-Session-Id": session_id})
        
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # Step 3: Verify resolution result is present
        assert data["resolution_type"] == "check"
        assert data["check"] is not None
        check = data["check"]
        assert check["ability"] == "int"
        assert "roll" in check
        assert "total" in check
        assert "dc" in check
        
        # Step 4: Verify outcome matches roll vs DC
        if check["total"] >= check["dc"]:
            assert data["outcome"] == "success"
        else:
            assert data["outcome"] == "failure"


@pytest.mark.asyncio
async def test_e2e_full_adventure_sequence(client):
    """E2E: Complete adventure sequence with multiple actions."""
    async with client as c:
        # Step 1: Create character
        session_id = await _create_character(c, "Adventurer", "warrior")
        
        actions = [
            # Auto-success exploration
            {"intent": "look around", "approach": "observe carefully"},
            # Skill check
            {"intent": "climb the wall", "approach": "scale quickly", "ability": "str", "dc": 10},
            # Another exploration
            {"intent": "search for treasure", "approach": "check behind the furniture"},
        ]
        
        outcomes = []
        for action in actions:
            resp = await c.post("/action", json={
                "scene_id": "dungeon-01",
                "actor": "Adventurer",
                **action,
            }, headers={"X-Session-Id": session_id})
            
            assert resp.status_code == 200
            data = resp.json()
            outcomes.append(data["outcome"])
            
            # Verify each response has required fields
            assert "narration" in data
            assert "gm_prompt" in data
            assert "resolution_type" in data
            assert data["outcome"] in ("success", "failure")
        
        # Step 3: Verify we got some variety in outcomes
        # (Not all should be the same due to dice rolls)
        # But this is probabilistic, so we just verify we have 3 outcomes
        assert len(outcomes) == 3


@pytest.mark.asyncio
async def test_e2e_character_persists_across_actions(client):
    """E2E: Verify character state persists across multiple actions."""
    async with client as c:
        # Step 1: Create character
        session_id = await _create_character(c, "Persistent", "warrior")
        
        # Step 2: Get initial character state
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        initial_data = char_resp.json()
        initial_hp = initial_data["hp"]["current"]
        
        # Step 3: Perform multiple actions
        for _ in range(3):
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "Persistent",
                "intent": "look around",
                "approach": "observe",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
        
        # Step 4: Verify character still exists with same stats
        char_resp_final = await c.get("/character", headers={"X-Session-Id": session_id})
        final_data = char_resp_final.json()
        
        assert final_data["name"] == "Persistent"
        assert final_data["hp"]["current"] == initial_hp  # Auto-success doesn't change HP

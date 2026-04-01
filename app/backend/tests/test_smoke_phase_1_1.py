"""Smoke tests for Phase 1.1 Character System milestone acceptance.

These tests verify end-to-end player experience:
1. Create character
2. Execute 3+ actions
3. Verify narrative includes character name and class features
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


async def _create_character(
    client: AsyncClient,
    name: str = "TestHero",
    character_class: str = "warrior"
) -> str:
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


@pytest.mark.asyncio
async def test_smoke_warrior_three_actions_with_narrative(client):
    """Smoke test: Create warrior → 3 actions → narrative includes name and class."""
    async with client as c:
        # Step 1: Create warrior character
        session_id = await _create_character(c, "Grimjaw", "warrior")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        char_data = char_resp.json()
        assert char_data["name"] == "Grimjaw"
        assert char_data["class"] == "warrior"
        
        # Step 2: Execute 3 distinct actions
        actions = [
            {
                "scene_id": "tavern-01",
                "actor": "Grimjaw",
                "intent": "look around the tavern",
                "approach": "scan the room for threats",
            },
            {
                "scene_id": "tavern-01",
                "actor": "Grimjaw",
                "intent": "intimidate the troublemaker",
                "approach": "flex muscles and stare menacingly",
                "ability": "str",
            },
            {
                "scene_id": "tavern-01",
                "actor": "Grimjaw",
                "intent": "attack the goblin",
                "approach": "swing my longsword with force",
                "weapon": "longsword",
                "target": "goblin-01",
            },
        ]
        
        results = []
        for action in actions:
            resp = await c.post("/action", json=action, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            data = resp.json()
            results.append(data)
            
            # Verify basic response structure
            assert "narration" in data
            assert "outcome" in data
            assert data["outcome"] in ("success", "failure")
        
        # Step 3: Verify narrative includes character name in all responses
        for result in results:
            assert "Grimjaw" in result["narration"], "Narration should mention character name"
        
        # Step 4: Verify combat action includes warrior-appropriate elements
        combat_result = results[2]
        assert combat_result["attack"] is not None
        narration = combat_result["narration"].lower()
        
        # Should mention combat elements appropriate to warrior
        assert "longsword" in narration or "sword" in narration or "weapon" in narration


@pytest.mark.asyncio
async def test_smoke_mage_three_actions_with_narrative(client):
    """Smoke test: Create mage → 3 actions → narrative includes name and class features."""
    async with client as c:
        # Step 1: Create mage character
        session_id = await _create_character(c, "Starweaver", "mage")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        char_data = char_resp.json()
        assert char_data["name"] == "Starweaver"
        assert char_data["class"] == "mage"
        # Mages have lower HP
        assert char_data["hp"]["max"] <= 8  # 6 + up to 2 CON mod
        
        # Step 2: Execute 3 distinct actions showing mage characteristics
        actions = [
            {
                "scene_id": "library-01",
                "actor": "Starweaver",
                "intent": "study the ancient runes",
                "approach": "examine the arcane symbols carefully",
                "ability": "int",
            },
            {
                "scene_id": "library-01",
                "actor": "Starweaver",
                "intent": "recall historical lore",
                "approach": "search my memory for relevant knowledge",
                "skill": "history",
            },
            {
                "scene_id": "library-01",
                "actor": "Starweaver",
                "intent": "identify the magical essence",
                "approach": "use my arcane training to sense magic",
                "skill": "arcana",
            },
        ]
        
        results = []
        for action in actions:
            resp = await c.post("/action", json=action, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            data = resp.json()
            results.append(data)
            
            # Verify narrative includes character name
            assert "Starweaver" in data["narration"]
        
        # Step 3: Verify skill checks used INT modifier
        for result in results[1:]:  # Last two actions used skills
            assert result["resolution_type"] == "check"
            assert result["check"]["ability"] == "int"


@pytest.mark.asyncio
async def test_smoke_rogue_three_actions_with_narrative(client):
    """Smoke test: Create rogue → 3 actions → narrative includes name and class features."""
    async with client as c:
        # Step 1: Create rogue character
        session_id = await _create_character(c, "Shadowstep", "rogue")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        char_data = char_resp.json()
        assert char_data["name"] == "Shadowstep"
        assert char_data["class"] == "rogue"
        # Rogues have leather armor AC
        assert char_data["ac"] >= 13  # 11 + at least +1 DEX (DEX 13 for standard array rogue)
        
        # Step 2: Execute 3 distinct actions showing rogue characteristics
        actions = [
            {
                "scene_id": "alley-01",
                "actor": "Shadowstep",
                "intent": "sneak past the guards",
                "approach": "move silently through the shadows",
                "skill": "stealth",
            },
            {
                "scene_id": "alley-01",
                "actor": "Shadowstep",
                "intent": "pick the merchant's pocket",
                "approach": "deftly lift the coin purse without being noticed",
                "skill": "sleight_of_hand",
            },
            {
                "scene_id": "alley-01",
                "actor": "Shadowstep",
                "intent": "scale the wall",
                "approach": "climb using agility and grip",
                "skill": "acrobatics",
            },
        ]
        
        results = []
        for action in actions:
            resp = await c.post("/action", json=action, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            data = resp.json()
            results.append(data)
            
            # Verify narrative includes character name
            assert "Shadowstep" in data["narration"]
        
        # Step 3: Verify rogue skills used DEX modifier
        for result in results:
            assert result["resolution_type"] == "check"
            assert result["check"]["ability"] == "dex"
            # Rogues are proficient in all three skills
            assert result["check"]["proficiency_bonus"] == 2


@pytest.mark.asyncio
async def test_smoke_character_state_persists_across_multiple_actions(client):
    """Smoke test: Character state persists correctly across multiple actions."""
    async with client as c:
        # Create character
        session_id = await _create_character(c, "Tank", "warrior")
        
        # Get initial state
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        initial_data = char_resp.json()
        initial_name = initial_data["name"]
        initial_class = initial_data["class"]
        initial_level = initial_data["level"]
        
        # Execute 5 actions
        for i in range(5):
            resp = await c.post("/action", json={
                "scene_id": "dungeon-01",
                "actor": "Tank",
                "intent": f"action {i+1}: explore the area",
                "approach": "proceed with caution",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
        
        # Verify character still exists with consistent core state
        final_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        final_data = final_resp.json()
        
        # Core character identity should persist
        assert final_data["name"] == initial_name
        assert final_data["class"] == initial_class
        assert final_data["level"] == initial_level
        # Character should still exist
        assert final_data["hp"]["current"] >= 0

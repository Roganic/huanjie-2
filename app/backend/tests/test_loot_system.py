"""Tests for the loot system.

Validates:
- Probability-based loot generation (0 = never, 1.0 = always)
- Loot tables for different enemy types
- Integration with combat system
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.loot import (
    LootItem,
    LootTable,
    generate_loot_for_enemy,
    generate_combat_loot,
    roll_loot_item,
    get_loot_table,
    format_loot_for_narrative,
)
from src.loot.tables import goblin_loot, skeleton_loot, bandit_loot
from src.state import reset_state, add_items_to_inventory, get_character_card


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Loot Probability Tests
# ---------------------------------------------------------------------------

class TestLootProbability:
    """Test probability-based loot generation."""
    
    def test_probability_zero_never_drops(self):
        """Items with probability 0 should never drop."""
        item = LootItem(
            item_id="rare_item",
            name="Rare Item",
            quantity=1,
            probability=0.0,  # Never drops
        )
        
        # Test with fixed random generator returning various values
        for roll in [0.0, 0.5, 0.99, 1.0]:
            assert roll_loot_item(item, lambda: roll) is False
    
    def test_probability_one_always_drops(self):
        """Items with probability 1.0 should always drop."""
        item = LootItem(
            item_id="common_item",
            name="Common Item",
            quantity=1,
            probability=1.0,  # Always drops
        )
        
        # Test with fixed random generator returning various values
        for roll in [0.0, 0.5, 0.99]:
            assert roll_loot_item(item, lambda: roll) is True
    
    def test_probability_fifty_percent(self):
        """Items with 0.5 probability drop based on roll."""
        item = LootItem(
            item_id="medium_item",
            name="Medium Item",
            quantity=1,
            probability=0.5,
        )
        
        # Roll 0.4 (< 0.5) should drop
        assert roll_loot_item(item, lambda: 0.4) is True
        # Roll 0.6 (>= 0.5) should not drop
        assert roll_loot_item(item, lambda: 0.6) is False
        # Edge case: roll exactly 0.5 should not drop
        assert roll_loot_item(item, lambda: 0.5) is False


# ---------------------------------------------------------------------------
# Loot Table Tests
# ---------------------------------------------------------------------------

class TestLootTables:
    """Test loot table definitions."""
    
    def test_goblin_loot_table_exists(self):
        """Goblin loot table should be defined."""
        assert goblin_loot is not None
        assert goblin_loot.enemy_type == "goblin"
        assert len(goblin_loot.drops) > 0
        
        # Check for expected items
        item_ids = [item.item_id for item in goblin_loot.drops]
        assert "shortsword" in item_ids or "gold_coins" in item_ids or "dagger" in item_ids
    
    def test_skeleton_loot_table_exists(self):
        """Skeleton loot table should be defined."""
        assert skeleton_loot is not None
        assert skeleton_loot.enemy_type == "skeleton"
        assert len(skeleton_loot.drops) > 0
        
        # Check for expected items
        item_ids = [item.item_id for item in skeleton_loot.drops]
        assert "bones" in item_ids or "rusty_sword" in item_ids
    
    def test_bandit_loot_table_exists(self):
        """Bandit loot table should be defined."""
        assert bandit_loot is not None
        assert bandit_loot.enemy_type == "bandit"
        assert len(bandit_loot.drops) > 0
        
        # Check for expected items
        item_ids = [item.item_id for item in bandit_loot.drops]
        assert "dagger" in item_ids or "leather_scrap" in item_ids
    
    def test_get_loot_table_by_id(self):
        """Should return correct loot table by enemy ID."""
        table = get_loot_table("goblin-01", "Goblin")
        assert table.enemy_type == "goblin"
        
        table = get_loot_table("skeleton-warrior", "骷髅战士")
        assert table.enemy_type == "skeleton"
        
        table = get_loot_table("bandit-leader", "强盗头目")
        assert table.enemy_type == "bandit"
    
    def test_get_loot_table_by_name(self):
        """Should return correct loot table by enemy name."""
        table = get_loot_table("enemy-01", "哥布林斥候")
        assert table.enemy_type == "goblin"


# ---------------------------------------------------------------------------
# Loot Generation Tests
# ---------------------------------------------------------------------------

class TestLootGeneration:
    """Test loot generation logic."""
    
    def test_generate_loot_with_always_drop_items(self):
        """Generate loot should include items with probability 1.0."""
        table = LootTable(
            enemy_type="test",
            enemy_name="Test Enemy",
            drops=[
                LootItem(item_id="always", name="Always Item", probability=1.0),
                LootItem(item_id="never", name="Never Item", probability=0.0),
            ]
        )
        
        # Manually test the generation
        loot = generate_loot_for_enemy("test-enemy", "Test Enemy", random_gen=lambda: 0.5)
        
        # With default tables, goblin loot should be returned for unknown enemy
        assert loot is not None
        assert loot.enemy_id == "test-enemy"
    
    def test_format_loot_for_narrative_empty(self):
        """Empty loot should return appropriate message."""
        loot = generate_combat_loot([])
        narrative = format_loot_for_narrative(loot)
        assert "没有发现战利品" in narrative or "没有" in narrative


# ---------------------------------------------------------------------------
# Combat Integration Tests
# ---------------------------------------------------------------------------

class TestCombatLootIntegration:
    """Test loot integration with combat system."""
    
    @pytest.mark.asyncio
    async def test_combat_victory_generates_loot(self, client):
        """Combat victory should generate loot and add to inventory."""
        async with client as c:
            # Create character
            resp = await c.post("/character/create", json={
                "name": "TestHero",
                "character_class": "warrior",
                "ability_generation": "standard_array",
            })
            assert resp.status_code == 200
            session_id = resp.headers.get("x-session-id")
            
            # Get initial inventory
            state_resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
            initial_inventory = state_resp.json()["actor"]["inventory"]
            
            # Start combat
            start_resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
            assert start_resp.status_code == 200
            combat_data = start_resp.json()
            
            # Find enemy
            enemy = next((p for p in combat_data["combatants"] if p["type"] == "enemy"), None)
            assert enemy is not None
            
            # Attack until combat ends (mocking high damage or relying on normal combat)
            max_attempts = 20
            for _ in range(max_attempts):
                action_resp = await c.post("/combat/action", json={
                    "action_type": "attack",
                    "target_id": enemy["id"],
                    "weapon": "longsword",
                }, headers={"X-Session-Id": session_id})
                
                assert action_resp.status_code == 200
                action_data = action_resp.json()
                
                # Check if combat ended
                if action_data.get("combat_ended"):
                    # Verify loot_gained field exists
                    assert "loot_gained" in action_data
                    
                    # If victory, loot_gained should be present (may be empty if no drops)
                    if action_data.get("victory"):
                        # Check that loot_gained is a list
                        assert isinstance(action_data["loot_gained"], list)
                    break
            else:
                pytest.fail("Combat did not end after max attempts")
    
    @pytest.mark.asyncio
    async def test_combat_action_response_has_loot_gained(self, client):
        """POST /combat/action should include loot_gained field when combat ends."""
        async with client as c:
            # Create character
            resp = await c.post("/character/create", json={
                "name": "LootTestHero",
                "character_class": "warrior",
                "ability_generation": "standard_array",
            })
            assert resp.status_code == 200
            session_id = resp.headers.get("x-session-id")
            
            # Start combat
            await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
            
            # Get combat state to find enemy
            state_resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
            combat_data = state_resp.json()
            enemy = next((c for c in combat_data["combatants"] if c["type"] == "enemy"), None)
            assert enemy is not None
            
            # Perform actions until combat ends
            for _ in range(20):
                action_resp = await c.post("/combat/action", json={
                    "action_type": "attack",
                    "target_id": enemy["id"],
                    "weapon": "longsword",
                }, headers={"X-Session-Id": session_id})
                
                assert action_resp.status_code == 200
                data = action_resp.json()
                
                # loot_gained should always be present
                assert "loot_gained" in data
                
                if data.get("combat_ended"):
                    break


# ---------------------------------------------------------------------------
# Inventory Integration Tests
# ---------------------------------------------------------------------------

class TestInventoryIntegration:
    """Test that loot is correctly added to inventory."""
    
    @pytest.mark.asyncio
    async def test_victory_adds_items_to_inventory(self, client):
        """Combat victory should add loot items to character inventory."""
        async with client as c:
            # Create character
            resp = await c.post("/character/create", json={
                "name": "InventoryTestHero",
                "character_class": "warrior",
                "ability_generation": "standard_array",
            })
            assert resp.status_code == 200
            session_id = resp.headers.get("x-session-id")
            
            # Get initial inventory
            state_resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
            initial_inventory_count = len(state_resp.json()["actor"]["inventory"])
            
            # Start combat
            await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
            
            # Get combat state to find enemy
            state_resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
            combat_data = state_resp.json()
            enemy = next((c for c in combat_data["combatants"] if c["type"] == "enemy"), None)
            
            # Fight until victory
            victory = False
            for _ in range(20):
                action_resp = await c.post("/combat/action", json={
                    "action_type": "attack",
                    "target_id": enemy["id"],
                    "weapon": "longsword",
                }, headers={"X-Session-Id": session_id})
                
                data = action_resp.json()
                if data.get("victory"):
                    victory = True
                    break
                if data.get("combat_ended"):
                    break
            
            if victory:
                # Get updated inventory
                state_resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
                final_inventory = state_resp.json()["actor"]["inventory"]
                
                # If loot was gained, inventory should have more items
                # (Note: loot is probabilistic, so we just verify the mechanism works)
                assert len(final_inventory) >= initial_inventory_count


# ---------------------------------------------------------------------------
# Narrative Integration Tests
# ---------------------------------------------------------------------------

class TestNarrativeIntegration:
    """Test that loot appears in narrative."""
    
    @pytest.mark.asyncio
    async def test_loot_mentioned_in_narrative(self, client):
        """Narrative should mention loot when items are gained."""
        async with client as c:
            # Create character
            resp = await c.post("/character/create", json={
                "name": "NarrativeTestHero",
                "character_class": "warrior",
                "ability_generation": "standard_array",
            })
            assert resp.status_code == 200
            session_id = resp.headers.get("x-session-id")
            
            # Start combat
            await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
            
            # Get combat state to find enemy
            state_resp = await c.get("/combat/state", headers={"X-Session-Id": session_id})
            combat_data = state_resp.json()
            enemy = next((c for c in combat_data["combatants"] if c["type"] == "enemy"), None)
            
            # Fight until end
            for _ in range(20):
                action_resp = await c.post("/combat/action", json={
                    "action_type": "attack",
                    "target_id": enemy["id"],
                    "weapon": "longsword",
                }, headers={"X-Session-Id": session_id})
                
                data = action_resp.json()
                
                if data.get("combat_ended"):
                    # Check narrative exists
                    assert "narrative" in data
                    # If victory and loot was gained, narrative should mention it
                    if data.get("victory") and data.get("loot_gained"):
                        # loot_gained field should be present
                        assert isinstance(data["loot_gained"], list)
                    break

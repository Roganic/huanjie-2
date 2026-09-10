"""Tests for scene navigation functionality.

This module tests:
- Scene exits data structure
- Scene switching via movement actions
- Movement actions not triggering combat
"""

import pytest
from src.models.state import Scene, SceneExit, AdventurePhase
from src.scenes.data import (
    VILLAGE_SQUARE_SCENE,
    TAVERN_SCENE,
    DUNGEON_ENTRANCE_SCENE,
    get_scene_by_id,
)


class TestSceneExitStructure:
    """Test that scenes have proper exit structures."""

    def test_scene_exit_model(self):
        """Test SceneExit model has required fields."""
        exit_data = SceneExit(direction="north", target_scene_id="tavern-01")
        assert exit_data.direction == "north"
        assert exit_data.target_scene_id == "tavern-01"

    def test_scene_with_exits(self):
        """Test Scene model can have exits."""
        scene = Scene(
            id="test-scene",
            name="Test Scene",
            description="A test scene.",
            exits=[
                SceneExit(direction="north", target_scene_id="scene-2"),
                SceneExit(direction="south", target_scene_id="scene-3"),
            ],
        )
        assert len(scene.exits) == 2
        assert scene.exits[0].direction == "north"
        assert scene.exits[0].target_scene_id == "scene-2"

    def test_scene_without_exits(self):
        """Test Scene model works without exits (backward compatibility)."""
        scene = Scene(
            id="test-scene",
            name="Test Scene",
            description="A test scene.",
        )
        assert scene.exits == []


class TestVillageSquareScene:
    """Test Village Square scene exits."""

    def test_village_square_has_exits(self):
        """Village square should have exits to tavern and dungeon entrance."""
        assert len(VILLAGE_SQUARE_SCENE.exits) == 3
        
        exit_directions = [e.direction for e in VILLAGE_SQUARE_SCENE.exits]
        assert "north" in exit_directions
        assert "south" in exit_directions

    def test_village_square_exit_targets(self):
        """Village square exits should point to correct scenes."""
        exits_by_direction = {e.direction: e.target_scene_id for e in VILLAGE_SQUARE_SCENE.exits}
        assert exits_by_direction["north"] == "tavern-01"
        assert exits_by_direction["east"] == "dungeon-entrance-01"


class TestTavernScene:
    """Test Tavern scene exits."""

    def test_tavern_has_exits(self):
        """Tavern should have exits to village square and dungeon entrance."""
        assert len(TAVERN_SCENE.exits) == 2
        
        exit_directions = [e.direction for e in TAVERN_SCENE.exits]
        assert "south" in exit_directions
        assert "east" in exit_directions

    def test_tavern_exit_targets(self):
        """Tavern exits should point to correct scenes."""
        exits_by_direction = {e.direction: e.target_scene_id for e in TAVERN_SCENE.exits}
        assert exits_by_direction["south"] == "village-square-01"
        assert exits_by_direction["east"] == "dungeon-entrance-01"


class TestDungeonEntranceScene:
    """Test Dungeon Entrance scene exits."""

    def test_dungeon_entrance_has_exits(self):
        """Dungeon entrance should have exits to tavern, village square and dungeon."""
        assert len(DUNGEON_ENTRANCE_SCENE.exits) == 4
        
        exit_directions = [e.direction for e in DUNGEON_ENTRANCE_SCENE.exits]
        assert "west" in exit_directions
        assert "down" in exit_directions
        assert "north" in exit_directions


class TestSceneRegistry:
    """Test scene registry lookups."""

    def test_get_scene_by_id_exists(self):
        """Should be able to retrieve scenes by ID."""
        scene = get_scene_by_id("village-square-01")
        assert scene is not None
        assert scene.id == "village-square-01"
        assert len(scene.exits) > 0

    def test_get_scene_by_id_not_found(self):
        """Should return None for non-existent scene."""
        scene = get_scene_by_id("non-existent-scene")
        assert scene is None




class TestSceneSwitching:
    """Test scene switching functionality."""

    def test_switch_scene_updates_state(self):
        """switch_scene should update session scene with exits."""
        from src.state import switch_scene, create_session, get_scene
        
        # Create a fresh session
        bootstrap = create_session()
        session_id = bootstrap.session_id
        
        # Switch to village square
        from src.state import create_character
        from src.models.state import CharacterCreateRequest
        create_character(CharacterCreateRequest(name="导航", character_class="warrior"), session_id)
        success = switch_scene("village-square-01", session_id)
        assert success is True
        
        # Verify scene was updated with exits
        scene = get_scene(session_id)
        assert scene.id == "village-square-01"
        assert len(scene.exits) == 3
        assert all(isinstance(e, SceneExit) for e in scene.exits)

    def test_switch_scene_not_found(self):
        """switch_scene should return False for non-existent scene."""
        from src.state import switch_scene
        
        success = switch_scene("non-existent-scene")
        assert success is False


class TestMovementDoesNotTriggerCombat:
    """Combat comes from real scene enemies or explicit attacks, not place-name keywords."""

    @pytest.mark.asyncio
    async def test_movement_to_peaceful_scene_remains_peaceful(self, client):
        from tests.conftest import create_session_and_character
        sid = await create_session_and_character(client)
        h = {"X-Session-Id": sid}
        r = await client.post("/map/move", headers=h, json={"target_scene_id": "dungeon-entrance-01"})
        assert r.status_code == 200 and r.json()["combat"] is None
        assert (await client.get("/state", headers=h)).json()["game_phase"] == "exploration"

    @pytest.mark.asyncio
    async def test_explicit_peaceful_npc_attack_is_disabled(self, client):
        from tests.conftest import create_session_and_character
        sid = await create_session_and_character(client)
        h = {"X-Session-Id": sid}
        r = await client.post("/action", headers=h, json=dict(scene_id="ignored", actor="ignored", intent="攻击老马库斯", approach=""))
        assert r.status_code == 409
        assert "暂不支持攻击" in r.json()["detail"]
        assert (await client.get("/state", headers=h)).json()["game_phase"] == "exploration"


class TestThreeConnectedScenes:
    """Test that at least 3 scenes are connected."""

    def test_minimum_three_scenes(self):
        """Verify at least 3 scenes exist with connections."""
        from src.scenes.data import SCENE_REGISTRY
        
        assert len(SCENE_REGISTRY) >= 3, "Should have at least 3 scenes"

    def test_scenes_are_interconnected(self):
        """Verify scenes have bidirectional connections."""
        # Village square <-> Tavern
        village_exits = {e.target_scene_id for e in VILLAGE_SQUARE_SCENE.exits}
        tavern_exits = {e.target_scene_id for e in TAVERN_SCENE.exits}
        
        assert "tavern-01" in village_exits
        assert "village-square-01" in tavern_exits
        
        # Both connect to dungeon entrance
        assert "dungeon-entrance-01" in village_exits
        assert "dungeon-entrance-01" in tavern_exits

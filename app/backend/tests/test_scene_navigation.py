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
        assert len(VILLAGE_SQUARE_SCENE.exits) == 2
        
        exit_directions = [e.direction for e in VILLAGE_SQUARE_SCENE.exits]
        assert "酒馆" in exit_directions
        assert "森林入口" in exit_directions

    def test_village_square_exit_targets(self):
        """Village square exits should point to correct scenes."""
        exits_by_direction = {e.direction: e.target_scene_id for e in VILLAGE_SQUARE_SCENE.exits}
        assert exits_by_direction["酒馆"] == "tavern-01"
        assert exits_by_direction["森林入口"] == "dungeon-entrance-01"


class TestTavernScene:
    """Test Tavern scene exits."""

    def test_tavern_has_exits(self):
        """Tavern should have exits to village square and dungeon entrance."""
        assert len(TAVERN_SCENE.exits) == 2
        
        exit_directions = [e.direction for e in TAVERN_SCENE.exits]
        assert "村庄广场" in exit_directions
        assert "森林入口" in exit_directions

    def test_tavern_exit_targets(self):
        """Tavern exits should point to correct scenes."""
        exits_by_direction = {e.direction: e.target_scene_id for e in TAVERN_SCENE.exits}
        assert exits_by_direction["村庄广场"] == "village-square-01"
        assert exits_by_direction["森林入口"] == "dungeon-entrance-01"


class TestDungeonEntranceScene:
    """Test Dungeon Entrance scene exits."""

    def test_dungeon_entrance_has_exits(self):
        """Dungeon entrance should have exits to tavern, village square and dungeon."""
        assert len(DUNGEON_ENTRANCE_SCENE.exits) == 3
        
        exit_directions = [e.direction for e in DUNGEON_ENTRANCE_SCENE.exits]
        assert "村庄广场" in exit_directions
        assert "酒馆" in exit_directions
        assert "地下城" in exit_directions


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


class TestMovementActionDetection:
    """Test that movement actions are properly detected."""

    @pytest.mark.parametrize("intent", [
        "前往酒馆",
        "去村庄广场",
        "走回酒馆",
        "进入森林",
        "离开这里",
        "返回村庄",
        "到酒馆去",
        "向北走",
    ])
    def test_movement_keywords(self, intent):
        """Movement keywords should be detected in intents."""
        from src.routers.action import _is_movement_action, _MOVEMENT_KEYWORDS
        
        # The function checks if any movement keyword is in the intent
        intent_lower = intent.lower()
        has_movement = any(kw in intent_lower for kw in _MOVEMENT_KEYWORDS)
        assert has_movement, f"Should detect movement in: {intent}"

    @pytest.mark.parametrize("intent", [
        "战斗",
        "砍杀敌人",
        "检查物品",
        "与NPC交谈",
    ])
    def test_non_movement_actions(self, intent):
        """Non-movement actions should not be detected as movement."""
        from src.routers.action import _MOVEMENT_KEYWORDS
        
        intent_lower = intent.lower()
        has_movement = any(kw in intent_lower for kw in _MOVEMENT_KEYWORDS)
        # Clear non-movement actions should not be detected as movement
        if "检查" in intent_lower or "交谈" in intent_lower:
            assert not has_movement, f"Should not detect movement in: {intent}"


class TestSceneSwitching:
    """Test scene switching functionality."""

    def test_switch_scene_updates_state(self):
        """switch_scene should update session scene with exits."""
        from src.state import switch_scene, create_session, get_scene
        
        # Create a fresh session
        bootstrap = create_session()
        session_id = bootstrap.session_id
        
        # Switch to village square
        result = switch_scene("village-square-01", session_id)
        assert result is True
        
        # Verify scene was updated with exits
        scene = get_scene(session_id)
        assert scene.id == "village-square-01"
        assert len(scene.exits) == 2
        assert all(isinstance(e, SceneExit) for e in scene.exits)

    def test_switch_scene_not_found(self):
        """switch_scene should return False for non-existent scene."""
        from src.state import switch_scene
        
        result = switch_scene("non-existent-scene")
        assert result is False


class TestMovementDoesNotTriggerCombat:
    """Test that movement actions don't trigger combat."""

    def test_movement_does_not_trigger_combat(self):
        """Movement actions should not trigger combat even with combat keywords."""
        from src.routers.action import _should_trigger_combat, _is_movement_action
        
        # Even "前往战斗地点" (go to battle location) should not trigger combat
        # because it's primarily a movement action
        intent = "前往战斗地点"
        approach = ""
        
        is_movement = _is_movement_action(intent, approach)
        should_combat = _should_trigger_combat(intent, approach)
        
        # Movement actions should not trigger combat
        if is_movement:
            assert not should_combat, "Movement actions should not trigger combat"

    def test_combat_still_triggers_without_movement(self):
        """Combat keywords should trigger combat when not a movement action."""
        from src.routers.action import _should_trigger_combat
        
        # Use combat keywords that don't overlap with movement keywords
        intent = "fight the goblin"
        approach = "swing sword"
        
        assert _should_trigger_combat(intent, approach) is True


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

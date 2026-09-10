"""Unit tests for the save/load system.

These tests validate the acceptance criteria:
1. POST /save creates a JSON file with character, scene, inventory, map_state fields
2. GET /saves returns list with id, timestamp, character_name, level, current_scene
3. POST /load/{save_id} restores character HP, level, inventory
4. POST /load/{save_id} restores explored_nodes (map state)
5. POST /save during combat returns 400 with "战斗中无法存档"

These cover the legacy standalone save-file adapter. Live API snapshot coverage
is in test_module_system_acceptance.py and test_world_encounters.py.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# NPC imports now use the canonical package directly.
from src.models.state import (  # noqa: E402
    AbilityScores,
    Actor,
    AdventurePhase,
    CharacterClass,
    EquippedItems,
    GamePhase,
    InventoryItem,
    ItemType,
    NarrativeHistoryEntry,
    Scene,
    SceneHistoryEntry,
)
from src.save_load.manager import (  # noqa: E402
    CombatSaveError,
    SaveLoadError,
    load_game_state,
    list_save_files,
    save_game_state,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_save_dir(tmp_path):
    """Patch SAVE_DIR to a temporary directory for isolation."""
    import src.save_load.manager as mgr
    original = mgr.SAVE_DIR
    mgr.SAVE_DIR = tmp_path
    yield tmp_path
    mgr.SAVE_DIR = original


def _make_actor(hp: int = 20, level: int = 1) -> Actor:
    abilities = AbilityScores(str_=15, dex=13, con=14, int_=8, wis=12, cha=10)
    sword = InventoryItem(id="longsword", name="长剑", type=ItemType.WEAPON, damage_dice="1d8")
    potion = InventoryItem(id="healing_potion", name="治疗药水", type=ItemType.CONSUMABLE)
    return Actor(
        id="warrior-aldric",
        name="Aldric",
        character_class=CharacterClass.WARRIOR,
        abilities=abilities,
        proficiency_bonus=2,
        level=level,
        experience_points=0,
        hp=hp,
        hp_max=hp,
        ac=16,
        description="A brave warrior.",
        inventory=[sword, potion],
        equipped=EquippedItems(weapon=sword),
    )


def _make_scene(scene_id: str = "tavern-01", name: str = "酒馆") -> Scene:
    return Scene(id=scene_id, name=name, description="A dimly lit tavern.", actors=[])


# ---------------------------------------------------------------------------
# Test 1: save creates JSON file with required fields
# ---------------------------------------------------------------------------

def test_save_creates_json_file_with_required_fields(tmp_save_dir):
    actor = _make_actor()
    scene = _make_scene()

    result = save_game_state(
        session_id="test-session",
        game_phase=AdventurePhase.EXPLORATION,
        phase=GamePhase.ADVENTURE,
        character=actor,
        scene=scene,
        explored_nodes=["tavern-01", "village-square-01"],
        narrative_history=[],
        scene_history=[],
    )

    assert result["success"] is True
    save_id = result["save_id"]

    # Verify file exists in saves dir
    save_file = tmp_save_dir / f"{save_id}.json"
    assert save_file.exists(), f"Save file not found: {save_file}"

    data = json.loads(save_file.read_text(encoding="utf-8"))

    # Required top-level fields per acceptance criteria
    assert "character" in data, "Missing 'character' field"
    assert "scene" in data, "Missing 'scene' field"
    assert "inventory" in data, "Missing 'inventory' field"
    assert "map_state" in data, "Missing 'map_state' field"

    # Character fields
    assert data["character"]["name"] == "Aldric"
    assert data["character"]["hp"] == 20
    assert data["character"]["level"] == 1

    # Scene fields
    assert data["scene"]["id"] == "tavern-01"

    # Inventory is a list
    assert isinstance(data["inventory"], list)
    assert len(data["inventory"]) == 2

    # Map state contains explored_nodes
    assert "explored_nodes" in data["map_state"]
    assert "tavern-01" in data["map_state"]["explored_nodes"]
    assert "village-square-01" in data["map_state"]["explored_nodes"]


# ---------------------------------------------------------------------------
# Test 2: GET /saves returns correct fields
# ---------------------------------------------------------------------------

def test_list_saves_returns_required_fields(tmp_save_dir):
    actor = _make_actor(hp=15, level=2)
    scene = _make_scene("village-square-01", "村庄广场")

    save_game_state(
        session_id="test-session",
        game_phase=AdventurePhase.EXPLORATION,
        phase=GamePhase.ADVENTURE,
        character=actor,
        scene=scene,
        explored_nodes=["village-square-01"],
        narrative_history=[],
        scene_history=[],
    )

    saves = list_save_files()
    assert len(saves) == 1

    entry = saves[0]
    assert "id" in entry, "Missing 'id' field"
    assert "timestamp" in entry, "Missing 'timestamp' field"
    assert "character_name" in entry, "Missing 'character_name' field"
    assert "level" in entry, "Missing 'level' field"
    assert "current_scene" in entry, "Missing 'current_scene' field"

    assert entry["character_name"] == "Aldric"
    assert entry["level"] == 2
    assert entry["current_scene"] == "村庄广场"


# ---------------------------------------------------------------------------
# Test 3: load restores character HP, level, inventory
# ---------------------------------------------------------------------------

def test_load_restores_character_state(tmp_save_dir):
    actor = _make_actor(hp=13, level=3)
    scene = _make_scene()

    result = save_game_state(
        session_id="test-session",
        game_phase=AdventurePhase.EXPLORATION,
        phase=GamePhase.ADVENTURE,
        character=actor,
        scene=scene,
        explored_nodes=["tavern-01"],
        narrative_history=[],
        scene_history=[],
    )
    save_id = result["save_id"]

    # Load it back
    data = load_game_state(save_id)

    restored_char = data["character"]
    assert restored_char["hp"] == 13, f"HP mismatch: {restored_char['hp']} != 13"
    assert restored_char["level"] == 3, f"Level mismatch: {restored_char['level']} != 3"

    restored_inventory = data["inventory"]
    assert len(restored_inventory) == 2
    inv_ids = [item["id"] for item in restored_inventory]
    assert "longsword" in inv_ids
    assert "healing_potion" in inv_ids


# ---------------------------------------------------------------------------
# Test 4: load restores explored_nodes (map state)
# ---------------------------------------------------------------------------

def test_load_restores_map_state(tmp_save_dir):
    actor = _make_actor()
    scene = _make_scene("dungeon-entrance-01", "地牢入口")
    explored = ["tavern-01", "village-square-01", "dungeon-entrance-01"]

    result = save_game_state(
        session_id="test-session",
        game_phase=AdventurePhase.EXPLORATION,
        phase=GamePhase.ADVENTURE,
        character=actor,
        scene=scene,
        explored_nodes=explored,
        narrative_history=[],
        scene_history=[],
    )
    save_id = result["save_id"]

    data = load_game_state(save_id)

    restored_nodes = data["map_state"]["explored_nodes"]
    assert set(restored_nodes) == set(explored), (
        f"explored_nodes mismatch: {restored_nodes} != {explored}"
    )


# ---------------------------------------------------------------------------
# Test 5: save during combat raises CombatSaveError (maps to HTTP 400)
# ---------------------------------------------------------------------------

def test_save_during_combat_raises_error(tmp_save_dir):
    actor = _make_actor()
    scene = _make_scene()

    with pytest.raises(CombatSaveError) as exc_info:
        save_game_state(
            session_id="test-session",
            game_phase=AdventurePhase.COMBAT,
            phase=GamePhase.ADVENTURE,
            character=actor,
            scene=scene,
            explored_nodes=[],
            narrative_history=[],
            scene_history=[],
        )

    assert "战斗中无法存档" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 6: max save slots – oldest is overwritten
# ---------------------------------------------------------------------------

def test_max_save_slots_overwrites_oldest(tmp_save_dir):
    from src.save_load.manager import MAX_SAVE_SLOTS
    actor = _make_actor()
    scene = _make_scene()

    # Create MAX_SAVE_SLOTS + 1 saves
    for i in range(MAX_SAVE_SLOTS + 1):
        save_game_state(
            session_id="test-session",
            game_phase=AdventurePhase.EXPLORATION,
            phase=GamePhase.ADVENTURE,
            character=actor,
            scene=scene,
            explored_nodes=[],
            narrative_history=[],
            scene_history=[],
        )

    # Should have at most MAX_SAVE_SLOTS files
    files = list(tmp_save_dir.glob("*.json"))
    assert len(files) <= MAX_SAVE_SLOTS, (
        f"Expected at most {MAX_SAVE_SLOTS} save files, got {len(files)}"
    )


# ---------------------------------------------------------------------------
# Test 7: load non-existent save raises SaveLoadError
# ---------------------------------------------------------------------------

def test_load_nonexistent_save_raises_error(tmp_save_dir):
    with pytest.raises(SaveLoadError):
        load_game_state("save_nonexistent_abc123")

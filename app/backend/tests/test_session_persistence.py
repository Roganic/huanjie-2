"""Tests for game session persistence functionality.

This module tests:
- State serialization to JSON file
- State deserialization from JSON file
- Reset flow that clears persistence file
"""

import json
import pytest
from httpx import ASGITransport, AsyncClient
from pathlib import Path

from src.main import app
from src.persistence import get_save_file_path, clear_save, has_save_file, SaveData
from src import game_state


@pytest.fixture(autouse=True)
def _clean_save_file():
    """Clean up save file before each test."""
    clear_save()
    yield
    clear_save()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Persistence File Tests
# ---------------------------------------------------------------------------


def test_save_file_path_exists():
    """Test that save file path is properly configured."""
    path = get_save_file_path()
    assert path is not None
    assert path.parent.exists()


def test_has_save_file_returns_false_when_no_save():
    """Test has_save_file returns False when no save exists."""
    clear_save()
    assert has_save_file() is False


def test_clear_save_returns_false_when_no_file():
    """Test clear_save returns False when no save file exists."""
    clear_save()
    result = clear_save()
    assert result is False


# ---------------------------------------------------------------------------
# State Serialization Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_character_creation_creates_save_file(client):
    """Test that creating a character creates a save file."""
    clear_save()
    assert has_save_file() is False
    
    async with client as c:
        # Create a character
        resp = await c.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        
        # Save file should be created
        assert has_save_file() is True
        
        # Verify save file content by loading directly from persistence
        from src.persistence import load_game
        save_data = load_game()
        assert save_data is not None
        assert save_data.character is not None
        assert save_data.character.name == "TestHero"


@pytest.mark.asyncio
async def test_action_updates_save_file(client):
    """Test that executing an action updates the save file."""
    from src.persistence import load_game
    
    async with client as c:
        # Create a character first
        resp = await c.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        
        # Get initial history length from save
        initial_save = load_game()
        initial_history_len = len(initial_save.action_history) if initial_save else 0
        
        # Execute an action
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "TestHero",
            "intent": "look around",
            "approach": "examine the surroundings",
        })
        assert resp.status_code == 200
        
        # Save file should be updated with new history
        updated_save = load_game()
        assert updated_save is not None
        assert len(updated_save.action_history) > initial_history_len


# ---------------------------------------------------------------------------
# State Deserialization / Recovery Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_recovery_after_restart(client):
    """Test that state can be recovered from save file after restart."""
    from src.persistence import load_game
    
    session_id = None
    
    async with client as c:
        # Create a character
        resp = await c.post("/character/create", json={
            "name": "PersistentHero",
            "character_class": "mage",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        session_id = resp.headers.get("X-Session-Id")
        
        # Execute an action
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "PersistentHero",
            "intent": "cast a spell",
            "approach": "use arcane magic",
        }, headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        
        # Get state before "restart"
        resp = await c.get("/state", headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        before_data = resp.json()
        assert before_data["actor"]["name"] == "PersistentHero"
        assert before_data["actor"]["character_class"] == "mage"
        assert len(before_data["narrative_history"]) > 0
    
    # Simulate restart by loading saved game from persistence file
    loaded_save = load_game()
    assert loaded_save is not None
    assert loaded_save.character is not None
    assert loaded_save.character.name == "PersistentHero"
    assert loaded_save.character.character_class.value == "mage"
    assert len(loaded_save.action_history) > 0


@pytest.mark.asyncio
async def test_auto_load_on_startup():
    """Test that saved game is auto-loaded on startup."""
    # First create a save file directly
    from src.state import create_character, get_bootstrap_state, set_current_session, reset_current_session
    from src.models.state import CharacterCreateRequest
    
    clear_save()
    
    # Create character and save
    token = set_current_session("test-auto-load")
    try:
        create_character(
            CharacterCreateRequest(name="AutoLoadHero", character_class="rogue"),
            session_id="test-auto-load",
        )
        game_state.save_current_game(session_id="test-auto-load")
    finally:
        reset_current_session(token)
    
    # Verify save exists
    assert has_save_file() is True
    
    # Test auto-load
    loaded = game_state.try_auto_load_on_startup()
    assert loaded is not None
    assert loaded.actor is not None
    assert loaded.actor.name == "AutoLoadHero"


# ---------------------------------------------------------------------------
# Reset Flow Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_reset_clears_save_file(client):
    """Test that POST /session/reset clears the save file."""
    async with client as c:
        # Create a character
        resp = await c.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        session_id = resp.headers.get("X-Session-Id")
        
        # Verify save file exists
        assert has_save_file() is True
        
        # Call session/reset
        resp = await c.post("/session/reset", headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        
        # Save file should be cleared
        assert has_save_file() is False
        
        # State should be in character_creation phase
        data = resp.json()
        assert data["phase"] == "character_creation"


@pytest.mark.asyncio
async def test_session_reset_returns_initial_state(client):
    """Test that POST /session/reset returns initial character creation state."""
    async with client as c:
        # Create a character first
        resp = await c.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        session_id = resp.headers.get("X-Session-Id")
        
        # Reset session
        resp = await c.post("/session/reset", headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Should be in character creation phase
        assert data["phase"] == "character_creation"
        assert data["game_phase"] == "exploration"
        
        # Should have no actor
        assert data["actor"] is None
        
        # Should have initial scene
        assert data["scene"] is not None
        assert data["scene"]["id"] == "character-creation-01"


@pytest.mark.asyncio
async def test_reset_endpoint_behavior(client):
    """Test that the /reset endpoint maintains backward compatibility."""
    async with client as c:
        # Create a character
        resp = await c.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        session_id = resp.headers.get("X-Session-Id")
        
        # Call /reset (not /session/reset)
        resp = await c.post("/reset", headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        
        # /reset may or may not clear save file depending on implementation
        # but should return valid state
        data = resp.json()
        assert "phase" in data
        assert "scene" in data


# ---------------------------------------------------------------------------
# Save Data Structure Tests
# ---------------------------------------------------------------------------


def test_save_data_model_validation():
    """Test that SaveData model validates correctly."""
    from src.models.state import Actor, AbilityScores, Scene, GamePhase, AdventurePhase
    
    # Create minimal valid save data
    save_data = SaveData(
        version=1,
        session_id="test-session",
        phase=GamePhase.CHARACTER_CREATION,
        game_phase=AdventurePhase.EXPLORATION,
    )
    
    assert save_data.version == 1
    assert save_data.session_id == "test-session"
    assert save_data.character is None


def test_save_data_with_character():
    """Test SaveData with character data."""
    from src.models.state import Actor, AbilityScores, Scene, GamePhase, AdventurePhase, CharacterClass
    
    actor = Actor(
        id="test-actor",
        name="Test Actor",
        character_class=CharacterClass.WARRIOR,
        abilities=AbilityScores(str=15, dex=12, con=14, int=10, wis=12, cha=8),
        proficiency_bonus=2,
        hp=12,
        hp_max=12,
        ac=16,
        description="A test character",
    )
    
    save_data = SaveData(
        version=1,
        session_id="test-session",
        phase=GamePhase.ADVENTURE,
        game_phase=AdventurePhase.EXPLORATION,
        character=actor,
    )
    
    assert save_data.character is not None
    assert save_data.character.name == "Test Actor"


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_persistence_flow(client):
    """Test the complete persistence flow: create, act, reset."""
    from src.persistence import load_game
    
    async with client as c:
        # 1. Create character
        resp = await c.post("/character/create", json={
            "name": "FlowTestHero",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert resp.status_code == 200
        session_id = resp.headers.get("X-Session-Id")
        
        # 2. Verify save exists with correct data
        assert has_save_file() is True
        save = load_game()
        assert save.character.name == "FlowTestHero"
        
        # 3. Execute multiple actions
        for i in range(3):
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "FlowTestHero",
                "intent": f"action {i}",
                "approach": f"approach {i}",
            }, headers={"X-Session-Id": session_id} if session_id else {})
            assert resp.status_code == 200
        
        # 4. Verify history is persisted
        save = load_game()
        assert len(save.action_history) >= 3
        
        # 5. Reset session
        resp = await c.post("/session/reset", headers={"X-Session-Id": session_id} if session_id else {})
        assert resp.status_code == 200
        
        # 6. Verify save is cleared and state is reset
        assert has_save_file() is False
        data = resp.json()
        assert data["phase"] == "character_creation"
        assert data["actor"] is None

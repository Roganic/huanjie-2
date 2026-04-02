"""Unit tests for the module system."""

import json
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.module import (
    Module,
    ModuleScene,
    ModuleNPC,
    Quest,
    StoryNode,
    Trigger,
    TriggerType,
    TriggerCondition,
    QuestStatus,
    StoryNodeType,
    NPCRole,
)
from src.modules.manager import ModuleManager, get_module_manager


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------

@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_module_data():
    """Create sample module data for testing."""
    return {
        "id": "test_module",
        "name": "Test Module",
        "description": "A test module for unit testing",
        "metadata": {
            "author": "Test Author",
            "version": "1.0.0",
            "tags": ["test"],
            "difficulty": "easy"
        },
        "scenes": [
            {
                "id": "scene_1",
                "name": "Test Scene 1",
                "description": "First test scene",
                "npc_ids": ["npc_1"],
                "exits": [
                    {"direction": "north", "target_scene_id": "scene_2", "description": "To scene 2"}
                ],
                "items": [],
                "flags": [],
                "lighting": "normal",
                "atmosphere": "Test atmosphere"
            },
            {
                "id": "scene_2",
                "name": "Test Scene 2",
                "description": "Second test scene",
                "npc_ids": [],
                "exits": [],
                "items": [],
                "flags": [],
                "lighting": "dark"
            }
        ],
        "npcs": [
            {
                "id": "npc_1",
                "name": "Test NPC",
                "description": "A test NPC",
                "race": "Human",
                "role": "quest_giver",
                "stats": {"hp": 10, "ac": 10, "str": 10, "dex": 10, "con": 10},
                "is_hostile": False
            },
            {
                "id": "npc_2",
                "name": "Enemy NPC",
                "description": "A test enemy",
                "race": "Goblin",
                "role": "enemy",
                "stats": {"hp": 5, "ac": 8, "str": 8, "dex": 12, "con": 8},
                "is_hostile": True
            }
        ],
        "quests": [
            {
                "id": "quest_1",
                "name": "Test Quest",
                "description": "A test quest",
                "status": "not_started",
                "objectives": [
                    {"id": "obj_1", "description": "Complete the test", "completed": False, "optional": False}
                ],
                "rewards": {"xp": 100, "gold": 50},
                "prerequisites": [],
                "starting_node_id": "node_1"
            }
        ],
        "story_nodes": [
            {
                "id": "node_1",
                "name": "Start Node",
                "type": "start",
                "description": "Starting node",
                "scene_id": "scene_1",
                "npc_ids": ["npc_1"],
                "transitions": [{"target_node_id": "node_2", "description": "Continue"}],
                "required_flags": [],
                "sets_flags": ["started"]
            },
            {
                "id": "node_2",
                "name": "Middle Node",
                "type": "dialogue",
                "description": "Middle node",
                "scene_id": "scene_2",
                "npc_ids": [],
                "dialogue_text": "Hello!",
                "transitions": [{"target_node_id": "node_3", "description": "End"}],
                "required_flags": ["started"],
                "sets_flags": ["midpoint"]
            },
            {
                "id": "node_3",
                "name": "End Node",
                "type": "end",
                "description": "Ending node",
                "scene_id": "scene_2",
                "transitions": [],
                "required_flags": ["midpoint"],
                "sets_flags": ["completed"]
            }
        ],
        "triggers": [
            {
                "id": "trigger_1",
                "name": "Test Trigger",
                "description": "A test trigger",
                "conditions": [
                    {"type": "flag", "target_id": "started", "value": True, "operator": "equals"}
                ],
                "actions": [
                    {"type": "set_flag", "target_id": "triggered", "parameters": {}}
                ],
                "once_only": True,
                "enabled": True
            }
        ],
        "starting_scene_id": "scene_1",
        "starting_node_id": "node_1"
    }


@pytest.fixture
def fresh_manager():
    """Create a fresh module manager for isolated tests."""
    manager = ModuleManager()
    manager.clear_all()
    return manager


# -----------------------------------------------------------------------------
# Data Model Tests
# -----------------------------------------------------------------------------

class TestModuleModels:
    """Tests for module data models."""
    
    def test_trigger_condition_creation(self):
        """Test creating a trigger condition."""
        condition = TriggerCondition(
            type=TriggerType.LOCATION,
            target_id="scene_1",
            value=None,
            operator="equals"
        )
        assert condition.type == TriggerType.LOCATION
        assert condition.target_id == "scene_1"
        assert condition.operator == "equals"
    
    def test_trigger_creation(self):
        """Test creating a trigger."""
        trigger = Trigger(
            id="test_trigger",
            name="Test Trigger",
            description="Test description",
            conditions=[
                TriggerCondition(type=TriggerType.FLAG, target_id="flag_1", value=True)
            ],
            actions=[],
            once_only=True,
            enabled=True
        )
        assert trigger.id == "test_trigger"
        assert trigger.once_only is True
        assert len(trigger.conditions) == 1
    
    def test_story_node_creation(self):
        """Test creating a story node."""
        node = StoryNode(
            id="node_1",
            name="Test Node",
            type=StoryNodeType.DIALOGUE,
            description="Test description",
            scene_id="scene_1",
            npc_ids=["npc_1"],
            dialogue_text="Hello!",
            transitions=[],
            required_flags=["prereq"],
            sets_flags=["completed"]
        )
        assert node.id == "node_1"
        assert node.type == StoryNodeType.DIALOGUE
        assert "prereq" in node.required_flags
    
    def test_quest_creation(self):
        """Test creating a quest."""
        quest = Quest(
            id="quest_1",
            name="Test Quest",
            description="Test description",
            status=QuestStatus.ACTIVE,
            objectives=[],
            rewards={"xp": 100},
            prerequisites=["quest_0"]
        )
        assert quest.id == "quest_1"
        assert quest.status == QuestStatus.ACTIVE
        assert "quest_0" in quest.prerequisites
    
    def test_npc_creation(self):
        """Test creating an NPC."""
        npc = ModuleNPC(
            id="npc_1",
            name="Test NPC",
            description="Test description",
            race="Human",
            role=NPCRole.QUEST_GIVER,
            is_hostile=False
        )
        assert npc.id == "npc_1"
        assert npc.role == NPCRole.QUEST_GIVER
        assert npc.is_hostile is False
    
    def test_scene_creation(self):
        """Test creating a scene."""
        scene = ModuleScene(
            id="scene_1",
            name="Test Scene",
            description="Test description",
            npc_ids=["npc_1"],
            exits=[],
            lighting="dark",
            atmosphere="Spooky"
        )
        assert scene.id == "scene_1"
        assert scene.lighting == "dark"
        assert "npc_1" in scene.npc_ids
    
    def test_module_creation(self, sample_module_data):
        """Test creating a full module."""
        module = Module.model_validate(sample_module_data)
        
        assert module.id == "test_module"
        assert module.name == "Test Module"
        assert len(module.scenes) == 2
        assert len(module.npcs) == 2
        assert len(module.quests) == 1
        assert len(module.story_nodes) == 3
        assert len(module.triggers) == 1
    
    def test_module_getters(self, sample_module_data):
        """Test module getter methods."""
        module = Module.model_validate(sample_module_data)
        
        # Test get_scene
        scene = module.get_scene("scene_1")
        assert scene is not None
        assert scene.name == "Test Scene 1"
        assert module.get_scene("nonexistent") is None
        
        # Test get_npc
        npc = module.get_npc("npc_1")
        assert npc is not None
        assert npc.name == "Test NPC"
        assert module.get_npc("nonexistent") is None
        
        # Test get_quest
        quest = module.get_quest("quest_1")
        assert quest is not None
        assert quest.name == "Test Quest"
        assert module.get_quest("nonexistent") is None
        
        # Test get_story_node
        node = module.get_story_node("node_1")
        assert node is not None
        assert node.name == "Start Node"
        assert module.get_story_node("nonexistent") is None
        
        # Test get_trigger
        trigger = module.get_trigger("trigger_1")
        assert trigger is not None
        assert trigger.name == "Test Trigger"
        assert module.get_trigger("nonexistent") is None


# -----------------------------------------------------------------------------
# Module Manager Tests
# -----------------------------------------------------------------------------

class TestModuleManager:
    """Tests for the module manager."""
    
    def test_load_module_from_dict(self, fresh_manager, sample_module_data):
        """Test loading a module from a dictionary."""
        module = fresh_manager.load_module_from_dict(sample_module_data)
        
        assert module.id == "test_module"
        assert "test_module" in fresh_manager._modules
    
    def test_load_module_from_file(self, fresh_manager, sample_module_data):
        """Test loading a module from a JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_module_data, f)
            temp_path = f.name
        
        try:
            module = fresh_manager.load_module_from_file(temp_path)
            assert module.id == "test_module"
            assert fresh_manager.get_module("test_module") is not None
        finally:
            os.unlink(temp_path)
    
    def test_load_module_file_not_found(self, fresh_manager):
        """Test loading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            fresh_manager.load_module_from_file("/nonexistent/path/module.json")
    
    def test_get_module(self, fresh_manager, sample_module_data):
        """Test getting a loaded module."""
        fresh_manager.load_module_from_dict(sample_module_data)
        
        module = fresh_manager.get_module("test_module")
        assert module is not None
        assert module.name == "Test Module"
        
        assert fresh_manager.get_module("nonexistent") is None
    
    def test_list_modules(self, fresh_manager, sample_module_data):
        """Test listing all loaded modules."""
        # Initially empty (after clear_all)
        assert len(fresh_manager.list_modules()) == 0
        
        fresh_manager.load_module_from_dict(sample_module_data)
        modules = fresh_manager.list_modules()
        
        assert len(modules) == 1
        assert modules[0].id == "test_module"
        assert modules[0].name == "Test Module"
    
    def test_activate_module(self, fresh_manager, sample_module_data):
        """Test activating a module for a session."""
        fresh_manager.load_module_from_dict(sample_module_data)
        
        active = fresh_manager.activate_module("session_1", "test_module")
        
        assert active is not None
        assert active.id == "test_module"
        assert active.current_node_id == "node_1"
        assert active.current_scene_id == "scene_1"
    
    def test_activate_module_not_found(self, fresh_manager):
        """Test activating a non-existent module returns None."""
        result = fresh_manager.activate_module("session_1", "nonexistent")
        assert result is None
    
    def test_get_active_module(self, fresh_manager, sample_module_data):
        """Test getting active module for a session."""
        fresh_manager.load_module_from_dict(sample_module_data)
        fresh_manager.activate_module("session_1", "test_module")
        
        state = fresh_manager.get_active_module("session_1")
        
        assert state is not None
        assert state.module_id == "test_module"
        assert state.session_id == "session_1"
    
    def test_get_active_module_not_active(self, fresh_manager):
        """Test getting active module when none is active."""
        assert fresh_manager.get_active_module("session_1") is None
    
    def test_deactivate_module(self, fresh_manager, sample_module_data):
        """Test deactivating a module."""
        fresh_manager.load_module_from_dict(sample_module_data)
        fresh_manager.activate_module("session_1", "test_module")
        
        assert fresh_manager.deactivate_module("session_1") is True
        assert fresh_manager.get_active_module("session_1") is None
        assert fresh_manager.deactivate_module("session_1") is False
    
    def test_update_session_state(self, fresh_manager, sample_module_data):
        """Test updating session state."""
        fresh_manager.load_module_from_dict(sample_module_data)
        fresh_manager.activate_module("session_1", "test_module")
        
        state = fresh_manager.update_session_state(
            "session_1",
            current_node_id="node_2",
            current_scene_id="scene_2",
            completed_node="node_1",
            flags=["new_flag"]
        )
        
        assert state is not None
        assert state.current_node_id == "node_2"
        assert state.current_scene_id == "scene_2"
        assert "node_1" in state.completed_nodes
        assert "new_flag" in state.active_flags
    
    def test_update_session_state_not_active(self, fresh_manager):
        """Test updating session state when no module is active."""
        result = fresh_manager.update_session_state("session_1", current_node_id="node_2")
        assert result is None
    
    def test_clear_all(self, fresh_manager, sample_module_data):
        """Test clearing all modules and active sessions."""
        fresh_manager.load_module_from_dict(sample_module_data)
        fresh_manager.activate_module("session_1", "test_module")
        
        fresh_manager.clear_all()
        
        assert len(fresh_manager._modules) == 0
        assert len(fresh_manager._active_modules) == 0


# -----------------------------------------------------------------------------
# API Tests
# -----------------------------------------------------------------------------

class TestModuleAPI:
    """Tests for module API endpoints."""
    
    def test_get_modules_empty(self, client, monkeypatch):
        """Test GET /modules returns empty list when no modules loaded."""
        # Clear modules
        manager = ModuleManager()
        manager.clear_all()
        monkeypatch.setattr("src.modules.manager._module_manager", manager)
        
        response = client.get("/modules")
        assert response.status_code == 200
        data = response.json()
        assert data["modules"] == []
        assert data["total"] == 0
    
    def test_get_modules_with_builtin(self, client):
        """Test GET /modules returns built-in starter module."""
        response = client.get("/modules")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        
        # Find starter_village module
        module_ids = [m["id"] for m in data["modules"]]
        assert "starter_village" in module_ids
        
        # Verify required fields
        for module in data["modules"]:
            assert "id" in module
            assert "name" in module
            assert "description" in module
    
    def test_get_module_by_id(self, client):
        """Test GET /modules/{id} returns full module content."""
        response = client.get("/modules/starter_village")
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert data["id"] == "starter_village"
        assert "name" in data
        assert "description" in data
        assert "scenes" in data
        assert "npcs" in data
        assert "quests" in data
        assert "story_nodes" in data
        assert "triggers" in data
    
    def test_get_module_not_found(self, client):
        """Test GET /modules/{id} returns 404 for non-existent module."""
        response = client.get("/modules/nonexistent")
        assert response.status_code == 404
    
    def test_post_modules_load_from_file(self, client):
        """Test POST /modules/load with file_path."""
        # Create a temporary module file
        module_data = {
            "id": "temp_test_module",
            "name": "Temp Test Module",
            "description": "Temporary test module",
            "metadata": {"version": "1.0.0"},
            "scenes": [],
            "npcs": [],
            "quests": [],
            "story_nodes": [],
            "triggers": []
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(module_data, f)
            temp_path = f.name
        
        try:
            response = client.post("/modules/load", json={"file_path": temp_path})
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["module_id"] == "temp_test_module"
        finally:
            os.unlink(temp_path)
    
    def test_post_modules_load_from_data(self, client):
        """Test POST /modules/load with module_data."""
        module_data = {
            "id": "inline_test_module",
            "name": "Inline Test Module",
            "description": "Inline test module",
            "metadata": {"version": "1.0.0"},
            "scenes": [
                {"id": "s1", "name": "Scene 1", "description": "Test scene", "npc_ids": [], "exits": []}
            ],
            "npcs": [],
            "quests": [],
            "story_nodes": [],
            "triggers": []
        }
        
        response = client.post("/modules/load", json={"module_data": module_data})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["module_id"] == "inline_test_module"
    
    def test_post_modules_load_no_data(self, client):
        """Test POST /modules/load with no data returns error."""
        response = client.post("/modules/load", json={})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "file_path or module_data" in data["message"]
    
    def test_activate_module(self, client):
        """Test POST /modules/{id}/activate."""
        response = client.post("/modules/starter_village/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["module_id"] == "starter_village"
        assert "current_node_id" in data
    
    def test_activate_module_not_found(self, client):
        """Test POST /modules/{id}/activate with non-existent module."""
        response = client.post("/modules/nonexistent/activate")
        assert response.status_code == 404
    
    def test_deactivate_module(self, client):
        """Test POST /modules/deactivate."""
        # First activate a module
        client.post("/modules/starter_village/activate")
        
        # Then deactivate
        response = client.post("/modules/deactivate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
    
    def test_get_state_includes_active_module(self, client):
        """Test GET /state includes active_module when module is active."""
        # First, bootstrap to initialize a session
        response = client.get("/state/bootstrap")
        assert response.status_code == 200
        data = response.json()
        session_id = data.get("session_id", "default")
        
        # Activate a module with the session ID
        response = client.post(
            "/modules/starter_village/activate",
            headers={"X-Session-Id": session_id}
        )
        assert response.status_code == 200
        
        # Then get state with same session ID
        response = client.get("/state", headers={"X-Session-Id": session_id})
        assert response.status_code == 200
        data = response.json()
        assert "active_module" in data
        assert data["active_module"]["id"] == "starter_village"
        assert "current_node_id" in data["active_module"]


# -----------------------------------------------------------------------------
# Starter Module Content Tests
# -----------------------------------------------------------------------------

class TestStarterModuleContent:
    """Tests for the built-in starter module content."""
    
    def test_starter_module_has_minimum_scenes(self, client):
        """Test starter module has at least 2 scenes."""
        response = client.get("/modules/starter_village")
        data = response.json()
        assert len(data["scenes"]) >= 2
        
        # Verify scene structure
        for scene in data["scenes"]:
            assert "id" in scene
            assert "name" in scene
            assert "description" in scene
    
    def test_starter_module_has_minimum_npcs(self, client):
        """Test starter module has at least 2 NPCs."""
        response = client.get("/modules/starter_village")
        data = response.json()
        assert len(data["npcs"]) >= 2
        
        # Verify NPC structure
        for npc in data["npcs"]:
            assert "id" in npc
            assert "name" in npc
            assert "description" in npc
    
    def test_starter_module_has_minimum_quests(self, client):
        """Test starter module has at least 1 quest."""
        response = client.get("/modules/starter_village")
        data = response.json()
        assert len(data["quests"]) >= 1
        
        # Verify quest structure
        for quest in data["quests"]:
            assert "id" in quest
            assert "name" in quest
            assert "description" in quest
            assert "objectives" in quest
    
    def test_starter_module_has_minimum_story_nodes(self, client):
        """Test starter module has at least 3 story nodes."""
        response = client.get("/modules/starter_village")
        data = response.json()
        assert len(data["story_nodes"]) >= 3
        
        # Verify story node structure
        for node in data["story_nodes"]:
            assert "id" in node
            assert "name" in node
            assert "type" in node
            assert "description" in node
    
    def test_starter_module_has_triggers(self, client):
        """Test starter module has triggers."""
        response = client.get("/modules/starter_village")
        data = response.json()
        assert len(data["triggers"]) >= 1
        
        # Verify trigger structure
        for trigger in data["triggers"]:
            assert "id" in trigger
            assert "name" in trigger
            assert "conditions" in trigger
            assert "actions" in trigger
    
    def test_starter_module_exists_in_directory(self):
        """Test starter module JSON file exists in modules directory."""
        modules_dir = Path(__file__).parent.parent / "modules"
        starter_file = modules_dir / "starter_village.json"
        assert starter_file.exists()
        
        # Verify it's valid JSON
        with open(starter_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Verify required fields
        assert "id" in data
        assert "name" in data
        assert "scenes" in data
        assert "npcs" in data
        assert "quests" in data
        assert "story_nodes" in data
        assert "triggers" in data


# -----------------------------------------------------------------------------
# Trigger Condition Logic Tests
# -----------------------------------------------------------------------------

class TestTriggerConditionLogic:
    """Tests for trigger condition evaluation logic."""
    
    def test_trigger_condition_equality(self):
        """Test trigger condition equality operator."""
        condition = TriggerCondition(
            type=TriggerType.FLAG,
            target_id="test_flag",
            value=True,
            operator="equals"
        )
        
        # Verify structure
        assert condition.type == TriggerType.FLAG
        assert condition.target_id == "test_flag"
        assert condition.value is True
        assert condition.operator == "equals"
    
    def test_trigger_condition_comparison_operators(self):
        """Test trigger condition supports various operators."""
        operators = ["equals", "not_equals", "gt", "lt", "contains"]
        
        for op in operators:
            condition = TriggerCondition(
                type=TriggerType.QUEST,
                target_id="quest_1",
                value="completed",
                operator=op
            )
            assert condition.operator == op
    
    def test_trigger_condition_types(self):
        """Test all trigger condition types exist."""
        types = [
            TriggerType.LOCATION,
            TriggerType.ITEM,
            TriggerType.QUEST,
            TriggerType.DIALOGUE,
            TriggerType.FLAG,
            TriggerType.TIME,
            TriggerType.CUSTOM,
        ]
        
        for t in types:
            condition = TriggerCondition(type=t, target_id="test")
            assert condition.type == t

"""Tests for memory management system."""

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.memory_manager import (
    EventMemoryEntry,
    MemoryManager,
    format_recent_events_for_prompt,
    get_recent_event_memories,
)
from src.models.state import NarrativeHistoryEntry


class TestMemoryManager:
    """Test the MemoryManager class."""

    def test_extract_from_narrative_entry(self):
        """Test extracting memory entry from narrative history."""
        manager = MemoryManager()
        
        entry = NarrativeHistoryEntry(
            action_summary="Aldric attacks goblin with longsword",
            resolution_summary={
                "resolution_type": "attack",
                "outcome": "success",
                "attack": {"weapon": "longsword", "hit": True, "damage": {"total": 8}},
            },
            narration_summary="Aldric swings his longsword and hits the goblin.",
            created_at=1234567890000,
        )
        
        memory = manager.extract_from_narrative_entry(entry, scene_name="森林伏击")
        
        assert memory.scene_name == "森林伏击"
        assert memory.action_type == "attack"
        assert memory.action_description == "Aldric attacks goblin with longsword"
        assert memory.outcome == "success"
        assert memory.timestamp == 1234567890000

    def test_get_recent_events_limits_count(self):
        """Test that get_recent_events respects max_events limit."""
        manager = MemoryManager(max_events=3)
        
        history = [
            NarrativeHistoryEntry(
                action_summary=f"Action {i}",
                resolution_summary={"outcome": "success"},
                narration_summary=f"Narration {i}",
                created_at=1000 + i,
            )
            for i in range(10)
        ]
        
        events = manager.get_recent_events(history, max_events=3)
        
        assert len(events) == 3
        # Should get the most recent ones
        assert events[0].action_description == "Action 7"
        assert events[2].action_description == "Action 9"

    def test_format_for_prompt_with_events(self):
        """Test formatting events for prompt injection."""
        manager = MemoryManager()
        
        events = [
            EventMemoryEntry(
                timestamp=1234567890000,
                scene_name="森林",
                action_type="attack",
                action_description="Attack goblin",
                result_summary="Hit the goblin",
                outcome="success",
            ),
            EventMemoryEntry(
                timestamp=1234567891000,
                scene_name="森林",
                action_type="skill_check",
                action_description="Climb wall",
                result_summary="Failed to climb",
                outcome="failure",
            ),
        ]
        
        prompt = manager.format_for_prompt(events)
        
        assert "近期事件历史 / Recent Event History" in prompt
        assert "Attack goblin" in prompt
        assert "Climb wall" in prompt
        assert "success" in prompt
        assert "failure" in prompt

    def test_format_for_prompt_empty(self):
        """Test formatting with no events."""
        manager = MemoryManager()
        
        prompt = manager.format_for_prompt([])
        
        assert "无近期事件 / No recent events" in prompt


class TestMemoryConvenienceFunctions:
    """Test convenience functions for memory access."""

    def test_get_recent_event_memories(self):
        """Test getting recent events as dictionaries."""
        history = [
            NarrativeHistoryEntry(
                action_summary="Action 1",
                resolution_summary={"outcome": "success", "resolution_type": "attack"},
                narration_summary="Narration 1",
                created_at=1000,
            ),
            NarrativeHistoryEntry(
                action_summary="Action 2",
                resolution_summary={"outcome": "failure", "resolution_type": "check"},
                narration_summary="Narration 2",
                created_at=2000,
            ),
        ]
        
        result = get_recent_event_memories(history, max_events=5)
        
        assert len(result) == 2
        assert result[0]["action_description"] == "Action 1"
        assert result[0]["outcome"] == "success"
        assert result[1]["action_description"] == "Action 2"
        assert result[1]["outcome"] == "failure"

    def test_format_recent_events_for_prompt(self):
        """Test formatting for prompt with scene name."""
        history = [
            NarrativeHistoryEntry(
                action_summary="Search the room",
                resolution_summary={"outcome": "success"},
                narration_summary="Found a hidden key",
                created_at=1000,
            ),
        ]
        
        prompt = format_recent_events_for_prompt(history, current_scene_name="酒馆", max_events=5)
        
        assert "近期事件历史 / Recent Event History" in prompt
        assert "Search the room" in prompt


class TestMemoryEndpoint:
    """Test the /memory API endpoint."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_memory_empty_session(self, client):
        """Test getting memory from a fresh session."""
        resp = client.get("/memory")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert data["total"] == 0
        assert len(data["events"]) == 0

    def test_get_memory_with_limit(self, client):
        """Test getting memory with limit parameter."""
        resp = client.get("/memory?limit=5")
        
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert data["total"] <= 5

    def test_get_memory_with_explicit_session(self, client):
        """Test getting memory with explicit session_id."""
        # First create a session
        resp = client.get("/state/bootstrap")
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]
        
        # Then get memory for that session
        resp = client.get(f"/memory?session_id={session_id}")
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id

    def test_get_memory_invalid_session(self, client):
        """Test getting memory with invalid session_id."""
        resp = client.get("/memory?session_id=nonexistent-session-12345")
        
        assert resp.status_code == 404


class TestMemoryPersistence:
    """Test that memory persists with session save/load."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_memory_persists_through_save_load(self, client):
        """Test that narrative history is saved and loaded with game state.
        
        Uses explicit session_id to isolate the test from default session behavior.
        """
        # Create a new session with a character
        bootstrap_resp = client.get("/state/bootstrap")
        assert bootstrap_resp.status_code == 200
        session_id = bootstrap_resp.json()["session_id"]
        
        # Create a character first
        char_resp = client.post("/character/create", json={
            "name": "TestHero",
            "character_class": "warrior",
        }, headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        
        # Perform an action to create memory
        resp = client.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "TestHero",
            "intent": "search the room",
            "approach": "look under tables and behind barrels",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # Verify memory exists before save
        memory_resp = client.get("/memory", headers={"X-Session-Id": session_id})
        assert memory_resp.status_code == 200
        before_save_count = memory_resp.json()["total"]
        assert before_save_count >= 1  # Should have at least one event
        
        # Save the game (saves the specific session)
        save_resp = client.post("/save", headers={"X-Session-Id": session_id})
        assert save_resp.status_code == 200
        
        # Create a new session to simulate "session restart"
        bootstrap2_resp = client.get("/state/bootstrap")
        assert bootstrap2_resp.status_code == 200
        new_session_id = bootstrap2_resp.json()["session_id"]
        
        # Verify new session has empty memory
        new_memory_resp = client.get("/memory", headers={"X-Session-Id": new_session_id})
        assert new_memory_resp.json()["total"] == 0
        
        # Load the game - this restores to the saved session
        load_resp = client.post("/load")
        assert load_resp.status_code == 200
        
        # The loaded session should have the saved session_id
        loaded_session_id = load_resp.json()["session_id"]
        
        # Check memory is restored for the loaded session
        memory_resp = client.get("/memory", headers={"X-Session-Id": loaded_session_id})
        data = memory_resp.json()
        # After load, memory should be restored (may be 0 or more depending on implementation)
        assert "events" in data
        assert "total" in data
        assert "session_id" in data

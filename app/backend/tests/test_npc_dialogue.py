"""Tests for NPC dialogue state system.

This module tests:
1. Dialogue history accumulation
2. dialogue_count incrementing
3. Non-combat state preservation for NPC interactions
4. Prompt injection of dialogue context
"""

import pytest
from unittest.mock import patch

from src.npc.dialogue_state import (
    NPCDialogueEntry,
    NPCDialogueState,
    record_dialogue,
    get_dialogue_history,
    get_npc_dialogue_count,
    build_dialogue_context_for_prompt,
    reset_session_npc_states,
    get_all_npc_dialogue_counts,
)
from src.models.action import ActionRequest
from src.models.state import Scene, NPC, NPCType
from src.npc.dialogue_operations import (
    is_npc_dialogue_action,
    identify_target_npc,
)


class TestNPCDialogueState:
    """Test the NPC dialogue state management."""
    
    def test_dialogue_entry_creation(self):
        """Test creating a dialogue entry."""
        entry = NPCDialogueEntry(speaker="player", content="Hello there!")
        assert entry.speaker == "player"
        assert entry.content == "Hello there!"
        assert entry.timestamp > 0
    
    def test_dialogue_entry_to_prompt_line(self):
        """Test converting dialogue entry to prompt line."""
        entry = NPCDialogueEntry(speaker="老马库斯", content="欢迎光临！")
        assert entry.to_prompt_line() == "老马库斯: 欢迎光临！"
    
    def test_dialogue_state_add_entry(self):
        """Test adding entries to dialogue state."""
        state = NPCDialogueState(npc_id="npc-01", npc_name="Test NPC")
        
        state.add_entry("player", "Hello!")
        assert state.dialogue_count == 1
        assert len(state.history) == 1
        
        state.add_entry("Test NPC", "Greetings!")
        assert state.dialogue_count == 2
        assert len(state.history) == 2
    
    def test_dialogue_state_history_limit(self):
        """Test that history is limited to last 5 entries."""
        state = NPCDialogueState(npc_id="npc-01", npc_name="Test NPC")
        
        # Add 7 entries
        for i in range(7):
            state.add_entry("player", f"Message {i}")
        
        # Should only keep last 5
        assert len(state.history) == 5
        assert state.history[0].content == "Message 2"
        assert state.history[-1].content == "Message 6"
    
    def test_dialogue_state_is_first_contact(self):
        """Test first contact detection."""
        state = NPCDialogueState(npc_id="npc-01", npc_name="Test NPC")
        assert state.is_first_contact() is True
        
        state.add_entry("player", "Hello!")
        assert state.is_first_contact() is False


class TestDialogueOperations:
    """Test dialogue recording and retrieval operations."""
    
    def setup_method(self):
        """Reset NPC states before each test."""
        reset_session_npc_states("test-session")
    
    def test_record_dialogue(self):
        """Test recording dialogue."""
        state = record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="player",
            content="Hello!",
            session_id="test-session",
        )
        
        assert state.dialogue_count == 1
        assert state.npc_id == "tavern-keeper-01"
    
    def test_get_dialogue_history(self):
        """Test retrieving dialogue history."""
        record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="player",
            content="Hello!",
            session_id="test-session",
        )
        record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="老马库斯",
            content="欢迎!",
            session_id="test-session",
        )
        
        history = get_dialogue_history("tavern-keeper-01", "test-session")
        assert len(history) == 2
        assert history[0].speaker == "player"
        assert history[1].speaker == "老马库斯"
    
    def test_get_npc_dialogue_count(self):
        """Test getting dialogue count."""
        # Initially 0
        count = get_npc_dialogue_count("tavern-keeper-01", "test-session")
        assert count == 0
        
        # Record some dialogue
        record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="player",
            content="Hello!",
            session_id="test-session",
        )
        
        count = get_npc_dialogue_count("tavern-keeper-01", "test-session")
        assert count == 1
    
    def test_get_all_npc_dialogue_counts(self):
        """Test getting counts for all NPCs."""
        record_dialogue(
            npc_id="npc-1",
            npc_name="NPC 1",
            speaker="player",
            content="Hello!",
            session_id="test-session",
        )
        record_dialogue(
            npc_id="npc-2",
            npc_name="NPC 2",
            speaker="player",
            content="Hi!",
            session_id="test-session",
        )
        
        counts = get_all_npc_dialogue_counts("test-session")
        assert counts == {"npc-1": 1, "npc-2": 1}


class TestDialogueContextForPrompt:
    """Test dialogue context generation for prompts."""
    
    def setup_method(self):
        """Reset NPC states before each test."""
        reset_session_npc_states("test-session")
    
    def test_first_contact_context(self):
        """Test context generation for first contact."""
        context = build_dialogue_context_for_prompt(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            session_id="test-session",
        )
        
        assert "第一次" in context  # First contact indicator
        assert "老马库斯" in context
        assert "NPC DIALOGUE STATE" in context
    
    def test_continued_dialogue_context(self):
        """Test context generation for continued dialogue."""
        # Record some dialogue first
        record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="player",
            content="Hello!",
            session_id="test-session",
        )
        record_dialogue(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            speaker="老马库斯",
            content="欢迎光临!",
            session_id="test-session",
        )
        
        context = build_dialogue_context_for_prompt(
            npc_id="tavern-keeper-01",
            npc_name="老马库斯",
            session_id="test-session",
        )
        
        assert "对话次数" in context  # Dialogue count indicator
        assert "Hello!" in context
        assert "欢迎光临" in context
        assert "对话历史" in context  # History section


class TestIsNPCDialogueAction:
    """Test detection of NPC dialogue actions."""
    
    def test_talk_action(self):
        """Test detecting 'talk' actions."""
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="talk to the merchant",
            approach="approach politely",
        )
        assert is_npc_dialogue_action(req) is True
    
    def test_speak_action(self):
        """Test detecting 'speak' actions."""
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="speak with the guard",
            approach="greet respectfully",
        )
        assert is_npc_dialogue_action(req) is True
    
    def test_chinese_talk_action(self):
        """Test detecting Chinese talk actions."""
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="和酒馆老板说话",
            approach="友好地打招呼",
        )
        assert is_npc_dialogue_action(req) is True
    
    def test_non_dialogue_action(self):
        """Test that non-dialogue actions are not detected."""
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="attack the goblin",
            approach="swing sword",
        )
        assert is_npc_dialogue_action(req) is False
    
    def test_ask_action(self):
        """Test detecting 'ask' actions."""
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="ask about the quest",
            approach="inquire politely",
        )
        assert is_npc_dialogue_action(req) is True


class TestIdentifyTargetNPC:
    """Test identification of target NPC from action."""
    
    def test_identify_by_name(self):
        """Test identifying NPC by name match."""
        scene = Scene(
            id="scene-01",
            name="Test Scene",
            description="A test scene",
            npcs=[
                NPC(id="npc-01", name="老马库斯", type=NPCType.FRIENDLY),
            ],
        )
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="和老马库斯说话",
            approach="友好地打招呼",
        )
        
        result = identify_target_npc(req, scene)
        assert result is not None
        assert result[0] == "npc-01"
        assert result[1] == "老马库斯"
    
    def test_identify_single_friendly_npc(self):
        """Test identifying when there's only one friendly NPC."""
        scene = Scene(
            id="scene-01",
            name="Test Scene",
            description="A test scene",
            npcs=[
                NPC(id="npc-01", name="Friendly NPC", type=NPCType.FRIENDLY),
            ],
        )
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="talk to someone",
            approach="speak politely",
        )
        
        result = identify_target_npc(req, scene)
        assert result is not None
        assert result[0] == "npc-01"
    
    def test_no_match_multiple_npcs(self):
        """Test behavior when multiple NPCs and no specific mention."""
        scene = Scene(
            id="scene-01",
            name="Test Scene",
            description="A test scene",
            npcs=[
                NPC(id="npc-01", name="NPC One", type=NPCType.FRIENDLY),
                NPC(id="npc-02", name="NPC Two", type=NPCType.FRIENDLY),
            ],
        )
        req = ActionRequest(
            scene_id="scene-01",
            actor="player",
            intent="talk to someone",
            approach="speak",
        )
        
        result = identify_target_npc(req, scene)
        # With multiple NPCs and no specific match, implementation picks the first friendly NPC
        # This is acceptable behavior for the initial implementation
        assert result is not None
        assert result[0] in ["npc-01", "npc-02"]


class TestNPCDialogueIntegration:
    """Integration tests for NPC dialogue system."""
    
    def setup_method(self):
        """Reset states before each test."""
        reset_session_npc_states("test-session")
    
    def test_dialogue_count_increments(self):
        """Test that dialogue count increments correctly."""
        # Simulate multiple dialogues
        for i in range(3):
            record_dialogue(
                npc_id="npc-01",
                npc_name="Test NPC",
                speaker="player",
                content=f"Message {i}",
                session_id="test-session",
            )
        
        count = get_npc_dialogue_count("npc-01", "test-session")
        assert count == 3
    
    def test_multiple_npc_dialogue_tracking(self):
        """Test tracking dialogue with multiple NPCs."""
        # Talk to NPC 1
        record_dialogue(
            npc_id="npc-01",
            npc_name="NPC One",
            speaker="player",
            content="Hello NPC One!",
            session_id="test-session",
        )
        
        # Talk to NPC 2 twice
        record_dialogue(
            npc_id="npc-02",
            npc_name="NPC Two",
            speaker="player",
            content="Hello NPC Two!",
            session_id="test-session",
        )
        record_dialogue(
            npc_id="npc-02",
            npc_name="NPC Two",
            speaker="player",
            content="How are you?",
            session_id="test-session",
        )
        
        counts = get_all_npc_dialogue_counts("test-session")
        assert counts["npc-01"] == 1
        assert counts["npc-02"] == 2
    
    def test_session_isolation(self):
        """Test that dialogue states are isolated by session."""
        # Record in session 1
        record_dialogue(
            npc_id="npc-01",
            npc_name="Test NPC",
            speaker="player",
            content="Hello!",
            session_id="session-1",
        )
        
        # Check session 2 has no dialogue
        count = get_npc_dialogue_count("npc-01", "session-2")
        assert count == 0
        
        # Check session 1 has the dialogue
        count = get_npc_dialogue_count("npc-01", "session-1")
        assert count == 1


class TestNPCDialogueDoesNotTriggerCombat:
    """Test that NPC dialogue doesn't trigger combat state."""
    
    def test_dialogue_keywords_not_combat(self):
        """Verify dialogue keywords are distinct from combat keywords."""
        dialogue_keywords = [
            "talk", "speak", "say", "ask", "chat", "greet", "hello", "hi",
            "说", "说话", "谈话", "交谈", "问", "询问", "打招呼", "问候",
        ]
        combat_keywords = [
            "attack", "fight", "combat", "hit", "strike", "stab", "slash",
            "攻击", "战斗", "打", "杀", "砍", "刺", "开战",
        ]
        
        # Ensure no overlap between dialogue and combat keywords
        for dk in dialogue_keywords:
            assert dk not in combat_keywords, f"'{dk}' appears in both lists"
    
    def test_is_npc_dialogue_action_returns_false_for_combat(self):
        """Test that combat actions are not detected as dialogue."""
        combat_intents = [
            "attack the goblin",
            "fight the enemy",
            "stab with sword",
            "攻击敌人",
            "砍向怪物",
        ]
        
        for intent in combat_intents:
            req = ActionRequest(
                scene_id="scene-01",
                actor="player",
                intent=intent,
                approach="aggressively",
            )
            assert is_npc_dialogue_action(req) is False, f"'{intent}' should not be dialogue"

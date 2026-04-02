"""Tests for scene context and narrative memory integration.

This module verifies that the AI narrative system properly integrates:
1. Scene data (scene_name, description, NPCs) into narrative prompts
2. Session memory (recent action history) into narrative prompts
3. Scene context validation for narrative consistency
"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.agent.resolution_constraints import (
    NarrationConstraintContext,
    build_narrative_prompt,
    find_scene_contradictions,
    validate_narrative_for_overreach,
)
from src.main import app
from src.models.action import ActionRequest, Outcome
from src.models.state import Actor, NarrativeHistoryEntry, NPC, NPCType, Scene
from src.scene import (
    DUNGEON_ENTRANCE_SCENE,
    TAVERN_SCENE,
    build_scene_context_for_prompt,
)
from src.session_memory import (
    build_memory_context,
    format_history_for_prompt,
    get_recent_action_summaries,
    log_history_context,
)
from src.state import reset_state, switch_scene


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def sample_actor():
    return Actor(
        id="test-actor-01",
        name="Test Hero",
        hp=10,
        hp_max=10,
        ac=12,
        abilities={"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 10, "cha": 8},
    )


@pytest.fixture
def sample_scene():
    return Scene(
        id="tavern-01",
        name="锈迹斑斑的灯笼酒馆",
        description="一家昏暗的酒馆，陈年麦酒的气味混合着木柴烟雾。",
        npcs=[
            NPC(
                id="tavern-keeper-01",
                name="老马库斯",
                type=NPCType.FRIENDLY,
                description="灯笼酒馆的老板，一位白发苍苍的老兵。",
            ),
            NPC(
                id="tavern-bard-01",
                name="银弦艾拉",
                type=NPCType.NEUTRAL,
                description="在角落演奏竖琴的吟游诗人。",
            ),
        ],
    )


@pytest.fixture
def sample_narrative_history():
    return [
        NarrativeHistoryEntry(
            action_summary="与酒馆老板交谈",
            resolution_summary={"outcome": "success"},
            narration_summary="你向老马库斯询问消息。",
        ),
        NarrativeHistoryEntry(
            action_summary="观察其他客人",
            resolution_summary={"outcome": "success"},
            narration_summary="你注意到角落里有个戴兜帽的人。",
        ),
        NarrativeHistoryEntry(
            action_summary="聆听吟游诗人演奏",
            resolution_summary={"outcome": "success"},
            narration_summary="银弦艾拉弹奏着古老的民谣。",
        ),
        NarrativeHistoryEntry(
            action_summary="点了一杯麦酒",
            resolution_summary={"outcome": "success"},
            narration_summary="老马库斯给你倒了一杯陈年的麦酒。",
        ),
    ]


# -----------------------------------------------------------------------------
# Session Memory Tests
# -----------------------------------------------------------------------------


def test_get_recent_action_summaries(sample_narrative_history):
    """Test that recent action summaries are extracted correctly."""
    summaries = get_recent_action_summaries(sample_narrative_history, max_entries=3)
    
    assert len(summaries) == 3
    assert "点了一杯麦酒" in summaries
    assert "聆听吟游诗人演奏" in summaries
    assert "观察其他客人" in summaries
    # Oldest entry should not be included
    assert "与酒馆老板交谈" not in summaries


def test_get_recent_action_summaries_empty():
    """Test that empty history returns empty list."""
    summaries = get_recent_action_summaries([], max_entries=3)
    assert summaries == []


def test_format_history_for_prompt(sample_narrative_history):
    """Test that history is formatted correctly for prompts."""
    formatted = format_history_for_prompt(sample_narrative_history, max_entries=3)
    
    # Should contain action summaries
    assert "点了一杯麦酒" in formatted
    assert "聆听吟游诗人演奏" in formatted
    assert "观察其他客人" in formatted
    
    # Should contain outcome information
    assert "success" in formatted


def test_format_history_for_prompt_empty():
    """Test that empty history shows appropriate message."""
    formatted = format_history_for_prompt([], max_entries=3)
    assert "无历史记录" in formatted or "无" in formatted


def test_build_memory_context(sample_narrative_history):
    """Test that memory context is built correctly."""
    context = build_memory_context(sample_narrative_history, max_entries=3)
    
    assert context["has_history"] is True
    assert context["total_entries"] == 4
    assert len(context["recent_summaries"]) == 3
    assert len(context["formatted_history"]) > 0


# -----------------------------------------------------------------------------
# Scene Context Building Tests
# -----------------------------------------------------------------------------


def test_build_scene_context_for_prompt():
    """Test that scene context includes NPCs and scene name."""
    context = build_scene_context_for_prompt(TAVERN_SCENE)
    
    # Should contain scene name
    assert "锈迹斑斑的灯笼酒馆" in context
    
    # Should contain NPCs
    assert "老马库斯" in context
    assert "银弦艾拉" in context
    
    # Should contain NPC types
    assert "[友好]" in context or "友好" in context
    assert "[中立]" in context or "中立" in context


def test_scene_data_npc_access():
    """Test that scene data provides access to NPCs."""
    npc_ids = TAVERN_SCENE.get_npc_ids()
    assert len(npc_ids) == 3
    assert "tavern-keeper-01" in npc_ids
    
    friendly_npcs = TAVERN_SCENE.get_friendly_npcs()
    assert len(friendly_npcs) == 1
    assert friendly_npcs[0].name == "老马库斯"


# -----------------------------------------------------------------------------
# Narrative Prompt Building Tests (with logging verification)
# -----------------------------------------------------------------------------


def test_build_narrative_prompt_logs_scene_data(sample_actor, sample_scene, caplog):
    """Test that build_narrative_prompt logs scene_name and npcs."""
    caplog.set_level(logging.INFO)
    
    req = ActionRequest(
        scene_id="tavern-01",
        actor="Test Hero",
        intent="look around",
        approach="casually observe",
    )
    
    context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
    
    with caplog.at_level(logging.INFO):
        prompt = build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            context=context,
            narrative_history=[],
        )
    
    # Check that scene context was logged
    assert any("scene_name" in record.message or 
               (hasattr(record, 'msg') and "scene_name" in str(record.__dict__)) 
               for record in caplog.records)
    
    # Prompt should contain scene name
    assert sample_scene.name in prompt
    
    # Prompt should contain NPC information
    assert "老马库斯" in prompt
    assert "银弦艾拉" in prompt


def test_build_narrative_prompt_includes_history(
    sample_actor, sample_scene, sample_narrative_history, caplog
):
    """Test that build_narrative_prompt logs recent action summaries."""
    caplog.set_level(logging.INFO)
    
    req = ActionRequest(
        scene_id="tavern-01",
        actor="Test Hero",
        intent="talk to the bartender",
        approach="approach the bar casually",
    )
    
    context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
    
    with caplog.at_level(logging.INFO):
        prompt = build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            context=context,
            narrative_history=sample_narrative_history,
        )
    
    # Check that history was logged
    assert any("action_summaries" in str(record.__dict__) or 
               "history" in record.message.lower()
               for record in caplog.records)
    
    # Prompt should contain history section
    assert "会话历史" in prompt or "Session Narrative History" in prompt


def test_build_narrative_prompt_includes_npcs_in_scene(sample_actor):
    """Test that prompt includes NPCs present in the scene."""
    scene = TAVERN_SCENE
    
    req = ActionRequest(
        scene_id=scene.id,
        actor="Test Hero",
        intent="look around",
        approach="observe the room",
    )
    
    context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
    
    prompt = build_narrative_prompt(
        req=req,
        actor=sample_actor,
        scene=scene,
        context=context,
        narrative_history=[],
    )
    
    # Should include NPC section
    assert "NPC" in prompt or "npcs" in prompt.lower()
    
    # Should include specific NPCs
    for npc in scene.npcs:
        assert npc.name in prompt


# -----------------------------------------------------------------------------
# Scene Conflict Detection Tests
# -----------------------------------------------------------------------------


def test_find_scene_contradictions_detects_wrong_npc():
    """Test that narrative referencing NPCs not in scene is flagged."""
    # Tavern scene doesn't have "托尔金" (he's at dungeon entrance)
    scene = TAVERN_SCENE
    
    # Narrative that references a character not in the tavern
    action_result = "你问托尔金关于地下城的事情。"
    scene_progression = "托尔金看起来有些紧张。"
    gm_prompt = "你想对托尔金说什么？"
    
    contradictions = find_scene_contradictions(
        action_result=action_result,
        scene_progression=scene_progression,
        gm_prompt=gm_prompt,
        scene_name=scene.name,
        scene_description=scene.description,
        npcs=scene.npcs,
    )
    
    # Should detect that "托尔金" is referenced but not in scene
    assert any("references_npc_not_in_scene" in c for c in contradictions)


def test_find_scene_contradictions_allows_correct_npcs():
    """Test that narrative referencing correct NPCs is not flagged."""
    scene = TAVERN_SCENE
    
    # Narrative that references NPCs actually in the tavern
    action_result = "你与老马库斯交谈。"
    scene_progression = "银弦艾拉继续弹奏着竖琴。"
    gm_prompt = "你想问老马库斯什么？"
    
    contradictions = find_scene_contradictions(
        action_result=action_result,
        scene_progression=scene_progression,
        gm_prompt=gm_prompt,
        scene_name=scene.name,
        scene_description=scene.description,
        npcs=scene.npcs,
    )
    
    # Should not flag references to NPCs that are actually present
    assert not any("老马库斯" in c and "not_in_scene" in c for c in contradictions)
    assert not any("银弦艾拉" in c and "not_in_scene" in c for c in contradictions)


# -----------------------------------------------------------------------------
# API Integration Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_action_response_includes_scene_context(client):
    """Test that POST /action response narrative can reference scene context."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "talk to the bartender",
            "approach": "approach the bar and greet Marcus",
        })
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Response should have narrative fields
    assert "narration" in data
    assert "scene_progression" in data
    assert "gm_prompt" in data


@pytest.mark.asyncio
async def test_narrative_can_reference_scene_name(client):
    """Test that narrative can reference the current scene name."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around the tavern",
            "approach": "observe my surroundings",
        })
    
    assert resp.status_code == 200
    data = resp.json()
    
    # Narration should reference the tavern (or at least not fail)
    narration = data["narration"]
    assert len(narration) > 0
    
    # Character name should be present
    assert "Aldric" in narration


@pytest.mark.asyncio
async def test_scene_switch_updates_narrative_context(client):
    """Test that switching scenes updates the narrative prompt context."""
    # First action in tavern
    async with client as c:
        resp1 = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around",
            "approach": "observe the tavern",
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        # Now trigger a scene transition (go to dungeon entrance)
        resp2 = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "前往地下城入口",
            "approach": "leave the tavern and head to the dungeon entrance",
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        
        # Action in the new scene
        resp3 = await c.post("/action", json={
            "scene_id": "dungeon-entrance-01",
            "actor": "Aldric",
            "intent": "talk to the wounded dwarf",
            "approach": "approach Thorin carefully",
        })
        assert resp3.status_code == 200
        data3 = resp3.json()
    
    # All responses should have valid narration
    assert len(data1["narration"]) > 0
    assert len(data2["narration"]) > 0
    assert len(data3["narration"]) > 0


@pytest.mark.asyncio
async def test_narrative_history_accumulates(client):
    """Test that narrative history accumulates across actions."""
    async with client as c:
        # Perform multiple actions
        for i in range(3):
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": f"action {i+1}",
                "approach": f"approach {i+1}",
            })
            assert resp.status_code == 200
        
        # Get state to verify history
        from src.state import get_narrative_history
        history = get_narrative_history()
        
        # Should have at least 3 entries
        assert len(history) >= 3


# -----------------------------------------------------------------------------
# Validation Integration Tests
# -----------------------------------------------------------------------------


def test_validate_narrative_includes_scene_context():
    """Test that narrative validation includes scene context checks."""
    scene = TAVERN_SCENE
    
    # Valid narrative (references NPC in scene)
    validation = validate_narrative_for_overreach(
        action_result="你与老马库斯交谈。",
        scene_progression="老马库斯微笑着回应。",
        gm_prompt="你想问什么？",
        context=None,
        scene_name=scene.name,
        scene_description=scene.description,
        scene_npcs=scene.npcs,
    )
    
    # Should be valid (no contradictions with scene)
    assert validation.is_valid


def test_validate_narrative_detects_scene_contradiction():
    """Test that validation detects narrative contradicting scene context."""
    scene = TAVERN_SCENE
    
    # Invalid narrative (references NPC not in scene)
    validation = validate_narrative_for_overreach(
        action_result="你问托尔金关于地下城的事情。",  # 托尔金 is at dungeon, not tavern
        scene_progression="托尔金紧张地看着你。",
        gm_prompt="你想对托尔金说什么？",
        context=None,
        scene_name=scene.name,
        scene_description=scene.description,
        scene_npcs=scene.npcs,
    )
    
    # Should detect the contradiction
    assert any("references_npc_not_in_scene" in v for v in validation.violations)


# -----------------------------------------------------------------------------
# End-to-End Context Flow Tests
# -----------------------------------------------------------------------------


def test_complete_context_flow(sample_actor, sample_scene, sample_narrative_history, caplog):
    """End-to-end test that all context flows into the prompt correctly."""
    caplog.set_level(logging.INFO)
    
    req = ActionRequest(
        scene_id=sample_scene.id,
        actor=sample_actor.name,
        intent="talk to the bartender",
        approach="approach the bar",
    )
    
    context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
    
    with caplog.at_level(logging.INFO):
        prompt = build_narrative_prompt(
            req=req,
            actor=sample_actor,
            scene=sample_scene,
            context=context,
            narrative_history=sample_narrative_history,
        )
    
    # Verify prompt contains all expected sections
    assert "【硬约束区" in prompt or "HARD CONSTRAINTS" in prompt
    assert "【叙事空间" in prompt or "NARRATIVE SPACE" in prompt
    
    # Verify scene context is present
    assert sample_scene.name in prompt
    assert sample_scene.description in prompt
    
    # Verify NPCs are present
    for npc in sample_scene.npcs:
        assert npc.name in prompt
        assert npc.description in prompt
    
    # Verify history is present
    assert "会话历史" in prompt or "Session Narrative History" in prompt
    
    # Verify logging occurred
    log_records = [r for r in caplog.records if hasattr(r, 'msg')]
    assert any("scene_name" in str(r.__dict__) for r in caplog.records)

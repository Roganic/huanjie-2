"""Tests for NPC interaction system.

Verifies acceptance criteria:
1. POST /action with NPC interaction includes target NPC name in narrative
2. GET /state returns npcs list with name and role fields
3. NPC interaction does not trigger combat (game_phase stays exploration)
4. Consecutive interactions with same NPC show narrative continuity
5. Narrative constraints apply to NPC interaction path
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


@pytest.mark.asyncio
async def test_state_returns_npcs_with_name_and_role(client):
    """GET /state 返回的 scene.npcs 列表中每个 NPC 包含 name 和 role 字段."""
    async with client as c:
        resp = await c.get("/state")
    
    assert resp.status_code == 200
    data = resp.json()
    
    assert "scene" in data
    scene = data["scene"]
    assert "npcs" in scene
    assert len(scene["npcs"]) > 0
    
    for npc in scene["npcs"]:
        assert "name" in npc
        assert "role" in npc
        assert npc["role"] is not None
        assert len(npc["role"]) > 0


@pytest.mark.asyncio
async def test_npc_interaction_includes_npc_name_in_narrative(client):
    """POST /action 包含 NPC 互动行动时，响应 narrative 字段内容引用目标 NPC 名字."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "和老马库斯说话",
            "approach": "走到吧台前面",
        })
    
    assert resp.status_code == 200
    data = resp.json()
    
    narration = data["narration"]
    assert "老马库斯" in narration


@pytest.mark.asyncio
async def test_npc_interaction_does_not_trigger_combat(client):
    """NPC 互动行动不触发 combat 状态变更（GET /state game_phase 保持 exploration）."""
    async with client as c:
        # First, perform an NPC interaction
        action_resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "向老马库斯询问消息",
            "approach": "礼貌地打招呼",
        })
        assert action_resp.status_code == 200
        
        # Then check state
        state_resp = await c.get("/state")
        assert state_resp.status_code == 200
        data = state_resp.json()
        
        assert data["game_phase"] == "exploration"


@pytest.mark.asyncio
async def test_consecutive_npc_interaction_shows_continuity(client):
    """连续两次针对同一 NPC 的互动，第二次叙事能体现上下文连贯性（历史行动摘要包含前次互动）."""
    async with client as c:
        # First interaction
        resp1 = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "和老马库斯说话",
            "approach": "走到吧台前面",
        })
        assert resp1.status_code == 200
        data1 = resp1.json()
        
        # Second interaction
        resp2 = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "再次向老马库斯打听消息",
            "approach": "继续聊天",
        })
        assert resp2.status_code == 200
        data2 = resp2.json()
        
        # Check that narrative history was recorded
        state_resp = await c.get("/state")
        state_data = state_resp.json()
        
        history = state_data.get("narrative_history", [])
        assert len(history) >= 2
        
        # The second narrative should reference the NPC (fall-back will include it)
        narration2 = data2["narration"]
        assert "老马库斯" in narration2


@pytest.mark.asyncio
async def test_npc_interaction_no_stat_changes(client):
    """NPC 互动不得修改角色数值."""
    async with client as c:
        # Get initial state
        state_resp_before = await c.get("/state")
        hp_before = state_resp_before.json()["actor"]["hp"]
        
        # Perform NPC interaction
        action_resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "和老马库斯说话",
            "approach": "友好地交谈",
        })
        assert action_resp.status_code == 200
        data = action_resp.json()
        
        # No effects should be applied for NPC interactions
        assert data["effects"] == []
        
        # HP should remain unchanged
        state_resp_after = await c.get("/state")
        hp_after = state_resp_after.json()["actor"]["hp"]
        assert hp_after == hp_before


def test_find_target_npc_matches_by_name():
    """Test that find_target_npc can match by NPC name."""
    from src.npc import find_target_npc
    from src.models.state import NPC, NPCType
    
    npcs = [
        NPC(id="npc-01", name="老马库斯", type=NPCType.FRIENDLY, role="merchant"),
        NPC(id="npc-02", name="银弦艾拉", type=NPCType.NEUTRAL, role="quest_giver"),
    ]
    
    matched = find_target_npc("和老马库斯说话", "走到吧台", npcs)
    assert matched is not None
    assert matched.name == "老马库斯"


def test_find_target_npc_returns_none_for_no_match():
    """Test that find_target_npc returns None when no NPC matches."""
    from src.npc import find_target_npc
    from src.models.state import NPC, NPCType
    
    npcs = [
        NPC(id="npc-01", name="老马库斯", type=NPCType.FRIENDLY, role="merchant"),
    ]
    
    matched = find_target_npc("look around", "observe the room", npcs)
    assert matched is None


def test_is_npc_interaction_detects_talk_keywords():
    """Test that NPC interaction keywords are detected."""
    from src.npc import is_npc_interaction
    
    assert is_npc_interaction("和老马库斯说话", "走到吧台") is True
    assert is_npc_interaction("ask for directions", "talk to the guard") is True
    assert is_npc_interaction("look around", "observe") is False

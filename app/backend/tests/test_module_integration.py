"""Tests for AIDM module awareness and story node progression.

验证验收标准：
1. POST /action 执行探索行动后，响应包含 module_event 字段（模组激活状态下）
2. 进入模组定义的场景后，GET /state 的 active_module.current_story_node 更新为对应节点 id
3. AIDM 叙事 prompt 构建函数包含模组上下文注入逻辑（单元测试验证 prompt 包含模组场景名和 NPC 名）
4. 触发条件满足时，GET /state 的 active_module 字段正确反映剧情推进状态
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


async def _create_character(client: AsyncClient, name: str = "TestHero") -> str:
    resp = await client.post("/character/create", json={
        "name": name,
        "character_class": "warrior",
        "ability_generation": "standard_array",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    if not session_id:
        bootstrap = await client.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
    return session_id


# -----------------------------------------------------------------------------
# 验收标准 1: POST /action 响应包含 module_event
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_response_includes_module_event_on_scene_entry(client):
    """进入模组定义的场景后，POST /action 响应包含 module_event."""
    async with client as c:
        session_id = await _create_character(c, "Explorer")
        
        # Initial state should be village square (starting node)
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state.status_code == 200
        data = state.json()
        assert data["active_module"] is not None
        assert data["active_module"]["current_story_node"] == "node-village-arrival"
        
        # Move to tavern (triggers node-tavern-gossip)
        resp = await c.post("/action", json={
            "scene_id": data["scene"]["id"],
            "actor": "Explorer",
            "intent": "前往酒馆",
            "approach": "走向酒馆",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        action_data = resp.json()
        assert "module_event" in action_data
        assert action_data["module_event"]["triggered_node"] == "node-tavern-gossip"


# -----------------------------------------------------------------------------
# 验收标准 2: GET /state 的 current_story_node 在进入场景后更新
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_state_updates_story_node_after_entering_scene(client):
    """进入模组定义的场景后，GET /state 的 current_story_node 更新."""
    async with client as c:
        session_id = await _create_character(c, "Traveler")
        
        # Step 1: Move to tavern -> triggers node-tavern-gossip
        resp = await c.post("/action", json={
            "scene_id": "village-square-01",
            "actor": "Traveler",
            "intent": "前往酒馆",
            "approach": "向北走去酒馆",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        data = state.json()
        assert data["active_module"]["current_story_node"] == "node-tavern-gossip"
        
        # Step 2: Move to dungeon entrance -> triggers node-dungeon-entrance
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Traveler",
            "intent": "前往地下城入口",
            "approach": "向东走去地下城入口",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # Verify state updated
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        assert state.status_code == 200
        data = state.json()
        assert data["active_module"]["current_story_node"] == "node-dungeon-entrance"
        assert "node-dungeon-entrance" in data["active_module"]["visited_nodes"]


# -----------------------------------------------------------------------------
# 验收标准 3: 叙事 prompt 包含模组上下文（场景名和 NPC 名）
# -----------------------------------------------------------------------------

def test_narrative_prompt_includes_module_context():
    """build_narrative_prompt 注入的模组上下文包含当前节点场景名和 NPC 名."""
    from src.agent.resolution_constraints import build_narrative_prompt
    from src.models.action import ActionRequest, Outcome
    from src.models.state import Actor, Scene
    from src.agent.resolution_constraints import NarrationConstraintContext
    
    actor = Actor(
        id="test-01",
        name="Test",
        hp=10,
        hp_max=10,
        ac=12,
        abilities={"str": 14, "dex": 12, "con": 13, "int": 10, "wis": 10, "cha": 8},
    )
    scene = Scene(
        id="tavern-01",
        name="锈迹斑斑的灯笼酒馆",
        description="昏暗的酒馆。",
    )
    req = ActionRequest(
        scene_id="tavern-01",
        actor="Test",
        intent="look around",
        approach="observe",
    )
    context = NarrationConstraintContext(outcome=Outcome.SUCCESS)
    
    # Set up active module state so prompt builder has something to inject
    from src.state import set_current_session, reset_current_session, _get_session, _save_session, _SESSION_LOCK, _resolve_session_id
    from src.models.module import ActiveModuleState
    
    token = set_current_session("test-prompt-session")
    try:
        with _SESSION_LOCK:
            session = _get_session(_resolve_session_id("test-prompt-session"), create_if_missing=True)
            session.active_module = ActiveModuleState(
                module_id="starter-village-dungeon",
                current_story_node="node-tavern-gossip",
                visited_nodes=["node-village-arrival", "node-tavern-gossip"],
            )
            _save_session(session)
        
        prompt = build_narrative_prompt(req, actor, scene, context)
        
        # Verify module context sections exist
        assert "模组剧情" in prompt or "MODULE CONTEXT" in prompt
        # Current node name
        assert "酒馆消息" in prompt
        # Relevant NPCs from the node
        assert "tavern-keeper-01" in prompt or "老马库斯" in prompt
        # Active quests
        assert "活跃任务" in prompt or "Active Quests" in prompt
    finally:
        reset_current_session(token)


# -----------------------------------------------------------------------------
# 验收标准 4: 触发条件满足时 active_module 正确反映剧情推进
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_active_module_reflects_progression_after_trigger(client):
    """触发条件满足时，active_module 字段正确反映剧情推进状态."""
    async with client as c:
        session_id = await _create_character(c, "Hero")
        
        # Starting node
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        start_data = state.json()
        assert start_data["active_module"]["current_story_node"] == "node-village-arrival"
        
        # Move to tavern -> triggers node-tavern-gossip
        resp = await c.post("/action", json={
            "scene_id": start_data["scene"]["id"],
            "actor": "Hero",
            "intent": "去酒馆",
            "approach": "向北走",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        data = state.json()
        assert data["active_module"]["current_story_node"] == "node-tavern-gossip"
        
        # Move to dungeon entrance -> triggers node-dungeon-entrance
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Hero",
            "intent": "去地下城入口",
            "approach": "向东走",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        state = await c.get("/state", headers={"X-Session-Id": session_id})
        data = state.json()
        assert data["active_module"]["current_story_node"] == "node-dungeon-entrance"
        visited = data["active_module"]["visited_nodes"]
        assert "node-village-arrival" in visited
        assert "node-tavern-gossip" in visited
        assert "node-dungeon-entrance" in visited

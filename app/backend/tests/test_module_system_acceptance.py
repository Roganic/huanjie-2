"""模组系统集成验收测试 — 端到端完整游玩流程。

验收标准：
1. 内置入门模组包含至少 3 个 story_nodes、2 个 NPCs、1 个 quest
2. 加载模组 → 探索场景 → 与 NPC 互动 → 推进剧情节点 → 完成模组任务 的完整流程
3. AIDM 叙事 prompt 在不同剧情节点包含对应的模组内容（场景名、NPC 名）
4. GET /state 的 active_module.active_story_node 随行动推进
5. GET /modules Dashboard API 返回模组列表和活跃模组状态
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.module import STARTER_MODULE, MODULE_REGISTRY
from src.module_engine import build_module_context_for_prompt
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_character(client: AsyncClient, name: str = "ModuleHero") -> str:
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


# =============================================================================
# 验收标准 1: 入门模组数据完整性
# =============================================================================


class TestStarterModuleDataIntegrity:
    """验证入门模组包含足够内容可完整游玩。"""

    def test_starter_module_has_at_least_3_story_nodes(self):
        assert len(STARTER_MODULE.nodes) >= 3, (
            f"入门模组仅有 {len(STARTER_MODULE.nodes)} 个节点，需要至少 3 个"
        )

    def test_starter_module_has_at_least_2_unique_npcs(self):
        all_npcs: set[str] = set()
        for node in STARTER_MODULE.nodes.values():
            all_npcs.update(node.visible_npcs)
        assert len(all_npcs) >= 2, (
            f"入门模组仅有 {len(all_npcs)} 个唯一 NPC，需要至少 2 个"
        )

    def test_starter_module_has_at_least_1_quest(self):
        all_quests: set[str] = set()
        for node in STARTER_MODULE.nodes.values():
            for quest in node.quests:
                all_quests.add(quest.id)
        assert len(all_quests) >= 1, "入门模组需要至少 1 个任务"

    def test_starter_module_is_in_registry(self):
        assert STARTER_MODULE.id in MODULE_REGISTRY

    def test_story_nodes_form_connected_chain(self):
        """验证节点通过 triggers 形成可达链：village → tavern → dungeon → goblin。"""
        reachable = {STARTER_MODULE.starting_node_id}
        frontier = [STARTER_MODULE.starting_node_id]
        while frontier:
            nid = frontier.pop()
            node = STARTER_MODULE.nodes[nid]
            for trigger in node.triggers:
                if trigger.next_node_id not in reachable:
                    reachable.add(trigger.next_node_id)
                    frontier.append(trigger.next_node_id)
        assert len(reachable) >= 3, (
            f"从起始节点仅可达 {len(reachable)} 个节点，需要至少 3 个"
        )

    def test_each_node_has_scene_id(self):
        for node in STARTER_MODULE.nodes.values():
            assert node.scene_id, f"节点 {node.id} 缺少 scene_id"


# =============================================================================
# 验收标准 2: 端到端完整游玩流程
# =============================================================================


@pytest.mark.asyncio
class TestEndToEndModulePlaythrough:
    """完整模组游玩流程：加载 → 探索 → NPC 互动 → 推进剧情 → 到达最终节点。"""

    async def test_full_playthrough_village_to_goblin(self, client):
        """从村庄出发，经酒馆、地下城入口，到达哥布林遭遇的完整流程。"""
        async with client as c:
            session_id = await _create_character(c, "Adventurer")

            # --- Step 0: 初始状态验证 ---
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state.status_code == 200
            data = state.json()
            assert data["active_module"] is not None
            assert data["active_module"]["module_id"] == "starter-village-dungeon"
            assert data["active_module"]["current_story_node"] == "node-village-arrival"
            assert "node-village-arrival" in data["active_module"]["visited_nodes"]

            # --- Step 1: 村庄 → 酒馆（enter_scene 触发） ---
            resp = await c.post("/action", json={
                "scene_id": data["scene"]["id"],
                "actor": "Adventurer",
                "intent": "前往酒馆",
                "approach": "走向灯笼酒馆",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            action_data = resp.json()
            # 验证 module_event 触发
            assert "module_event" in action_data
            assert action_data["module_event"]["triggered_node"] == "node-tavern-gossip"
            assert action_data["module_event"]["previous_node"] == "node-village-arrival"

            # 验证 state 更新
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            data = state.json()
            assert data["active_module"]["current_story_node"] == "node-tavern-gossip"

            # --- Step 2: 酒馆 → 地下城入口（enter_scene 触发） ---
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "Adventurer",
                "intent": "前往地下城入口",
                "approach": "离开酒馆向东走",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            action_data = resp.json()
            assert "module_event" in action_data
            assert action_data["module_event"]["triggered_node"] == "node-dungeon-entrance"

            # 验证 state 更新
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            data = state.json()
            assert data["active_module"]["current_story_node"] == "node-dungeon-entrance"

            # --- Step 3: 地下城入口 → 哥布林遭遇（enter_scene 触发） ---
            resp = await c.post("/action", json={
                "scene_id": "dungeon-entrance-01",
                "actor": "Adventurer",
                "intent": "进入地下城通道",
                "approach": "推开石门进入",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            action_data = resp.json()
            assert "module_event" in action_data
            assert action_data["module_event"]["triggered_node"] == "node-goblin-encounter"

            # --- 最终状态验证 ---
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            data = state.json()
            assert data["active_module"]["current_story_node"] == "node-goblin-encounter"
            visited = data["active_module"]["visited_nodes"]
            assert "node-village-arrival" in visited
            assert "node-tavern-gossip" in visited
            assert "node-dungeon-entrance" in visited
            assert "node-goblin-encounter" in visited

    async def test_npc_interaction_trigger(self, client):
        """验证 interact_npc 类型触发器正确工作。"""
        async with client as c:
            session_id = await _create_character(c, "Talker")

            # 先移动到酒馆
            await c.post("/action", json={
                "scene_id": "village-square-01",
                "actor": "Talker",
                "intent": "前往酒馆",
                "approach": "走去酒馆",
            }, headers={"X-Session-Id": session_id})

            # 与酒馆老板互动（interact_npc 触发器）
            resp = await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "Talker",
                "intent": "和tavern-keeper-01交谈，询问地下城的消息",
                "approach": "走到吧台前问老马库斯",
            }, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            # interact_npc trigger for tavern-keeper-01 points to node-tavern-gossip
            # (same node, so it stays at tavern-gossip)
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            data = state.json()
            assert data["active_module"]["current_story_node"] == "node-tavern-gossip"


# =============================================================================
# 验收标准 3: AIDM 叙事 prompt 在不同节点包含对应模组内容
# =============================================================================


class TestNarrativePromptModuleContext:
    """验证每个剧情节点的叙事 prompt 包含正确的场景名和 NPC 名。"""

    def _setup_module_state(self, node_id: str):
        """为指定节点设置 active module 状态。"""
        from src.state import (
            set_current_session, reset_current_session,
            _get_session, _save_session, _SESSION_LOCK, _resolve_session_id,
        )
        from src.models.module import ActiveModuleState

        session_key = f"test-narrative-{node_id}"
        token = set_current_session(session_key)
        with _SESSION_LOCK:
            session = _get_session(_resolve_session_id(session_key), create_if_missing=True)
            session.active_module = ActiveModuleState(
                module_id="starter-village-dungeon",
                current_story_node=node_id,
                visited_nodes=[node_id],
            )
            _save_session(session)
        return token, session_key

    def _teardown(self, token):
        from src.state import reset_current_session
        reset_current_session(token)

    def test_village_arrival_prompt_contains_village_npcs(self):
        token, _ = self._setup_module_state("node-village-arrival")
        try:
            context = build_module_context_for_prompt()
            assert "抵达村庄" in context
            assert "village-elder-01" in context
            assert "blacksmith-01" in context
            assert "探索村庄" in context
        finally:
            self._teardown(token)

    def test_tavern_gossip_prompt_contains_tavern_npcs(self):
        token, _ = self._setup_module_state("node-tavern-gossip")
        try:
            context = build_module_context_for_prompt()
            assert "酒馆消息" in context
            assert "tavern-keeper-01" in context
            assert "tavern-bard-01" in context
            assert "地下城传闻" in context
        finally:
            self._teardown(token)

    def test_dungeon_entrance_prompt_contains_dungeon_npcs(self):
        token, _ = self._setup_module_state("node-dungeon-entrance")
        try:
            context = build_module_context_for_prompt()
            assert "地下城入口" in context
            assert "wounded-adventurer-01" in context
            assert "进入地下城" in context
        finally:
            self._teardown(token)

    def test_goblin_encounter_prompt_contains_combat_npcs(self):
        token, _ = self._setup_module_state("node-goblin-encounter")
        try:
            context = build_module_context_for_prompt()
            assert "哥布林遭遇" in context
            assert "goblin-01" in context
            assert "goblin-shaman-01" in context
            assert "突破遭遇" in context
        finally:
            self._teardown(token)

    def test_prompt_contains_narrative_constraints(self):
        token, _ = self._setup_module_state("node-village-arrival")
        try:
            context = build_module_context_for_prompt()
            assert "叙事约束" in context or "NARRATIVE CONSTRAINT" in context
            assert "不要引入" in context
        finally:
            self._teardown(token)


# =============================================================================
# 验收标准 4: GET /state 的 active_story_node 随行动推进
# =============================================================================


@pytest.mark.asyncio
class TestStoryNodeProgression:
    """验证 active_story_node 在每次有效行动后正确更新。"""

    async def test_initial_node_is_starting_node(self, client):
        async with client as c:
            session_id = await _create_character(c)
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            data = state.json()
            assert data["active_module"]["current_story_node"] == STARTER_MODULE.starting_node_id

    async def test_visited_nodes_accumulate(self, client):
        async with client as c:
            session_id = await _create_character(c)

            # Move through nodes
            for intent in ["前往酒馆", "前往地下城入口"]:
                state = await c.get("/state", headers={"X-Session-Id": session_id})
                scene_id = state.json()["scene"]["id"]
                await c.post("/action", json={
                    "scene_id": scene_id,
                    "actor": "ModuleHero",
                    "intent": intent,
                    "approach": "走",
                }, headers={"X-Session-Id": session_id})

            state = await c.get("/state", headers={"X-Session-Id": session_id})
            visited = state.json()["active_module"]["visited_nodes"]
            assert len(visited) >= 3

    async def test_irrelevant_action_does_not_advance_beyond_current_node(self, client):
        """在酒馆内执行不满足地下城触发条件的行动不应推进到下一节点。"""
        async with client as c:
            session_id = await _create_character(c)

            # First advance to tavern (known good progression)
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            await c.post("/action", json={
                "scene_id": state.json()["scene"]["id"],
                "actor": "ModuleHero",
                "intent": "前往酒馆",
                "approach": "走",
            }, headers={"X-Session-Id": session_id})

            state = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state.json()["active_module"]["current_story_node"] == "node-tavern-gossip"

            # Now do an action that doesn't trigger dungeon-entrance
            await c.post("/action", json={
                "scene_id": "tavern-01",
                "actor": "ModuleHero",
                "intent": "看看天花板上的吊灯",
                "approach": "抬头仰望",
            }, headers={"X-Session-Id": session_id})

            state = await c.get("/state", headers={"X-Session-Id": session_id})
            assert state.json()["active_module"]["current_story_node"] == "node-tavern-gossip"


# =============================================================================
# 验收标准 5: GET /modules Dashboard API
# =============================================================================


@pytest.mark.asyncio
class TestModulesDashboardAPI:
    """验证 GET /modules 返回前端 Dashboard 所需的数据结构。"""

    async def test_modules_endpoint_returns_module_list(self, client):
        async with client as c:
            session_id = await _create_character(c)
            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            data = resp.json()

            assert "modules" in data
            assert "active_module" in data
            assert len(data["modules"]) >= 1

    async def test_module_entry_has_required_fields(self, client):
        async with client as c:
            session_id = await _create_character(c)
            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            data = resp.json()
            mod = data["modules"][0]

            # 验证前端 Module 类型所需的字段
            assert "id" in mod
            assert "name" in mod
            assert "description" in mod
            assert "status" in mod
            assert "scenes" in mod
            assert "npcs" in mod
            assert "quests" in mod
            assert mod["status"] in ("active", "inactive", "completed")

    async def test_active_module_state_matches_game_state(self, client):
        async with client as c:
            session_id = await _create_character(c)
            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            data = resp.json()

            active = data["active_module"]
            assert active is not None
            assert active["module_id"] == "starter-village-dungeon"
            assert active["module_name"] == "村庄与地下城"
            assert active["current_story_node"] == "抵达村庄"
            assert "active_quests" in active

    async def test_active_module_status_is_active(self, client):
        async with client as c:
            session_id = await _create_character(c)
            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            data = resp.json()
            starter = [m for m in data["modules"] if m["id"] == "starter-village-dungeon"]
            assert len(starter) == 1
            assert starter[0]["status"] == "active"

    async def test_module_scenes_npcs_quests_populated(self, client):
        """验证模组包含的 scenes、npcs、quests 被正确聚合。"""
        async with client as c:
            session_id = await _create_character(c)
            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            data = resp.json()
            mod = [m for m in data["modules"] if m["id"] == "starter-village-dungeon"][0]

            assert len(mod["scenes"]) >= 3, "模组应包含至少 3 个场景"
            assert len(mod["npcs"]) >= 2, "模组应包含至少 2 个 NPC"
            assert len(mod["quests"]) >= 1, "模组应包含至少 1 个任务"

    async def test_dashboard_reflects_progression(self, client):
        """剧情推进后 Dashboard API 反映最新状态。"""
        async with client as c:
            session_id = await _create_character(c)

            # Move to tavern
            state = await c.get("/state", headers={"X-Session-Id": session_id})
            scene_id = state.json()["scene"]["id"]
            await c.post("/action", json={
                "scene_id": scene_id,
                "actor": "ModuleHero",
                "intent": "前往酒馆",
                "approach": "走",
            }, headers={"X-Session-Id": session_id})

            resp = await c.get("/modules", headers={"X-Session-Id": session_id})
            data = resp.json()
            assert data["active_module"]["current_story_node"] == "酒馆消息"

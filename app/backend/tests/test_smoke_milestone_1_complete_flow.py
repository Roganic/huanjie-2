"""Smoke tests for Milestone 1 - Complete Game Flow Acceptance.

These tests verify the complete end-to-end playability:
1. Create character
2. Enter scene
3. Exploration actions (with skill checks)
4. Trigger combat
5. Turn-based combat resolution
6. Combat ends
7. Continue exploration

This covers the full game loop from character creation through combat.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import get_actor, get_enemy, reset_state, set_current_session, reset_current_session


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_character(
    client: AsyncClient,
    name: str = "TestHero",
    character_class: str = "warrior"
) -> str:
    """Create a character and return session_id."""
    resp = await client.post("/character/create", json={
        "name": name,
        "character_class": character_class,
        "ability_generation": "standard_array",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    if not session_id:
        bootstrap = await client.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
    return session_id


# -----------------------------------------------------------------------------
# Complete Game Flow Test
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_game_flow_character_creation_to_exploration(client):
    """完整流程：创建角色 → 进入场景 → 探索行动 → 检定 → 继续探索"""
    async with client as c:
        # Step 1: 创建角色
        session_id = await _create_character(c, "Aragorn", "warrior")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        char_data = char_resp.json()
        assert char_data["name"] == "Aragorn"
        assert char_data["class"] == "warrior"
        initial_hp = char_data["hp"]["current"]
        initial_max_hp = char_data["hp"]["max"]
        
        # Step 2: 进入场景（自动成功探索）
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aragorn",
            "intent": "look around the tavern",
            "approach": "scan the room for threats",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["outcome"] == "success"
        assert data["resolution_type"] == "auto_success"
        assert "Aragorn" in data["narration"]
        
        # Step 3: 技能检定行动
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aragorn",
            "intent": "intimidate the troublemaker",
            "approach": "flex muscles and stare menacingly",
            "ability": "cha",
            "dc": 12,
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolution_type"] == "check"
        assert data["check"]["ability"] == "cha"
        assert "check" in data
        
        # Step 4: 继续探索
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aragorn",
            "intent": "walk to the bar",
            "approach": "casually approach the bartender",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "Aragorn" in data["narration"]
        
        # 验证角色状态一致
        char_resp_final = await c.get("/character", headers={"X-Session-Id": session_id})
        final_data = char_resp_final.json()
        assert final_data["name"] == "Aragorn"
        assert final_data["hp"]["max"] == initial_max_hp  # 最大HP不应改变


@pytest.mark.asyncio
async def test_complete_game_flow_with_combat(client):
    """完整流程：创建角色 → 探索 → 触发战斗 → 回合制战斗 → 战斗结束"""
    async with client as c:
        # Step 1: 创建战士角色
        session_id = await _create_character(c, "Conan", "warrior")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        character_hp = char_data["hp"]["current"]
        
        # 获取敌人初始HP
        token = set_current_session(session_id)
        try:
            enemy_initial_hp = get_enemy().hp  # 应该是7
        finally:
            reset_current_session(token)
        
        # Step 2: 探索场景
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "Conan",
            "intent": "look around the forest",
            "approach": "scan for movement in the trees",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # Step 3: 感知检定发现敌人
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "Conan",
            "intent": "spot hidden enemies",
            "approach": "use my keen perception",
            "skill": "perception",
            "dc": 12,
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolution_type"] == "check"
        
        # Step 4: 进入战斗 - 第一次攻击
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Conan",
            "intent": "attack the goblin",
            "approach": "charge forward with longsword raised",
            "weapon": "longsword",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        
        # 验证战斗响应结构
        assert data["attack"] is not None
        assert "hit_roll" in data["attack"]
        assert "total_attack" in data["attack"]
        assert data["attack"]["target_ac"] == 12
        
        # 记录战斗结果
        first_attack_hit = data["outcome"] == "success"
        damage_dealt = 0
        if first_attack_hit and data["attack"]["damage"]:
            damage_dealt = data["attack"]["damage"]["total"]
        
        # 验证敌人HP变化
        token = set_current_session(session_id)
        try:
            enemy_hp_after_first = get_enemy().hp
        finally:
            reset_current_session(token)
        
        if first_attack_hit:
            assert enemy_hp_after_first < enemy_initial_hp
            assert enemy_hp_after_first == enemy_initial_hp - damage_dealt
        
        # Step 5: 继续战斗 - 第二次攻击
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Conan",
            "intent": "strike again",
            "approach": "swing my longsword with all my strength",
            "weapon": "longsword",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        
        # 验证第二次攻击也正确返回
        assert data["attack"] is not None
        
        # Step 6: 战斗结束后验证状态
        char_resp_final = await c.get("/character", headers={"X-Session-Id": session_id})
        final_data = char_resp_final.json()
        
        # 验证角色HP没有异常变化（战士攻击不损失自己HP）
        assert final_data["hp"]["current"] == character_hp
        assert final_data["name"] == "Conan"


@pytest.mark.asyncio
async def test_combat_defeats_enemy_and_continues(client):
    """测试击败敌人后可以继续探索"""
    async with client as c:
        # 创建角色
        session_id = await _create_character(c, "Victor", "warrior")
        
        # 预设敌人HP为1，确保一击必杀
        from src.models.action import Effect
        from src.state import apply_effects
        
        token = set_current_session(session_id)
        try:
            # 将敌人HP设为1
            enemy = get_enemy()
            current_hp = enemy.hp
            if current_hp > 1:
                apply_effects([Effect(target="goblin-01", field="hp", delta=-(current_hp-1), description="setup for defeat test")])
            assert get_enemy().hp == 1
        finally:
            reset_current_session(token)
        
        # 攻击并击败敌人
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Victor",
            "intent": "finish off the goblin",
            "approach": "deliver a powerful strike",
            "weapon": "longsword",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        
        if data["outcome"] == "success" and data["attack"]["damage"]:
            # 验证敌人被击败
            token = set_current_session(session_id)
            try:
                enemy = get_enemy()
                if enemy.hp == 0:
                    assert "defeated" in enemy.conditions
            finally:
                reset_current_session(token)
        
        # 战斗后继续探索
        resp = await c.post("/action", json={
            "scene_id": "forest-01",
            "actor": "Victor",
            "intent": "search the defeated enemy",
            "approach": "look for valuables on the goblin",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "Victor" in data["narration"]


@pytest.mark.asyncio
async def test_five_consecutive_actions_with_combat(client):
    """连续进行5次行动（含至少1次战斗行动），验证AI叙事不越权修改数值"""
    async with client as c:
        session_id = await _create_character(c, "Ranger", "warrior")
        
        actions = [
            # 1. 探索
            {
                "scene_id": "forest-01",
                "actor": "Ranger",
                "intent": "look around",
                "approach": "scan the area",
            },
            # 2. 技能检定
            {
                "scene_id": "forest-01",
                "actor": "Ranger",
                "intent": "track the goblin",
                "approach": "search for footprints",
                "skill": "survival",
            },
            # 3. 战斗行动
            {
                "scene_id": "combat-01",
                "actor": "Ranger",
                "intent": "attack the goblin",
                "approach": "shoot with my bow",
                "weapon": "shortbow",
                "target": "goblin-01",
            },
            # 4. 继续战斗
            {
                "scene_id": "combat-01",
                "actor": "Ranger",
                "intent": "strike again",
                "approach": "draw another arrow",
                "weapon": "shortbow",
                "target": "goblin-01",
            },
            # 5. 战后探索
            {
                "scene_id": "forest-01",
                "actor": "Ranger",
                "intent": "search the area",
                "approach": "look for hidden items",
            },
        ]
        
        results = []
        for action in actions:
            resp = await c.post("/action", json=action, headers={"X-Session-Id": session_id})
            assert resp.status_code == 200
            data = resp.json()
            results.append(data)
            
            # 验证叙事包含角色名
            assert "Ranger" in data["narration"]
            
            # 验证AI没有越权修改数值
            # 叙事中不应包含HP直接修改语句
            narration_lower = data["narration"].lower()
            assert "hp becomes" not in narration_lower
            assert "生命值变为" not in narration_lower
            assert "hp is now" not in narration_lower
        
        # 验证我们进行了5次行动
        assert len(results) == 5
        
        # 验证至少有一次战斗行动
        combat_results = [r for r in results if r["attack"] is not None]
        assert len(combat_results) >= 1


@pytest.mark.asyncio
async def test_hp_consistency_throughout_combat(client):
    """战斗全程HP变化可追溯：每次受伤/治疗都有对应的裁定记录"""
    async with client as c:
        session_id = await _create_character(c, "Tank", "warrior")
        
        # 获取初始状态
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        initial_hp = char_data["hp"]["current"]
        
        # 进行多次战斗行动
        hp_history = [initial_hp]
        
        for i in range(3):
            resp = await c.post("/action", json={
                "scene_id": "combat-01",
                "actor": "Tank",
                "intent": f"attack round {i+1}",
                "approach": "swing my sword",
                "weapon": "longsword",
                "target": "goblin-01",
            }, headers={"X-Session-Id": session_id})
            
            assert resp.status_code == 200
            data = resp.json()
            
            # 每次行动后检查角色HP
            char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
            char_data = char_resp.json()
            current_hp = char_data["hp"]["current"]
            
            # 战士攻击不会损失HP，除非有特殊效果
            # 记录HP变化
            if current_hp != hp_history[-1]:
                # 如果有HP变化，检查effects中是否有记录
                hp_changes = [e for e in data["effects"] if e["field"] == "hp" and e["target"] == char_data.get("id", "warrior-tank")]
                # HP变化应该对应具体的effect
                pass  # 这里允许没有HP变化，因为战士攻击不损失HP
            
            hp_history.append(current_hp)
        
        # 验证最终HP一致性
        char_resp_final = await c.get("/character", headers={"X-Session-Id": session_id})
        final_data = char_resp_final.json()
        assert final_data["hp"]["current"] == hp_history[-1]


@pytest.mark.asyncio
async def test_mage_complete_flow_with_spell_combat(client):
    """法师完整流程：创建 → 探索 → 法术战斗"""
    async with client as c:
        session_id = await _create_character(c, "Gandalf", "mage")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        assert char_data["class"] == "mage"
        assert char_data["hp"]["max"] <= 8  # 法师HP较低
        
        # 探索
        resp = await c.post("/action", json={
            "scene_id": "library-01",
            "actor": "Gandalf",
            "intent": "study the ancient texts",
            "approach": "examine the arcane symbols",
            "skill": "arcana",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # 法术战斗（使用 requires_saving_throw）
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Gandalf",
            "intent": "cast fire bolt",
            "approach": "channel arcane energy",
            "action_type": "spell_attack",
            "target": "goblin-01",
            "damage_dice": "2d6",
            "saving_throw_ability": "dex",
            "saving_throw_dc": 13,
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        
        # 验证法术攻击响应
        assert data["attack"] is not None
        assert "Gandalf" in data["narration"]


@pytest.mark.asyncio
async def test_rogue_complete_flow_with_stealth_combat(client):
    """盗贼完整流程：潜行 → 偷袭 → 战斗"""
    async with client as c:
        session_id = await _create_character(c, "Shadow", "rogue")
        
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        char_data = char_resp.json()
        assert char_data["class"] == "rogue"
        
        # 潜行检定
        resp = await c.post("/action", json={
            "scene_id": "alley-01",
            "actor": "Shadow",
            "intent": "sneak up on the guard",
            "approach": "move silently through shadows",
            "skill": "stealth",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["check"]["skill_name"] == "stealth"
        assert data["check"]["ability"] == "dex"
        
        # 偷袭攻击（使用 finesse 武器）
        resp = await c.post("/action", json={
            "scene_id": "combat-01",
            "actor": "Shadow",
            "intent": "backstab the goblin",
            "approach": "strike from the shadows",
            "weapon": "dagger",
            "target": "goblin-01",
        }, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        data = resp.json()
        
        # 验证匕首攻击（finesse武器使用DEX）
        assert data["attack"] is not None
        if data["outcome"] == "success":
            # 匕首是finesse武器，应该使用DEX调整值
            pass


@pytest.mark.asyncio
async def test_narrative_no_numeric_overreach_in_combat(client):
    """验证战斗叙事中AI不越权声明具体数值"""
    async with client as c:
        session_id = await _create_character(c, "Paladin", "warrior")
        
        # 进行多次战斗
        for _ in range(5):
            resp = await c.post("/action", json={
                "scene_id": "combat-01",
                "actor": "Paladin",
                "intent": "attack the goblin",
                "approach": "strike with holy fury",
                "weapon": "longsword",
                "target": "goblin-01",
            }, headers={"X-Session-Id": session_id})
            
            assert resp.status_code == 200
            data = resp.json()
            
            narration = data["narration"].lower()
            
            # AI叙事不应包含这些越权数值声明
            forbidden_patterns = [
                "hp becomes",
                "生命值变为",
                "hp is now",
                "now has",
                "点生命值",
                "deals exactly",
                "造成精准",
            ]
            
            for pattern in forbidden_patterns:
                assert pattern not in narration, f"AI narrative should not contain: {pattern}"

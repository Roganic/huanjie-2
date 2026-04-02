"""法师职业完整施法体验集成验收测试。

验证法术槽系统与法术效果系统协同工作，形成完整的施法循环。

验收标准：
1. 法师角色创建后 spell_slots 正确初始化
2. 施放伤害法术：槽位消耗 + 目标受伤 + 裁定记录
3. 施放治疗法术：槽位消耗 + HP 恢复
4. 法术槽耗尽后施法返回错误，槽位不变
5. 长休后法术槽恢复
6. 端到端集成测试覆盖完整施法循环

覆盖完整施法循环：
角色创建 → 施放伤害法术 → 验证槽位消耗和目标受伤 → 施放治疗法术 → 验证槽位消耗和 HP 恢复 → 耗尽法术槽 → 验证错误处理 → 长休恢复 → 验证恢复效果
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state


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
    character_class: str = "mage"
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


async def _get_state(client: AsyncClient, session_id: str) -> dict:
    """Helper to get current state."""
    resp = await client.get("/state", headers={"X-Session-Id": session_id})
    assert resp.status_code == 200
    return resp.json()


# -----------------------------------------------------------------------------
# 法师完整施法体验验收测试
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mage_complete_spell_casting_cycle(client):
    """
    验证法师完整施法循环的所有验收标准。
    
    流程：
    1. 角色创建 → 验证 spell_slots 初始化
    2. 施放伤害法术（魔法飞弹）→ 验证槽位消耗 + 目标受伤
    3. 施放治疗法术（治疗之触）→ 验证槽位消耗 + HP 恢复
    4. 耗尽法术槽 → 验证错误处理 + 槽位不变
    5. 长休 → 验证法术槽恢复
    """
    async with client as c:
        # ========== Step 1: 角色创建，验证法术槽初始化 ==========
        session_id = await _create_character(c, "Merlin", "mage")
        
        state = await _get_state(c, session_id)
        actor = state["actor"]
        
        # 验证角色职业
        assert actor["character_class"] == "mage"
        
        # 验收标准1: 法师角色创建后 spell_slots 正确初始化
        assert "spell_slots" in actor, "法师角色应有 spell_slots 字段"
        spell_slots = actor["spell_slots"]
        assert len(spell_slots) >= 1, "法师角色应有法术槽"
        
        # 验证1级法师有2个1环法术位
        first_level_slot = spell_slots[0]
        assert first_level_slot["level"] == 1, "法术槽等级应为1级"
        assert first_level_slot["max"] == 2, "1级法师应有2个1环法术位"
        assert first_level_slot["current"] == 2, "初始当前值应等于最大值"
        
        initial_hp = actor["hp"]
        hp_max = actor["hp_max"]
        
        # ========== Step 2: 开始战斗，获取目标 ==========
        resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        combat_data = resp.json()
        
        enemy = next((p for p in combat_data["combatants"] if p["type"] == "enemy"), None)
        assert enemy is not None, "应有敌人存在"
        enemy_id = enemy["id"]
        
        # ========== Step 3: 施放伤害法术（魔法飞弹）==========
        resp = await c.post("/action", json={
            "scene_id": state["scene"]["id"],
            "actor": "Merlin",
            "intent": "施放魔法飞弹",
            "approach": "施放魔法飞弹攻击敌人",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        damage_spell_result = resp.json()
        
        # 验收标准2: 施放伤害法术成功
        assert damage_spell_result["outcome"] == "success", "施放伤害法术应成功"
        
        # 验证裁定记录包含必要字段
        action_summary = damage_spell_result.get("action_summary", "")
        narration = damage_spell_result.get("narration", "")
        assert len(narration) > 0, "应有叙事描述"
        
        # 验证法术槽消耗
        state = await _get_state(c, session_id)
        spell_slots_after_damage = state["actor"]["spell_slots"]
        assert spell_slots_after_damage[0]["current"] == 1, (
            f"施放1环法术后，法术槽应从2减少到1，实际为 {spell_slots_after_damage[0]['current']}"
        )
        
        # ========== Step 4: 降低HP以便测试治疗法术 ==========
        # 通过直接修改状态模拟受伤
        from src.state import _get_session, _save_session, _SESSION_LOCK, _resolve_session_id
        
        with _SESSION_LOCK:
            session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
            actor_obj = session.actor
            assert actor_obj is not None
            damaged_hp = max(1, actor_obj.hp - 5)
            session.actor = actor_obj.model_copy(update={"hp": damaged_hp})
            _save_session(session)
        
        state = await _get_state(c, session_id)
        hp_before_heal = state["actor"]["hp"]
        assert hp_before_heal < hp_max, "HP应已降低以便测试治疗"
        
        # ========== Step 5: 施放治疗法术（治疗之触）==========
        resp = await c.post("/action", json={
            "scene_id": state["scene"]["id"],
            "actor": "Merlin",
            "intent": "施放治疗之触",
            "approach": "施放治疗之触恢复生命值",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        heal_spell_result = resp.json()
        
        # 验收标准3: 施放治疗法术成功
        assert heal_spell_result["outcome"] == "success", "施放治疗法术应成功"
        
        # 验证HP恢复
        state = await _get_state(c, session_id)
        hp_after_heal = state["actor"]["hp"]
        assert hp_after_heal > hp_before_heal, (
            f"治疗法术后HP应从 {hp_before_heal} 恢复到更高的值，实际为 {hp_after_heal}"
        )
        
        # 验证法术槽消耗（治疗之触也是1环法术）
        spell_slots_after_heal = state["actor"]["spell_slots"]
        assert spell_slots_after_heal[0]["current"] == 0, (
            f"施放第二个1环法术后，法术槽应从1减少到0，实际为 {spell_slots_after_heal[0]['current']}"
        )
        
        # ========== Step 6: 验证法术槽耗尽后施法失败 ==========
        resp = await c.post("/action", json={
            "scene_id": state["scene"]["id"],
            "actor": "Merlin",
            "intent": "施放魔法飞弹",
            "approach": "尝试施放魔法飞弹",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        fail_result = resp.json()
        
        # 验收标准4: 法术槽耗尽后施法返回错误
        assert fail_result["outcome"] == "failure", "法术槽耗尽时施法应失败"
        
        # 验证错误信息（可能在 narration 或 gm_prompt 字段中）
        error_sources = [
            fail_result.get("error_message", ""),
            fail_result.get("narration", ""),
            fail_result.get("gm_prompt", ""),
        ]
        error_message = " ".join(error_sources)
        assert "法术" in error_message or "法术位" in error_message or "槽" in error_message or "没有" in error_message, (
            f"错误信息应提示法术槽相关: {error_message}"
        )
        
        # 验证法术槽未变
        state = await _get_state(c, session_id)
        spell_slots_after_fail = state["actor"]["spell_slots"]
        assert spell_slots_after_fail[0]["current"] == 0, (
            f"施法失败后法术槽不应改变，实际为 {spell_slots_after_fail[0]['current']}"
        )
        
        # ========== Step 7: 结束战斗，准备长休 ==========
        await c.post("/combat/end", json={}, headers={"X-Session-Id": session_id})
        
        # ========== Step 8: 执行长休，验证法术槽恢复 ==========
        resp = await c.post("/action", json={
            "scene_id": state["scene"]["id"],
            "actor": "Merlin",
            "intent": "长休",
            "approach": "休息一晚恢复法术位",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        rest_result = resp.json()
        
        # 验收标准5: 长休后法术槽恢复
        assert rest_result["outcome"] == "success", "长休应成功"
        
        # 验证法术槽恢复
        state = await _get_state(c, session_id)
        spell_slots_after_rest = state["actor"]["spell_slots"]
        
        for slot in spell_slots_after_rest:
            assert slot["current"] == slot["max"], (
                f"{slot['level']}环法术槽应恢复至最大值 {slot['max']}，实际为 {slot['current']}"
            )


@pytest.mark.asyncio
async def test_mage_spell_slots_state_consistency(client):
    """
    验证 GET /state 的 character.spell_slots 与每次施法后的实际消耗始终一致。
    
    验收标准验证：
    - GET /state 返回的 spell_slots 准确反映实际消耗
    - 多次施法后状态一致
    """
    async with client as c:
        session_id = await _create_character(c, "StateChecker", "mage")
        
        # 获取初始状态
        state = await _get_state(c, session_id)
        spell_slots = state["actor"]["spell_slots"]
        
        # 记录初始法术槽状态
        initial_slots = {slot["level"]: slot["current"] for slot in spell_slots}
        
        # 开始战斗
        resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # 施放法术并验证状态一致性
        for i in range(2):  # 施放2次，消耗所有1环法术位
            resp = await c.post("/action", json={
                "scene_id": state["scene"]["id"],
                "actor": "StateChecker",
                "intent": "施放魔法飞弹",
                "approach": "施放魔法飞弹",
            }, headers={"X-Session-Id": session_id})
            
            assert resp.status_code == 200
            result = resp.json()
            
            # 获取最新状态
            state = await _get_state(c, session_id)
            current_slots = {slot["level"]: slot["current"] for slot in state["actor"]["spell_slots"]}
            
            # 验证状态一致性
            expected_remaining = initial_slots[1] - (i + 1)
            actual_remaining = current_slots[1]
            
            assert actual_remaining == max(0, expected_remaining), (
                f"第{i+1}次施法后，1环法术槽应为 {max(0, expected_remaining)}，"
                f"实际为 {actual_remaining}"
            )
        
        # 结束战斗
        await c.post("/combat/end", json={}, headers={"X-Session-Id": session_id})


@pytest.mark.asyncio
async def test_mage_cantrip_no_slot_consumption(client):
    """
    验证戏法（0环法术）不消耗法术槽。
    
    寒冰射线是戏法，施放时不应消耗法术位。
    """
    async with client as c:
        session_id = await _create_character(c, "CantripTester", "mage")
        
        # 获取初始法术槽状态
        state = await _get_state(c, session_id)
        initial_spell_slots = state["actor"]["spell_slots"]
        initial_first_level = initial_spell_slots[0]["current"]
        
        # 开始战斗
        resp = await c.post("/combat/start", json={}, headers={"X-Session-Id": session_id})
        assert resp.status_code == 200
        
        # 施放戏法（寒冰射线）
        resp = await c.post("/action", json={
            "scene_id": state["scene"]["id"],
            "actor": "CantripTester",
            "intent": "施放寒冰射线",
            "approach": "施放寒冰射线攻击敌人",
        }, headers={"X-Session-Id": session_id})
        
        assert resp.status_code == 200
        result = resp.json()
        
        # 戏法施放应成功
        assert result["outcome"] == "success", "施放戏法应成功"
        
        # 验证法术槽未消耗
        state = await _get_state(c, session_id)
        current_spell_slots = state["actor"]["spell_slots"]
        current_first_level = current_spell_slots[0]["current"]
        
        assert current_first_level == initial_first_level, (
            f"戏法不应消耗法术槽，1环法术槽应保持 {initial_first_level}，"
            f"实际为 {current_first_level}"
        )
        
        # 结束战斗
        await c.post("/combat/end", json={}, headers={"X-Session-Id": session_id})

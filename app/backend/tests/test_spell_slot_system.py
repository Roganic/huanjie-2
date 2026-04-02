"""法术槽与施法系统验收测试。

验证以下验收标准：
1. GET /state 返回 character.spell_slots 字段，法师角色包含各环法术槽的 current 和 max 值
2. POST /action 施放魔法飞弹后，GET /state 的 spell_slots[0].current 减少 1
3. 法术槽为 0 时施法，POST /action 返回错误提示，spell_slots 不变
4. POST /action 执行长休后，GET /state 的 spell_slots 全部恢复至 max 值
5. 法术裁定响应包含 spell_name、spell_level、slot_used、damage_roll、damage_total 字段（单元测试验证）
"""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 验收标准5：单元测试验证法术裁定响应字段
# ---------------------------------------------------------------------------

class TestSpellCastResult:
    """验证 game/action_handler.py 的 handle_spell_cast 返回字段。"""

    def _create_mock_actor(self):
        """创建一个测试用的法师 Actor。"""
        from src.models.state import Actor, AbilityScores, CharacterClass, SpellSlot

        return Actor(
            id="mage-test-001",
            name="测试法师",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 8,
                "dex": 13,
                "con": 12,
                "int": 15,
                "wis": 14,
                "cha": 10,
            }),
            proficiency_bonus=2,
            level=1,
            hp=6,
            hp_max=6,
            ac=12,
            spell_slots=[SpellSlot(level=1, max=2, current=2)],
        )

    def test_magic_missile_result_has_required_fields(self):
        """魔法飞弹施放结果包含所有必需字段。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-001")

        assert result is not None, "施放魔法飞弹应返回结果"
        assert "spell_name" in result, "结果应包含 spell_name 字段"
        assert "spell_level" in result, "结果应包含 spell_level 字段"
        assert "effect_type" in result, "结果应包含 effect_type 字段"
        assert "slot_used" in result, "结果应包含 slot_used 字段"
        assert "damage_roll" in result, "结果应包含 damage_roll 字段"
        assert "damage_total" in result, "结果应包含 damage_total 字段"

    def test_magic_missile_spell_name_is_correct(self):
        """魔法飞弹的 spell_name 字段值正确。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-002")

        assert result is not None
        assert result["spell_name"] == "魔法飞弹", f"spell_name 应为 '魔法飞弹'，实际为 {result['spell_name']!r}"

    def test_magic_missile_spell_level_is_1(self):
        """魔法飞弹的 spell_level 字段值为 1。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-003")

        assert result is not None
        assert result["spell_level"] == 1, f"spell_level 应为 1，实际为 {result['spell_level']}"

    def test_magic_missile_slot_used_is_1(self):
        """魔法飞弹消耗 1 环法术槽。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-004")

        assert result is not None
        assert result["slot_used"] == 1, f"slot_used 应为 1，实际为 {result['slot_used']}"

    def test_magic_missile_damage_roll_is_list(self):
        """魔法飞弹的 damage_roll 是列表。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-005")

        assert result is not None
        assert isinstance(result["damage_roll"], list), f"damage_roll 应为列表，实际为 {type(result['damage_roll'])}"
        assert len(result["damage_roll"]) > 0, "魔法飞弹应有伤害骰子结果"

    def test_magic_missile_damage_total_is_positive(self):
        """魔法飞弹的 damage_total 是正整数。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-006")

        assert result is not None
        assert isinstance(result["damage_total"], int), f"damage_total 应为整数，实际为 {type(result['damage_total'])}"
        assert result["damage_total"] > 0, f"魔法飞弹伤害应大于0，实际为 {result['damage_total']}"

    def test_magic_missile_success_is_true(self):
        """法术槽充足时施放魔法飞弹成功。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-007")

        assert result is not None
        assert result["success"] is True, f"施放成功时 success 应为 True，实际为 {result['success']}"

    def test_no_spell_slots_returns_failure(self):
        """法术槽耗尽时施放返回失败。"""
        from src.game.action_handler import handle_spell_cast
        from src.models.state import Actor, AbilityScores, CharacterClass, SpellSlot

        actor = Actor(
            id="mage-empty-001",
            name="空槽法师",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 8, "dex": 13, "con": 12,
                "int": 15, "wis": 14, "cha": 10,
            }),
            proficiency_bonus=2,
            level=1,
            hp=6,
            hp_max=6,
            ac=12,
            spell_slots=[SpellSlot(level=1, max=2, current=0)],  # 法术槽已耗尽
        )

        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-unit-008")

        assert result is not None
        assert result["success"] is False, "法术槽耗尽时施放应失败"
        assert result["error_message"] is not None, "失败时应有错误信息"
        assert result["slot_used"] == 0, "失败时不应消耗法术槽"

    def test_cure_wounds_effect_type_is_heal(self):
        """治疗法术的 effect_type 是 'heal'。"""
        from src.game.action_handler import handle_spell_cast

        actor = self._create_mock_actor()
        result = handle_spell_cast("施放治疗之触", actor, session_id="test-unit-009")

        assert result is not None, "施放治疗之触应返回结果"
        assert "effect_type" in result, "结果应包含 effect_type 字段"
        assert result["effect_type"] == "heal", f"治疗法术的 effect_type 应为 'heal'，实际为 {result['effect_type']}"
        assert result["damage_total"] < 0, "治疗法术的 damage_total 应为负值（表示恢复）"


# ---------------------------------------------------------------------------
# 规则模块单元测试
# ---------------------------------------------------------------------------

class TestSpellSlotsRules:
    """验证 rules/spells.py 和 rules/character.py 的法术槽规则。"""

    def test_wizard_level1_has_2_first_level_slots(self):
        """1级法师有2个1环法术槽。"""
        from src.rules.spells import get_wizard_spell_slots

        slots = get_wizard_spell_slots(1)
        assert slots.get(1) == 2, f"1级法师应有2个1环法术槽，实际为 {slots.get(1)}"

    def test_wizard_level1_has_no_higher_slots(self):
        """1级法师没有2环以上法术槽。"""
        from src.rules.spells import get_wizard_spell_slots

        slots = get_wizard_spell_slots(1)
        assert slots.get(2) is None, "1级法师不应有2环法术槽"
        assert slots.get(3) is None, "1级法师不应有3环法术槽"

    def test_wizard_level5_has_third_level_slots(self):
        """5级法师有3环法术槽。"""
        from src.rules.spells import get_wizard_spell_slots

        slots = get_wizard_spell_slots(5)
        assert slots.get(3) == 2, f"5级法师应有2个3环法术槽，实际为 {slots.get(3)}"

    def test_init_spell_slots_for_mage(self):
        """法师角色初始化法术槽正确。"""
        from src.rules.character import init_spell_slots

        slots = init_spell_slots("mage", 1)
        assert len(slots) == 1, f"1级法师应有1种法术槽，实际有 {len(slots)}"
        assert slots[0]["level"] == 1
        assert slots[0]["max"] == 2
        assert slots[0]["current"] == 2

    def test_init_spell_slots_for_warrior_is_empty(self):
        """战士角色没有法术槽。"""
        from src.rules.character import init_spell_slots

        slots = init_spell_slots("warrior", 1)
        assert slots == [], f"战士不应有法术槽，实际为 {slots}"

    def test_fireball_is_level3(self):
        """火球术是3环法术。"""
        from src.rules.spells import register_extended_spells
        from src.spells.spell_registry import get_spell

        register_extended_spells()
        spell = get_spell("火球术")
        assert spell is not None, "火球术应存在"
        assert spell.level == 3, f"火球术应为3环，实际为 {spell.level}环"

    def test_cure_wounds_cleric_only(self):
        """治疗术仅牧师可用。"""
        from src.rules.spells import register_extended_spells
        from src.spells.spell_registry import get_spell

        register_extended_spells()
        spell = get_spell("治疗术")
        assert spell is not None, "治疗术应存在"
        assert "cleric" in spell.available_to, "治疗术应只有牧师可用"
        assert "mage" not in spell.available_to, "法师不应能使用治疗术"


# ---------------------------------------------------------------------------
# 集成测试：通过 HTTP API 验证所有验收标准
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """创建 FastAPI 测试客户端。"""
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


@pytest.fixture
def mage_session(client):
    """创建一个法师角色并返回 session_id。"""
    resp = client.post("/character/create", json={
        "name": "测试法师",
        "character_class": "mage",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    assert session_id is not None
    return session_id


class TestSpellSlotAcceptanceCriteria:
    """验收标准集成测试。"""

    def test_ac1_get_state_returns_spell_slots(self, client, mage_session):
        """验收标准1: GET /state 返回法师的 spell_slots 字段。"""
        resp = client.get("/state", headers={"X-Session-Id": mage_session})
        assert resp.status_code == 200

        actor = resp.json().get("actor", {})
        spell_slots = actor.get("spell_slots", [])

        assert len(spell_slots) > 0, "法师角色应有法术槽"
        slot = spell_slots[0]
        assert "level" in slot, "法术槽应包含 level 字段"
        assert "current" in slot, "法术槽应包含 current 字段"
        assert "max" in slot, "法术槽应包含 max 字段"
        assert slot["level"] == 1
        assert slot["max"] == 2
        assert slot["current"] == 2

    def test_ac2_cast_magic_missile_decreases_slot(self, client, mage_session):
        """验收标准2: 施放魔法飞弹后 spell_slots[0].current 减少 1。"""
        # 施放魔法飞弹
        resp = client.post("/action", json={
            "scene_id": "combat-01",
            "actor": "测试法师",
            "intent": "施放魔法飞弹",
            "approach": "向敌人施放魔法飞弹",
        }, headers={"X-Session-Id": mage_session})
        assert resp.status_code == 200
        assert resp.json().get("outcome") == "success"

        # 检查法术槽减少
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session})
        spell_slots = state_resp.json().get("actor", {}).get("spell_slots", [])
        assert spell_slots[0]["current"] == 1, f"施放后1级法术槽应为1，实际为 {spell_slots[0]['current']}"

    def test_ac3_cast_with_empty_slots_fails(self, client, mage_session):
        """验收标准3: 法术槽为0时施法返回错误，spell_slots 不变。"""
        # 消耗所有法术槽
        for _ in range(2):
            client.post("/action", json={
                "scene_id": "combat-01",
                "actor": "测试法师",
                "intent": "施放魔法飞弹",
                "approach": "向敌人施放魔法飞弹",
            }, headers={"X-Session-Id": mage_session})

        # 确认法术槽已耗尽
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session})
        spell_slots = state_resp.json().get("actor", {}).get("spell_slots", [])
        assert spell_slots[0]["current"] == 0, "法术槽应已耗尽"

        # 尝试施法（应失败）
        fail_resp = client.post("/action", json={
            "scene_id": "combat-01",
            "actor": "测试法师",
            "intent": "施放魔法飞弹",
            "approach": "向敌人施放魔法飞弹",
        }, headers={"X-Session-Id": mage_session})
        assert fail_resp.status_code == 200
        assert fail_resp.json().get("outcome") == "failure", "法术槽耗尽时施法应失败"

        # 确认法术槽未变
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session})
        spell_slots_after = state_resp.json().get("actor", {}).get("spell_slots", [])
        assert spell_slots_after[0]["current"] == 0, "失败后法术槽不应改变"

    def test_ac4_long_rest_restores_spell_slots(self, client, mage_session):
        """验收标准4: 长休后 spell_slots 全部恢复至 max 值。"""
        # 消耗一个法术槽
        client.post("/action", json={
            "scene_id": "combat-01",
            "actor": "测试法师",
            "intent": "施放魔法飞弹",
            "approach": "向敌人施放魔法飞弹",
        }, headers={"X-Session-Id": mage_session})

        # 确认法术槽减少
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session})
        spell_slots = state_resp.json().get("actor", {}).get("spell_slots", [])
        assert spell_slots[0]["current"] == 1

        # 执行长休
        rest_resp = client.post("/action", json={
            "scene_id": "exploration-01",
            "actor": "测试法师",
            "intent": "长休",
            "approach": "休息一晚",
        }, headers={"X-Session-Id": mage_session})
        assert rest_resp.status_code == 200
        assert rest_resp.json().get("outcome") == "success"

        # 确认法术槽恢复
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session})
        spell_slots = state_resp.json().get("actor", {}).get("spell_slots", [])
        for slot in spell_slots:
            assert slot["current"] == slot["max"], (
                f"{slot['level']}环法术槽应恢复至最大值 {slot['max']}，实际为 {slot['current']}"
            )

    def test_ac5_spell_cast_result_has_required_fields(self):
        """验收标准5: 法术裁定响应包含 spell_name、spell_level、effect_type、slot_used、damage_roll、damage_total 字段。"""
        from src.game.action_handler import handle_spell_cast
        from src.models.state import Actor, AbilityScores, CharacterClass, SpellSlot

        actor = Actor(
            id="mage-ac5-001",
            name="验收法师",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 8, "dex": 13, "con": 12,
                "int": 15, "wis": 14, "cha": 10,
            }),
            proficiency_bonus=2,
            level=1,
            hp=6,
            hp_max=6,
            ac=12,
            spell_slots=[SpellSlot(level=1, max=2, current=2)],
        )

        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-ac5-001")

        assert result is not None, "施放结果不应为 None"
        assert "spell_name" in result, "结果应包含 spell_name 字段"
        assert "spell_level" in result, "结果应包含 spell_level 字段"
        assert "effect_type" in result, "结果应包含 effect_type 字段"
        assert "slot_used" in result, "结果应包含 slot_used 字段"
        assert "damage_roll" in result, "结果应包含 damage_roll 字段"
        assert "damage_total" in result, "结果应包含 damage_total 字段"

        # 验证字段值的合理性
        assert result["spell_name"] == "魔法飞弹"
        assert result["spell_level"] == 1
        assert result["effect_type"] == "damage", f"伤害法术的 effect_type 应为 'damage'，实际为 {result['effect_type']}"
        assert result["slot_used"] == 1
        assert isinstance(result["damage_roll"], list)
        assert isinstance(result["damage_total"], int)
        assert result["damage_total"] > 0

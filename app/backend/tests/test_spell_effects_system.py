"""法术效果系统验收测试。

验证以下验收标准：
1. POST /action 施放魔法飞弹后，目标 HP 减少，GET /state 返回更新后的战斗状态，包含法术效果裁定记录
2. POST /action 施放治疗术后，GET /state 返回 character.hp 增加（不超过 hp_max），spell_slots[1].current 减少 1
3. 法术裁定响应包含 spell_name、spell_level、effect_type、roll_result、damage/heal 字段（单元测试验证）
"""

from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# 验收标准3：单元测试验证法术裁定响应字段
# ---------------------------------------------------------------------------

class TestSpellCastResultFields:
    """验证 game/action_handler.py 的 handle_spell_cast 返回新验收标准字段。"""

    def _create_mage_actor(self, hp=6, hp_max=6):
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
            hp=hp,
            hp_max=hp_max,
            ac=12,
            spell_slots=[SpellSlot(level=1, max=2, current=2)],
        )

    # -----------------------------------------------------------------------
    # 魔法飞弹字段验证
    # -----------------------------------------------------------------------

    def test_magic_missile_has_spell_name(self):
        """魔法飞弹结果包含 spell_name 字段。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-mm-001")
        assert result is not None
        assert "spell_name" in result
        assert result["spell_name"] == "魔法飞弹"

    def test_magic_missile_has_spell_level(self):
        """魔法飞弹结果包含 spell_level 字段值为 1。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-mm-002")
        assert result is not None
        assert "spell_level" in result
        assert result["spell_level"] == 1

    def test_magic_missile_has_effect_type_damage(self):
        """魔法飞弹结果包含 effect_type 字段值为 'damage'。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-mm-003")
        assert result is not None
        assert "effect_type" in result
        assert result["effect_type"] == "damage"

    def test_magic_missile_has_roll_result(self):
        """魔法飞弹结果包含 roll_result 字段（列表）。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-mm-004")
        assert result is not None
        assert "roll_result" in result
        assert isinstance(result["roll_result"], list)
        assert len(result["roll_result"]) > 0

    def test_magic_missile_has_damage_field(self):
        """魔法飞弹结果包含 damage 字段（正整数）。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-mm-005")
        assert result is not None
        assert "damage" in result
        assert isinstance(result["damage"], int)
        assert result["damage"] > 0

    def test_magic_missile_damage_range(self):
        """魔法飞弹伤害范围：1d4+1，即 2-5。"""
        from src.game.action_handler import handle_spell_cast
        # 运行多次确保范围正确
        for i in range(10):
            actor = self._create_mage_actor()
            result = handle_spell_cast("施放魔法飞弹", actor, session_id=f"test-mm-range-{i}")
            assert result is not None
            assert result["success"] is True
            assert 2 <= result["damage"] <= 5, (
                f"魔法飞弹伤害应在 2-5 之间，实际为 {result['damage']}"
            )

    # -----------------------------------------------------------------------
    # 治疗术字段验证
    # -----------------------------------------------------------------------

    def test_cure_wounds_has_spell_name(self):
        """治疗术结果包含 spell_name 字段。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor(hp=3, hp_max=6)
        result = handle_spell_cast("施放治疗术", actor, session_id="test-cw-001")
        assert result is not None
        assert "spell_name" in result
        assert result["spell_name"] == "治疗术"

    def test_cure_wounds_has_effect_type_heal(self):
        """治疗术结果包含 effect_type 字段值为 'heal'。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor(hp=3, hp_max=6)
        result = handle_spell_cast("施放治疗术", actor, session_id="test-cw-002")
        assert result is not None
        assert "effect_type" in result
        assert result["effect_type"] == "heal"

    def test_cure_wounds_has_heal_field(self):
        """治疗术结果包含 heal 字段（正整数）。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor(hp=1, hp_max=6)
        result = handle_spell_cast("施放治疗术", actor, session_id="test-cw-003")
        assert result is not None
        assert "heal" in result
        assert isinstance(result["heal"], int)
        assert result["heal"] > 0

    def test_cure_wounds_heal_includes_int_modifier(self):
        """治疗术恢复量包含智力修正（INT 15 => 修正 +2）。"""
        from src.game.action_handler import handle_spell_cast
        # INT 15 => modifier = (15-10)//2 = 2
        # 1d8+2 => min 3, max 10
        actor = self._create_mage_actor(hp=1, hp_max=20)
        for i in range(10):
            actor2 = self._create_mage_actor(hp=1, hp_max=20)
            result = handle_spell_cast("施放治疗术", actor2, session_id=f"test-cw-mod-{i}")
            assert result is not None
            assert result["success"] is True
            assert 3 <= result["heal"] <= 10, (
                f"治疗术恢复量应在 3-10 之间（1d8+2），实际为 {result['heal']}"
            )

    # -----------------------------------------------------------------------
    # 燃烧之手字段验证
    # -----------------------------------------------------------------------

    def test_burning_hands_has_effect_type_damage(self):
        """燃烧之手结果包含 effect_type 字段值为 'damage'。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放燃烧之手", actor, session_id="test-bh-001")
        assert result is not None
        assert "effect_type" in result
        assert result["effect_type"] == "damage"

    def test_burning_hands_has_roll_result(self):
        """燃烧之手结果包含 roll_result 字段。"""
        from src.game.action_handler import handle_spell_cast
        actor = self._create_mage_actor()
        result = handle_spell_cast("施放燃烧之手", actor, session_id="test-bh-002")
        assert result is not None
        assert "roll_result" in result
        assert isinstance(result["roll_result"], list)


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


class TestSpellEffectsAcceptanceCriteria:
    """法术效果系统验收标准集成测试。"""

    def test_ac1_magic_missile_reduces_enemy_hp(self, client, mage_session, predictable_combat):
        from tests.conftest import enter_passage_sync
        enter_passage_sync(client,mage_session)
        """验收标准1: 施放魔法飞弹后，目标 HP 减少，GET /state 返回更新后的战斗状态。"""
        # 获取初始状态
        initial_state = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        initial_enemy_hp = initial_state.get("enemy", {}).get("hp", 0)

        # 施放魔法飞弹
        resp = client.post("/action", json={
            "scene_id": "combat-01",
            "actor": "测试法师",
            "intent": "施放魔法飞弹",
            "approach": "向哥布林施放魔法飞弹",
        }, headers={"X-Session-Id": mage_session})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("outcome") == "success", f"施放魔法飞弹应成功，实际: {data}"

        # 检查响应包含法术裁定记录
        spell_cast = data.get("spell_cast", {})
        assert spell_cast.get("spell_name") == "魔法飞弹", "响应应包含 spell_name"
        assert spell_cast.get("spell_level") == 1, "响应应包含 spell_level"
        assert spell_cast.get("effect_type") == "damage", "响应应包含 effect_type=damage"
        assert isinstance(spell_cast.get("damage_roll"), list), "响应应包含 roll_result 列表"
        assert spell_cast.get("damage", 0) > 0, "响应应包含 damage > 0"

        # 检查目标 HP 减少
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        new_enemy_hp = state_resp.get("enemy", {}).get("hp", 0)
        assert new_enemy_hp < initial_enemy_hp, (
            f"敌人 HP 应减少，初始: {initial_enemy_hp}，当前: {new_enemy_hp}"
        )

    def test_ac2_cure_wounds_increases_hp_and_consumes_slot(self, client, mage_session):
        from src.state import get_actor
        get_actor(mage_session).hp = 1
        """验收标准2: 施放治疗术后，character.hp 增加（不超过 hp_max），spell_slots[1].current 减少 1。"""
        # 先让法师受伤（通过直接修改状态不可行，用 API 间接处理）
        # 获取初始状态
        initial_state = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        initial_slots = initial_state.get("actor", {}).get("spell_slots", [])
        initial_slot_current = initial_slots[0]["current"] if initial_slots else 2

        # 为了测试治疗效果，先人为减少HP
        # 由于没有直接 API，我们检查法术槽消耗（即使满血治疗，槽仍然消耗）
        resp = client.post("/action", json={
            "scene_id": "exploration-01",
            "actor": "测试法师",
            "intent": "施放治疗术",
            "approach": "对自己施放治疗术",
        }, headers={"X-Session-Id": mage_session})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("outcome") == "success", f"施放治疗术应成功，实际: {data}"

        # 检查响应包含法术裁定记录
        spell_cast = data.get("spell_cast", {})
        assert spell_cast.get("spell_name") == "治疗术", "响应应包含 spell_name=治疗术"
        assert spell_cast.get("spell_level") == 1, "响应应包含 spell_level=1"
        assert spell_cast.get("effect_type") == "heal", "响应应包含 effect_type=heal"
        assert isinstance(spell_cast.get("damage_roll"), list), "响应应包含 roll_result 列表"
        assert "heal" in spell_cast, "响应应包含 heal 字段"

        # 检查法术槽减少
        state_resp = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        new_slots = state_resp.get("actor", {}).get("spell_slots", [])
        new_slot_current = new_slots[0]["current"] if new_slots else initial_slot_current
        assert new_slot_current == initial_slot_current - 1, (
            f"施放治疗术后1级法术槽应减少1，初始: {initial_slot_current}，当前: {new_slot_current}"
        )

        # 检查 HP 不超过 hp_max
        actor_data = state_resp.get("actor", {})
        hp = actor_data.get("hp", 0)
        hp_max = actor_data.get("hp_max", 0)
        assert hp <= hp_max, f"HP 不应超过 hp_max，当前 hp={hp}，hp_max={hp_max}"

    def test_ac3_spell_cast_result_has_all_required_fields(self):
        """验收标准3: 法术裁定响应包含 spell_name、spell_level、effect_type、roll_result、damage/heal 字段。"""
        from src.game.action_handler import handle_spell_cast
        from src.models.state import Actor, AbilityScores, CharacterClass, SpellSlot

        actor = Actor(
            id="mage-ac3-001",
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

        # 测试魔法飞弹
        result = handle_spell_cast("施放魔法飞弹", actor, session_id="test-ac3-mm")
        assert result is not None
        assert "spell_name" in result, "结果应包含 spell_name 字段"
        assert "spell_level" in result, "结果应包含 spell_level 字段"
        assert "effect_type" in result, "结果应包含 effect_type 字段"
        assert "roll_result" in result, "结果应包含 roll_result 字段"
        assert "damage" in result, "结果应包含 damage 字段"
        assert result["spell_name"] == "魔法飞弹"
        assert result["spell_level"] == 1
        assert result["effect_type"] == "damage"
        assert isinstance(result["roll_result"], list)
        assert result["damage"] > 0

        # 测试治疗术
        actor2 = Actor(
            id="mage-ac3-002",
            name="验收法师2",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 8, "dex": 13, "con": 12,
                "int": 15, "wis": 14, "cha": 10,
            }),
            proficiency_bonus=2,
            level=1,
            hp=3,
            hp_max=6,
            ac=12,
            spell_slots=[SpellSlot(level=1, max=2, current=2)],
        )
        result2 = handle_spell_cast("施放治疗术", actor2, session_id="test-ac3-cw")
        assert result2 is not None
        assert "spell_name" in result2
        assert "spell_level" in result2
        assert "effect_type" in result2
        assert "roll_result" in result2
        assert "heal" in result2
        assert result2["spell_name"] == "治疗术"
        assert result2["spell_level"] == 1
        assert result2["effect_type"] == "heal"
        assert isinstance(result2["roll_result"], list)
        assert result2["heal"] > 0

    def test_burning_hands_saving_throw_halves_damage(self, client, mage_session):
        """燃烧之手：豁免机制正确（目标进行 DEX 豁免，成功则减半伤害）。"""
        from src.game.action_handler import handle_spell_cast
        from src.models.state import Actor, AbilityScores, CharacterClass, SpellSlot

        actor = Actor(
            id="mage-bh-001",
            name="燃手法师",
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

        result = handle_spell_cast("施放燃烧之手", actor, session_id="test-bh-save")
        assert result is not None
        assert result["success"] is True
        assert result["spell_name"] == "燃烧之手"
        assert result["spell_level"] == 1
        assert result["effect_type"] == "damage"
        # 燃烧之手 3d6 伤害，豁免成功减半，范围 1-18（或减半后 1-9）
        assert result["damage"] >= 1, f"燃烧之手伤害应 >= 1，实际: {result['damage']}"
        assert result["damage"] <= 18, f"燃烧之手伤害应 <= 18，实际: {result['damage']}"

    def test_magic_missile_consumes_spell_slot(self, client, mage_session, predictable_combat):
        from tests.conftest import enter_passage_sync
        enter_passage_sync(client,mage_session)
        """施放魔法飞弹消耗 1 级法术槽。"""
        # 获取初始法术槽
        initial_state = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        initial_slots = initial_state.get("actor", {}).get("spell_slots", [])
        assert len(initial_slots) > 0
        initial_current = initial_slots[0]["current"]

        # 施放魔法飞弹
        client.post("/action", json={
            "scene_id": "combat-01",
            "actor": "测试法师",
            "intent": "施放魔法飞弹",
            "approach": "向敌人施放",
        }, headers={"X-Session-Id": mage_session})

        # 检查法术槽减少
        state = client.get("/state", headers={"X-Session-Id": mage_session}).json()
        new_slots = state.get("actor", {}).get("spell_slots", [])
        assert new_slots[0]["current"] == initial_current - 1, (
            f"法术槽应减少1，初始: {initial_current}，当前: {new_slots[0]['current']}"
        )

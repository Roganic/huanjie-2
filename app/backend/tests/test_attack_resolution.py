"""Deterministic rule boundaries; clients cannot dictate AC or damage."""
import pytest
from src import state
from src.combat import resolve_attack_with_equipment
from src.models.state import InventoryItem
from tests.conftest import create_default_actor, create_session_and_character, enter_passage


@pytest.mark.parametrize("roll,ac,hit", [(1,1,False),(20,99,True),(10,14,True),(10,15,False)])
def test_hit_miss_and_natural_rolls(monkeypatch, roll, ac, hit):
    create_default_actor()
    actor = state.get_actor()
    monkeypatch.setattr("random.randint", lambda a,b: roll if b == 20 else 4)
    result = resolve_attack_with_equipment(actor,ac)
    assert result["hit"] is hit
    assert result["total_attack"] == roll + actor.abilities.modifier("str") + actor.proficiency_bonus
    assert result["damage"] == (4 + actor.abilities.modifier("str") if hit else 0)
    assert result["damage_rolls"] == ([4] if hit else [])


@pytest.mark.parametrize("advantage,expected", [(True,18),(False,2)])
def test_advantage_uses_two_rolls(monkeypatch, advantage, expected):
    create_default_actor()
    rolls = iter([2,18,4])
    monkeypatch.setattr("random.randint", lambda a,b: next(rolls))
    result = resolve_attack_with_equipment(state.get_actor(),10,advantage=advantage)
    assert result["attack_roll"] == expected


@pytest.mark.parametrize("ability", ["str","dex"])
def test_equipped_weapon_ability_and_signed_damage_bonus(monkeypatch, ability):
    create_default_actor()
    actor = state.get_actor()
    actor.equipped.weapon = InventoryItem(id="module-blade", name="模组剑", type="weapon", damage_dice="1d6+2",attack_ability=ability)
    monkeypatch.setattr("random.randint", lambda a,b: b)
    result = resolve_attack_with_equipment(actor,10)
    assert result["total_attack"] == 20 + actor.abilities.modifier(ability) + actor.proficiency_bonus
    assert result["damage"] == 6 + 2 + actor.abilities.modifier(ability)


@pytest.mark.asyncio
async def test_offscene_attack_cannot_create_target(client):
    sid = await create_session_and_character(client)
    before = state.get_actor(sid).model_dump()
    response = await client.post("/action",headers={"X-Session-Id":sid},json=dict(scene_id="combat-01",actor="fake",intent="attack the goblin",approach="",target="goblin-01",weapon="longsword",dc=1,damage_dice="99d99"))
    assert response.status_code == 400
    assert state.get_actor(sid).model_dump() == before
    assert state.get_scene(sid).id == "tavern-01"


@pytest.mark.asyncio
async def test_text_attack_ignores_client_damage_and_dc(client, predictable_combat):
    sid = await create_session_and_character(client)
    battle = await enter_passage(client,sid)
    enemy = next(p for p in battle["participants"] if not p["is_player"])
    response = await client.post("/action",headers={"X-Session-Id":sid},json=dict(scene_id="invented",actor="fake",intent="攻击",approach="",target=enemy["id"],dc=99,damage_dice="99d99"))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["hit"] is True and result["damage"] == 10
    participant = next(p for p in result["combat_state"]["participants"] if p["id"] == enemy["id"])
    assert participant["hp"] == max(0,enemy["hp"]-10)

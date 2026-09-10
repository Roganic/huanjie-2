"""Playable levels 1–5: real rewards, derived values, skill progression and save/restore."""
import pytest
from src import state
from src.rules.experience import XP_THRESHOLDS
from tests.conftest import create_session_and_character, enter_passage


@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["warrior","rogue","mage"])
@pytest.mark.parametrize("target_level",[2,3,4,5])
async def test_every_supported_level_from_combat_rewards(client,predictable_combat,kind,target_level):
    sid = await create_session_and_character(client,character_class=kind)
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    initial = session.actor.model_copy(deep=True)
    for npc in session.content_pack.characters.values(): npc.xp_reward = 0
    session.content_pack.characters["goblin-01"].xp_reward = XP_THRESHOLDS[target_level]
    battle = await enter_passage(client,sid)
    for p in battle["participants"]:
        if p["is_player"]: continue
        result = await client.post("/combat/action",headers=h,json={"action_type":"attack","target_id":p["id"]})
        assert result.status_code == 200,result.text
    assert result.json()["victory"]
    actor = state.get_actor(sid)
    assert actor.level == target_level and actor.experience_points == XP_THRESHOLDS[target_level]
    assert actor.hp_max == initial.hp_max + (target_level-1)*({"warrior":6,"rogue":5,"mage":4}[kind]+initial.abilities.modifier("con"))
    assert actor.hp == actor.hp_max and actor.hit_dice_total == actor.hit_dice_remaining == target_level
    assert actor.proficiency_bonus == (3 if target_level == 5 else 2)
    for skill in actor.skills:
        assert skill.modifier == actor.abilities.modifier(skill.ability)+(actor.proficiency_bonus if skill.proficient else 0)
    if kind == "mage":
        expected = {2:{1:3},3:{1:4,2:2},4:{1:4,2:3},5:{1:4,2:3,3:2}}[target_level]
        assert {s.level:s.current for s in actor.spell_slots} == expected
        assert {s.level:s.max for s in actor.spell_slots} == expected
    else:
        assert not actor.spell_slots
    saved = (await client.post("/save",headers=h,json={})).json()
    before = actor.model_dump()
    state._sessions.clear()
    assert (await client.post("/load",json={"save_id":saved["save_id"]})).status_code == 200
    assert state.get_actor(sid).model_dump() == before
    progression = (await client.get("/character/progression",headers=h)).json()
    assert progression["level_cap"] == 5
    assert progression["next_level_xp"] == (XP_THRESHOLDS[target_level+1] if target_level < 5 else None)


def test_level_cap_and_hp_minimum():
    from src.rules.experience import calculate_level_up,get_level_from_xp
    from src.rules.calculations import calculate_max_hp,CharacterClass
    assert get_level_from_xp(100000) == 5
    xp,change = calculate_level_up(5,6500,100,-5,CharacterClass.MAGE)
    assert xp == 6600 and change is None
    assert calculate_max_hp(CharacterClass.MAGE,-5,5) == 5


@pytest.mark.asyncio
async def test_higher_slots_can_replace_exhausted_lower_slots_with_correct_cost(client,predictable_combat):
    from src.models.state import SpellSlot
    from src.game.world import world_scene
    sid = await create_session_and_character(client,character_class="mage")
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    session.actor.spell_slots = [SpellSlot(level=1,current=0,max=4),SpellSlot(level=2,current=1,max=2)]
    for enemy in world_scene(session,"combat-encounter-01").enemies.values(): enemy.hp = enemy.hp_max = 100
    await enter_passage(client,sid)
    result = await client.post("/action",headers=h,json=dict(scene_id="x",actor="x",intent="施放魔法飞弹",approach=""))
    assert result.status_code == 200,result.text
    data = result.json()
    assert data["spell_cast"]["spell_level"] == 1 and data["spell_cast"]["slot_used"] == 2
    assert data["spell_cast"]["damage_total"] == 5
    assert {"resource":"spell_slot","level":2,"amount":1} in data["costs"]
    assert [s.current for s in state.get_actor(sid).spell_slots] == [0,0]
    assert (await client.post("/combat/action",headers=h,json={"action_type":"magic_missile"})).status_code == 409

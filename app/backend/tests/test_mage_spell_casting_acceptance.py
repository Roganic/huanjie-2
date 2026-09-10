"""Real spell cycle: target damage, healing, exhaustion, cantrip and rest."""
import pytest
from src import state
from tests.conftest import create_session_and_character, enter_passage


@pytest.mark.asyncio
async def test_mage_spell_cycle(client, predictable_combat):
    sid = await create_session_and_character(client,character_class="mage")
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    # A durable test opponent allows checking exhaustion before combat ends.
    from src.game.world import world_scene
    for enemy in world_scene(session,"combat-encounter-01").enemies.values():
        enemy.hp = enemy.hp_max = 100
    battle = await enter_passage(client,sid)
    target = next(p for p in battle["participants"] if not p["is_player"])
    first = await client.post("/action",headers=h,json=dict(scene_id="ignored",actor="ignored",intent="施放魔法飞弹",approach="",target=target["id"]))
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["spell_cast"]["damage_total"] == 5
    assert next(p["hp"] for p in result["combat_state"]["participants"] if p["id"] == target["id"]) == 95
    assert state.get_actor(sid).spell_slots[0].current == 1
    state.get_actor(sid).hp = 1
    heal = await client.post("/combat/action",headers=h,json={"action_type":"cure_wounds"})
    assert heal.status_code == 200, heal.text
    assert state.get_actor(sid).hp == state.get_actor(sid).hp_max
    assert state.get_actor(sid).spell_slots[0].current == 0
    before = (await client.get("/combat/state",headers=h)).json()
    exhausted = await client.post("/combat/action",headers=h,json={"action_type":"magic_missile"})
    assert exhausted.status_code == 409
    assert (await client.get("/combat/state",headers=h)).json() == before
    cantrip = await client.post("/combat/action",headers=h,json={"action_type":"ray_of_frost"})
    assert cantrip.status_code == 200, cantrip.text
    assert state.get_actor(sid).spell_slots[0].current == 0
    assert not any(c["resource"] == "spell_slot" for c in cantrip.json()["costs"])
    assert (await client.post("/combat/end",headers=h,json={"reason":"flee"})).status_code == 200
    assert (await client.post("/character/rest",headers=h,json={"kind":"long"})).status_code == 200
    assert state.get_actor(sid).spell_slots[0].current == 2
    state._sessions.clear()
    assert (await client.get("/state",headers=h)).json()["actor"]["spell_slots"][0]["current"] == 2

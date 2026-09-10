"""One maintained three-class journey replaces historical milestone copies."""
import pytest
from src import state
from tests.conftest import create_session_and_character


@pytest.mark.asyncio
@pytest.mark.parametrize("kind",["warrior","rogue","mage"])
async def test_complete_adventure(client,predictable_combat,kind):
    sid = await create_session_and_character(client,name="冒险者",character_class=kind)
    h = {"X-Session-Id":sid}
    async def post(path,body):
        response = await client.post(path,headers=h,json=body)
        assert response.status_code == 200,response.text
        return response.json()
    async def text(intent):
        return await post("/action",dict(scene_id="ignored",actor="ignored",intent=intent,approach=""))
    assert (await text("和老马库斯说话"))["check"] is None
    await text("拾取皮甲")
    await text("装备皮甲")
    await post("/map/move",{"target_scene_id":"dungeon-entrance-01"})
    await text("和托尔金说话")
    assert (await client.get("/exploration",headers=h)).json()["quest"]["status"] == "active"
    battle = (await post("/map/move",{"target_scene_id":"combat-encounter-01"}))["combat"]
    assert len(battle["participants"]) == 4
    skill = {"warrior":"action_surge","rogue":"feint","mage":"magic_missile"}[kind]
    used = await post("/combat/action",{"action_type":skill})
    assert used["costs"]
    battle = used["combat_state"]
    # Bounded by the three actual targets; no conditional assertions or random retry-until-pass.
    for enemy in [p for p in battle["participants"] if not p["is_player"] and p["hp"] > 0]:
        used = await post("/combat/action",{"action_type":"attack","target_id":enemy["id"]})
        assert next(p["hp"] for p in used["combat_state"]["participants"] if p["id"] == enemy["id"]) == 0
    assert used["victory"] and used["xp_gained"] == 150
    actor = state.get_actor(sid)
    assert actor.level == 1 and actor.experience_points == used["xp_gained"]
    assert used["loot_gained"]
    for drop in used["loot_gained"]:
        for item in drop["items"]:
            assert sum(i.name == item["name"] for i in actor.inventory) >= item["quantity"]
    xp = actor.experience_points
    await post("/combat/end",{"reason":"victory"})
    await post("/map/move",{"target_scene_id":"dungeon-entrance-01"})
    await text("和托尔金说话")
    assert (await client.get("/exploration",headers=h)).json()["quest"]["status"] == "completed"
    xp += 300
    assert state.get_actor(sid).level == 2 and state.get_actor(sid).experience_points == xp
    assert state._get_session(sid,False).adventure_outcome["id"] == "road-reopened"
    inventory = len(state.get_actor(sid).inventory)
    await text("和托尔金说话")
    assert len(state.get_actor(sid).inventory) == inventory
    await post("/character/rest",{"kind":"long"})
    assert state.get_actor(sid).hp == state.get_actor(sid).hp_max
    before = (await client.get("/state",headers=h)).json()
    before_map = (await client.get("/map",headers=h)).json()
    save = await post("/save",{"save_name":"三职业闭环"})
    assert (await post("/map/move",{"target_scene_id":"combat-encounter-01"}))["combat"] is None
    assert state.get_actor(sid).experience_points == xp
    state._sessions.clear()
    assert (await client.post("/load",json={"save_id":save["save_id"]})).status_code == 200
    assert (await client.get("/state",headers=h)).json() == before
    assert (await client.get("/map",headers=h)).json() == before_map

"""Recovery and action boundaries for every player-facing mode, including old saves."""
import pytest
from src import state
from src.models.state import AdventurePhase
from src.game.lifecycle import play_status
from tests.conftest import create_session_and_character, enter_passage


@pytest.mark.asyncio
@pytest.mark.parametrize("mode",["combat","aftermath","defeated"])
async def test_all_exploration_adapters_reject_blocked_modes_without_changes(client,predictable_combat,mode):
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    if mode == "combat":
        await enter_passage(client,sid)
    elif mode == "aftermath":
        session.game_phase = AdventurePhase.ENDED
    else:
        # Legacy defeat: no battle snapshot and stale exploration flag.
        session.actor.hp = 0
    state._save_session(session)
    assert (await client.get("/state",headers=h)).json()["play_status"]["mode"] == mode
    before = session.model_dump(exclude={"updated_at"})
    for path,body in [("/inventory/use",{"item_id":"healing_potion"}),
                      ("/inventory/equip",{"item_id":"longsword"}),
                      ("/inventory/pickup",{"item_id":"shortsword"}),
                      ("/inventory/unequip",{"slot":"weapon"}),
                      ("/map/move",{"target_scene_id":"village-square-01"}),
                      ("/character/rest",{"kind":"long"})]:
        assert (await client.post(path,headers=h,json=body)).status_code == 409
    for intent in ["长休","短休","和老马库斯说话","拾取短剑","装备长剑","前往村庄广场","环顾四周"]:
        r = await client.post("/action",headers=h,json=dict(scene_id="ignored",actor="ignored",intent=intent,approach=""))
        if mode == "combat":
            assert r.status_code == 200 and r.json()["outcome"] == "failure"
        else:
            assert r.status_code == 409
    assert session.model_dump(exclude={"updated_at"}) == before


@pytest.mark.asyncio
async def test_defeat_reason_survives_reload_restart_preserves_old_run(client,monkeypatch):
    from src.game import combat_service
    sid = await create_session_and_character(client,character_class="mage",name="继续者")
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    session.content_pack.name = "此冒险的固定版本"
    rolls = iter([1,20,20,20])
    monkeypatch.setattr(combat_service,"roll_d20",lambda:next(rolls))
    monkeypatch.setattr(combat_service,"resolve_attack_with_equipment",lambda *a,**k:dict(hit=True,damage=100,attack_roll=20,total_attack=20,damage_rolls=[100]))
    await enter_passage(client,sid)
    status = (await client.get("/state",headers=h)).json()["play_status"]
    assert status["mode"] == "defeated" and "击倒" in status["reason"]
    assert not status["can_explore"] and status["can_restart"]
    old = session.model_dump(exclude={"updated_at"})
    saved = (await client.post("/save",headers=h,json={})).json()
    fresh = await client.post("/session/restart",headers=h)
    assert fresh.status_code == 200,fresh.text
    data = fresh.json()
    assert data["session_id"] != sid
    assert data["play_status"]["mode"] == "exploration"
    assert data["actor"]["name"] == "继续者" and data["actor"]["level"] == 1
    assert data["actor"]["hp"] == data["actor"]["hp_max"]
    assert data["actor"]["abilities"] == session.actor.abilities.model_dump(by_alias=True)
    new = state._get_session(data["session_id"],False)
    assert new.content_pack.name == "此冒险的固定版本"
    assert new.content_pack is not session.content_pack
    assert not new.world_scenes or all(not world.rewarded_ids for world in new.world_scenes.values())
    assert not new.completed_interactions and not new.narrative_history
    assert session.model_dump(exclude={"updated_at"}) == old
    state._sessions.clear()
    assert (await client.post("/load",json={"save_id":saved["save_id"]})).status_code == 200
    assert (await client.get("/state",headers=h)).json()["play_status"] == status


@pytest.mark.asyncio
async def test_surrender_does_not_restore_exploration_or_allow_restart_midcombat(client,predictable_combat):
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    await enter_passage(client,sid)
    assert (await client.post("/session/restart",headers=h)).status_code == 409
    r = await client.post("/combat/end",headers=h,json={"reason":"surrender"})
    assert r.status_code == 200
    assert (await client.get("/state",headers=h)).json()["play_status"]["mode"] == "defeated"
    assert (await client.post("/combat/end",headers=h,json={"reason":"defeat"})).status_code == 200
    assert (await client.get("/state",headers=h)).json()["play_status"]["mode"] == "defeated"


@pytest.mark.asyncio
async def test_text_and_button_rest_same_time_resources_and_history(client):
    one = await create_session_and_character(client)
    two = await create_session_and_character(client)
    for sid in (one,two):
        session = state._get_session(sid,False)
        session.actor.hp = 1
        session.actor.class_features.action_surge_used = True
    r = await client.post("/action",headers={"X-Session-Id":one},json=dict(scene_id="x",actor="x",intent="长休",approach=""))
    assert r.status_code == 200,r.text
    assert (await client.post("/character/rest",headers={"X-Session-Id":two},json={"kind":"long"})).status_code == 200
    assert state.get_actor(one).model_dump() == state.get_actor(two).model_dump()
    assert state.get_scene(one).time == state.get_scene(two).time == 8
    assert len(state.get_action_history(one)) == len(state.get_action_history(two)) == 1


@pytest.mark.asyncio
async def test_peaceful_offensive_spell_never_hits_a_phantom_enemy(client):
    sid = await create_session_and_character(client,character_class="mage")
    session = state._get_session(sid,False)
    before = session.model_dump(exclude={"updated_at"})
    r = await client.post("/action",headers={"X-Session-Id":sid},json=dict(scene_id="combat-01",actor="x",intent="施放魔法飞弹",approach="向敌人施放"))
    assert r.status_code == 400
    assert session.model_dump(exclude={"updated_at"}) == before


@pytest.mark.asyncio
async def test_scene_injury_can_end_adventure_and_cannot_be_rest_healed(client,monkeypatch):
    from src.content.schema import InteractionDefinition
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    session = state._get_session(sid,False)
    session.actor.hp = 1
    session.content_pack.scenes[session.scene.id].interactions = [InteractionDefinition(id="trap",name="陷阱机关",action_name="调查陷阱机关",skill="investigation",dc=40,failure_damage=1)]
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:1)
    result = await client.post("/action",headers=h,json=dict(scene_id="x",actor="x",intent="调查陷阱机关",approach=""))
    assert result.status_code == 200
    view = (await client.get("/state",headers=h)).json()
    assert view["play_status"]["mode"] == "defeated" and "调查受伤" in view["play_status"]["reason"]
    assert view["scene"]["time"] == 1
    assert (await client.post("/character/rest",headers=h,json={"kind":"long"})).status_code == 409
    saved = (await client.post("/save",headers=h,json={})).json()
    state._sessions.clear()
    assert (await client.post("/load",json={"save_id":saved["save_id"]})).status_code == 200
    assert (await client.get("/state",headers=h)).json()["play_status"] == view["play_status"]

"""Authored checks apply effects once and survive restart/load, scoped to a session."""
import pytest
from pydantic import ValidationError
from src import state
from src.content.schema import InteractionDefinition, ModulePack
from tests.conftest import create_session_and_character


async def setup(client):
    sid = await create_session_and_character(client)
    session = state._get_session(sid,False)
    session.content_pack.scenes[session.scene.id].interactions = [InteractionDefinition(
        id="cache",name="旧木箱",action_name="检查旧木箱",skill="investigation",dc=12,
        success_narrative="你找到了箱底的夹层。",failure_narrative="木刺扎伤了你的手。",failure_damage=1,
        reward_item="healing_potion",reward_info="墙上的记号指向地下通道。")]
    state._save_session(session)
    return sid,{"X-Session-Id":sid}


async def inspect(client,h):
    return await client.post("/action",headers=h,json=dict(scene_id="spoof",actor="spoof",intent="检查旧木箱",approach=""))


@pytest.mark.asyncio
async def test_success_rewards_once_persists_and_is_session_scoped(client,monkeypatch):
    sid,h = await setup(client)
    second,h2 = await setup(client)
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:20)
    guide = (await client.get("/exploration",headers=h)).json()
    assert guide["interactions"] == [{"id":"cache","name":"旧木箱","intent":"检查旧木箱"}]
    initial = len(state.get_actor(sid).inventory)
    response = await inspect(client,h)
    assert response.status_code == 200,response.text
    data = response.json()
    assert data["outcome"] == "success"
    check = data["check"]
    assert check["total"] == 20 + state.get_actor(sid).abilities.modifier("int") + check["proficiency_bonus"]
    assert len(state.get_actor(sid).inventory) == initial+1
    assert state.get_actor(sid).inventory[-1] is not state._get_session(sid,False).content_pack.items["healing_potion"]
    assert state.get_scene(sid).time == 1
    assert len(state.get_action_history(sid)) == 1
    assert (await client.get("/exploration",headers=h)).json()["interactions"] == []
    assert "墙上的记号指向地下通道。" in (await client.get("/exploration",headers=h)).json()["clues"]
    saved = (await client.post("/save",headers=h,json={})).json()
    state._sessions.clear()
    assert (await client.post("/load",json={"save_id":saved["save_id"]})).status_code == 200
    assert (await inspect(client,h)).json()["outcome"] == "failure"
    assert len(state.get_actor(sid).inventory) == initial+1 and state.get_scene(sid).time == 1
    assert (await inspect(client,h2)).json()["outcome"] == "success"
    assert len(state.get_actor(second).inventory) == initial+1


@pytest.mark.asyncio
async def test_failure_applies_damage_without_reward_then_allows_retry(client,monkeypatch):
    sid,h = await setup(client)
    hp = state.get_actor(sid).hp
    count = len(state.get_actor(sid).inventory)
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:1)
    response = await inspect(client,h)
    assert response.status_code == 200,response.text
    assert response.json()["skill_check"]["success"] is False
    assert state.get_actor(sid).hp == hp-1
    assert len(state.get_actor(sid).inventory) == count
    monkeypatch.setattr("src.engine.dice.roll_d20",lambda:20)
    assert (await inspect(client,h)).json()["outcome"] == "success"
    assert len(state.get_actor(sid).inventory) == count+1


@pytest.mark.asyncio
async def test_content_validation_rejects_missing_interaction_reward(client):
    sid,_ = await setup(client)
    pack = state._get_session(sid,False).content_pack.model_dump()
    pack["scenes"]["tavern-01"]["interactions"][0]["reward_item"] = "undefined"
    with pytest.raises(ValidationError,match="reward_item"):
        ModulePack.model_validate(pack)

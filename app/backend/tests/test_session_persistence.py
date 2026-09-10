"""Live sessions and named saves are independent; reset cannot erase another game."""
import pytest
from src import state
from src.persistence import manager
from tests.conftest import create_session_and_character


@pytest.mark.asyncio
async def test_actions_persist_exactly_once_across_memory_restart(client):
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    for index,intent in enumerate(["环顾四周","和老马库斯说话","拾取短剑","装备短剑","卸下武器"],1):
        response = await client.post("/action",headers=h,json=dict(scene_id="ignored",actor="ignored",intent=intent,approach=""))
        assert response.status_code == 200,response.text
        assert response.json()["outcome"] == "success"
        assert len(state.get_action_history(sid)) == index
    before = (await client.get("/state",headers=h)).json()
    state._sessions.clear()
    assert (await client.get("/state",headers=h)).json() == before
    assert len(before["narrative_history"]) == 5


@pytest.mark.asyncio
async def test_named_save_restores_full_state_after_reset_without_erasing_other_saves(client):
    first = await create_session_and_character(client,name="一号")
    second = await create_session_and_character(client,name="二号")
    h = {"X-Session-Id":first}
    before = (await client.get("/state",headers=h)).json()
    save1 = (await client.post("/save",headers=h,json={"save_name":"保留"})).json()
    save2 = (await client.post("/save",headers={"X-Session-Id":second},json={})).json()
    reset = await client.post("/session/reset",headers=h)
    assert reset.status_code == 200
    assert reset.json()["actor"] is None and reset.json()["phase"] == "character_creation"
    assert manager.has_save_file(save1["save_id"]) and manager.has_save_file(save2["save_id"])
    assert (await client.get("/state",headers={"X-Session-Id":second})).json()["actor"]["name"] == "二号"
    assert (await client.post("/load",json={"save_id":save1["save_id"]})).status_code == 200
    after = (await client.get("/state",headers=h)).json()
    assert after["actor"] == before["actor"] and after["scene"] == before["scene"]


@pytest.mark.asyncio
async def test_corrupt_save_is_rejected_without_replacing_live_state(client):
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    saved = (await client.post("/save",headers=h,json={})).json()
    before = (await client.get("/state",headers=h)).json()
    manager.get_save_file_path(saved["save_id"]).write_text('{"broken":')
    assert (await client.post("/load",json={"save_id":saved["save_id"]})).status_code == 400
    assert (await client.get("/state",headers=h)).json() == before
    assert (await client.post("/load",json={"save_id":"missing"})).status_code == 404


@pytest.mark.asyncio
async def test_startup_tolerates_corrupt_legacy_save_and_reset_preserves_other_owner(client):
    from src import game_state
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    path = manager.get_save_file_path()
    path.write_text("broken")
    original_default = state._load_session(state.DEFAULT_SESSION_ID)
    resumed = game_state.try_auto_load_on_startup()
    assert resumed is not None and resumed.actor.model_dump() == original_default.actor.model_dump()
    assert state.get_actor(sid).name == "Aldric"
    own = (await client.post("/save",headers=h,json={})).json()
    path.write_bytes(manager.get_save_file_path(own["save_id"]).read_bytes())
    other = await create_session_and_character(client,name="另一个冒险")
    assert (await client.post("/session/reset",headers={"X-Session-Id":other})).status_code == 200
    assert path.exists()
    assert manager.load_game().session_id == sid

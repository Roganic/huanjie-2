"""Regression coverage for orientation and NPC conversations without a model."""
import json

import pytest

from src import state
from src.persistence import manager
from src.agent import orchestrator
from tests.conftest import create_session_and_character


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", sessions)
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "saves")
    def forbidden(*args, **kwargs):
        raise AssertionError("Ordinary dialogue must not call the generic resolver")
    monkeypatch.setattr(orchestrator, "resolve_action_with_agent", forbidden)


async def talk(client, sid, intent, stream=False):
    return await client.post("/action", headers={"X-Session-Id": sid, "Accept": "text/event-stream" if stream else "application/json"},
                             json={"scene_id": "tavern-01", "actor": "Aldric", "intent": intent, "approach": "礼貌地打招呼"})


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["和老马库斯说话", "和老马库斯说句话", "向老马库斯询问消息", "和老马库斯打招呼"])
@pytest.mark.parametrize("stream", [False, True])
async def test_dialogue_never_rolls_or_starts_combat(client, intent, stream):
    sid = await create_session_and_character(client)
    before = state.get_actor(sid).model_dump()
    response = await talk(client, sid, intent, stream)
    assert response.status_code == 200
    if stream:
        event = next(block for block in response.text.split("\n\n") if "event: complete" in block)
        result = json.loads(event.split("data: ", 1)[1])
    else:
        result = response.json()
    assert result["resolution_type"] == "auto_success"
    assert result["check"] is None and result["effects"] == []
    assert "托尔金" in result["narration"]
    assert state.get_actor(sid).model_dump() == before
    assert state._get_session(sid, False).game_phase.value == "exploration"


@pytest.mark.asyncio
async def test_guidance_clues_movement_repeat_and_save_restore(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    guide = (await client.get("/exploration", headers=headers)).json()
    assert "酒馆" in guide["location"] and "老马库斯" in guide["objective"]
    assert guide["clues"] == []
    await talk(client, sid, "和老马库斯说话")
    again = (await talk(client, sid, "和老马库斯说话")).json()
    assert "再次" in again["narration"]
    guide = (await client.get("/exploration", headers=headers)).json()
    assert len(guide["clues"]) == 1 and "托尔金" in guide["objective"]
    assert {m["target_scene_id"] for m in guide["moves"]} == {"village-square-01", "dungeon-entrance-01"}
    saved = (await client.post("/save", headers=headers, json={"save_name": "线索恢复"})).json()
    assert saved["success"]
    await client.post("/map/move", headers=headers, json={"target_scene_id": "dungeon-entrance-01"})
    guide = (await client.get("/exploration", headers=headers)).json()
    assert {n["name"] for n in guide["npcs"]} == {"托尔金"}
    # The stale scene_id in free text must not allow talking to an absent NPC.
    missing = (await talk(client, sid, "和老马库斯说话")).json()
    assert missing["outcome"] == "failure"
    await talk(client, sid, "和托尔金说话")
    assert len((await client.get("/exploration", headers=headers)).json()["clues"]) == 2
    state._sessions.clear()
    assert (await client.post("/load", json={"save_id": saved["save_id"]})).status_code == 200
    restored = (await client.get("/exploration", headers=headers)).json()
    assert "酒馆" in restored["location"] and len(restored["clues"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("intent", ["和陌生人说话", "打招呼", "威胁老马库斯告诉我秘密"])
async def test_ambiguous_and_special_dialogue_cannot_grant_clues(client, intent):
    sid = await create_session_and_character(client)
    result = (await talk(client, sid, intent)).json()
    assert result["outcome"] == "failure" and result["check"] is None
    assert state._get_session(sid, False).discovered_clues == {}


@pytest.mark.asyncio
async def test_clues_are_session_scoped_and_cleared_for_new_character(client):
    sid = await create_session_and_character(client)
    await talk(client, sid, "和老马库斯说话")
    other = await create_session_and_character(client)
    assert (await client.get("/exploration", headers={"X-Session-Id": other})).json()["clues"] == []
    await client.post("/character/create", headers={"X-Session-Id": sid}, json={"name": "新冒险者", "character_class": "warrior"})
    assert (await client.get("/exploration", headers={"X-Session-Id": sid})).json()["clues"] == []

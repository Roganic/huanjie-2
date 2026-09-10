"""Narration and UI module state follow the actual scene and quest state."""
import pytest
from src import state
from src.content.store import builtin
from src.module_engine import build_module_context_for_prompt
from tests.conftest import create_session_and_character


@pytest.mark.asyncio
async def test_movement_updates_scene_and_module_together(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    response = await client.post("/action", headers=headers, json=dict(
        scene_id="invented", actor="invented", intent="前往地下城入口", approach=""))
    assert response.status_code == 200
    result = (await client.get("/state", headers=headers)).json()
    assert result["scene"]["id"] == "dungeon-entrance-01"
    assert result["active_module"]["current_story_node"] == result["scene"]["name"]
    assert result["active_module"]["module_id"] == builtin().id


@pytest.mark.asyncio
async def test_dialogue_quest_and_catalog_share_progress(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    await client.post("/map/move", headers=headers, json={"target_scene_id": "dungeon-entrance-01"})
    await client.post("/action", headers=headers, json=dict(scene_id="ignored", actor="ignored", intent="和托尔金说话", approach=""))
    result = (await client.get("/state", headers=headers)).json()
    catalog = (await client.get("/modules", headers=headers)).json()
    assert catalog["active_module"] == result["active_module"]
    assert result["active_module"]["active_quests"][0]["quest_id"] == "clear-passage"


@pytest.mark.asyncio
async def test_narrative_prompt_tracks_current_content(client):
    sid = await create_session_and_character(client)
    prompt = build_module_context_for_prompt(sid)
    assert "老马库斯" in prompt and "灯笼酒馆" in prompt
    await client.post("/map/move", headers={"X-Session-Id": sid}, json={"target_scene_id": "dungeon-entrance-01"})
    prompt = build_module_context_for_prompt(sid)
    assert "托尔金" in prompt and "遗忘地下城入口" in prompt
    assert "老马库斯" not in prompt


@pytest.mark.asyncio
async def test_display_and_prompt_do_not_use_legacy_story_pointer(client):
    sid = await create_session_and_character(client)
    from src.models.module import ActiveModuleState
    state._get_session(sid, False).active_module = ActiveModuleState(module_id="old-missing", current_story_node="invented")
    result = (await client.get("/state", headers={"X-Session-Id": sid})).json()
    assert result["active_module"]["module_id"] == builtin().id
    assert "invented" not in build_module_context_for_prompt(sid)

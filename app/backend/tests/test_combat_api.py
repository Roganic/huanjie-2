"""HTTP boundaries not duplicated by test_combat_commands or world_encounters."""
import pytest
from tests.conftest import create_session_and_character, enter_passage


@pytest.mark.asyncio
async def test_combat_requires_valid_character_and_actual_encounter(client):
    assert (await client.post("/combat/start",json={})).status_code == 400
    assert (await client.post("/combat/start",headers={"X-Session-Id":"missing"},json={})).status_code == 404
    sid = (await client.get("/state/bootstrap")).json()["session_id"]
    h = {"X-Session-Id":sid}
    assert (await client.post("/combat/start",headers=h,json={})).status_code == 400
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    assert (await client.post("/combat/start",headers=h,json={})).status_code == 409
    assert (await client.get("/combat/state",headers=h)).status_code == 404
    assert (await client.post("/combat/action",headers=h,json={"action_type":"attack"})).status_code == 400


@pytest.mark.asyncio
async def test_cannot_fabricate_defeat_or_cross_session_target(client,predictable_combat):
    first = await create_session_and_character(client)
    second = await create_session_and_character(client)
    battle = await enter_passage(client,first)
    h = {"X-Session-Id":first}
    assert (await client.post("/combat/end",headers=h,json={"reason":"defeat"})).status_code == 409
    assert (await client.post("/combat/action",headers={"X-Session-Id":second},json={"action_type":"attack","target_id":battle["participants"][-1]["id"]})).status_code == 400
    assert (await client.get("/combat/state",headers=h)).json() == battle

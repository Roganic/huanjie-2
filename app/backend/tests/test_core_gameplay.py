"""Player-facing foundation flow without modules or model calls."""

import pytest

from src import state
from src.models.state import DEFAULT_CONSUMABLES, InventoryItem, AdventurePhase
from src.persistence import manager
from tests.conftest import create_session_and_character


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", sessions)
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.mark.asyncio
async def test_inventory_map_save_reload_flow(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    inventory = (await client.get("/inventory", headers=headers)).json()
    assert any(item["id"] == "shortsword" for item in inventory["available_items"])
    assert (await client.post("/inventory/pickup", headers=headers, json={"item_id": "shortsword"})).status_code == 200
    assert (await client.post("/inventory/pickup", headers=headers, json={"item_id": "shortsword"})).status_code == 409
    assert (await client.post("/inventory/equip", headers=headers, json={"item_id": "shortsword"})).status_code == 200
    assert (await client.post("/inventory/unequip", headers=headers, json={"slot": "armor"})).status_code == 200
    actor = state.get_actor(sid)
    assert actor.ac == 10 + actor.abilities.modifier("dex")
    before_time = state.get_scene(sid).time
    assert (await client.post("/map/move", headers=headers, json={"target_scene_id": "village-square-01"})).status_code == 200
    assert state.get_scene(sid).time == before_time + 1
    map_data = (await client.get("/map", headers=headers)).json()
    assert map_data["current_node"] == "village-square-01"
    assert map_data["connections"]
    assert any(node["id"] == "forest-path-01" for node in map_data["nodes"])
    for node in map_data["nodes"]:
        assert "description" in node and "exits" in node
    assert {"tavern-01", "village-square-01"} <= set(map_data["explored_nodes"])
    saved = (await client.post("/save", headers=headers, json={"save_name": "基础闭环"})).json()
    assert saved["success"]
    assert (await client.post("/map/move", headers=headers, json={"target_scene_id": "forest-path-01"})).status_code == 200
    state._sessions.clear()  # Simulate restarting the in-memory state store.
    loaded = await client.post("/load", json={"save_id": saved["save_id"]})
    assert loaded.status_code == 200, loaded.text
    restored = (await client.get("/state", headers=headers)).json()
    assert restored["scene"]["id"] == "village-square-01"
    assert restored["actor"]["equipped"]["weapon"]["id"] == "shortsword"
    assert restored["actor"]["equipped"]["armor"] is None
    assert "str" in restored["actor"]["abilities"]
    assert "str_" not in restored["actor"]["abilities"]
    assert (await client.get("/map", headers=headers)).json()["explored_nodes"] == map_data["explored_nodes"]
    await client.post("/map/move", headers=headers, json={"target_scene_id": "tavern-01"})
    inventory = (await client.get("/inventory", headers=headers)).json()
    assert not any(item["id"] == "shortsword" for item in inventory["available_items"])


@pytest.mark.asyncio
async def test_consumes_exactly_one_potion_and_persists(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    state.add_items_to_inventory([InventoryItem.from_consumable(DEFAULT_CONSUMABLES["healing_potion"])], sid)
    actor = state.get_actor(sid)
    actor.hp = 1
    state._save_session(state._get_session(sid, False))
    response = await client.post("/inventory/use", headers=headers, json={"item_id": "healing_potion"})
    assert response.status_code == 200
    state._sessions.clear()
    actor = state.get_actor(sid)
    assert 1 < actor.hp <= actor.hp_max
    items = (await client.get("/inventory", headers=headers)).json()["items"]
    assert next(item["quantity"] for item in items if item["id"] == "healing_potion") == 1


@pytest.mark.asyncio
async def test_full_health_does_not_consume_potion(client):
    sid = await create_session_and_character(client)
    response = await client.post("/inventory/use", headers={"X-Session-Id": sid}, json={"item_id": "healing_potion"})
    assert response.status_code == 409
    assert sum(item.id == "healing_potion" for item in state.get_actor(sid).inventory) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("character_class", ["warrior", "mage", "rogue"])
async def test_rest_resources_and_progression(client, character_class):
    sid = await create_session_and_character(client, character_class=character_class)
    headers = {"X-Session-Id": sid}
    actor = state.get_actor(sid)
    actor.hp = 1
    actor.class_features.second_wind_used = True
    for slot in actor.spell_slots:
        slot.current = 0
    state._save_session(state._get_session(sid, False))
    short = await client.post("/character/rest", headers=headers, json={"kind": "short"})
    assert short.status_code == 200, short.text
    actor = state.get_actor(sid)
    assert actor.hp > 1
    assert actor.hit_dice_remaining == 0
    assert not actor.class_features.second_wind_used
    assert all(slot.current == 0 for slot in actor.spell_slots)
    assert (await client.post("/character/rest", headers=headers, json={"kind": "short"})).status_code == 409
    assert (await client.post("/character/rest", headers=headers, json={"kind": "long"})).status_code == 200
    state._sessions.clear()
    actor = state.get_actor(sid)
    assert actor.hp == actor.hp_max
    assert actor.hit_dice_remaining == actor.hit_dice_total
    assert all(slot.current == slot.max for slot in actor.spell_slots)
    growth = (await client.get("/character/progression", headers=headers)).json()
    assert growth["next_level_xp"] == 300
    assert growth["skills"]


@pytest.mark.asyncio
async def test_invalid_actions_and_sessions_do_not_mutate(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    actor_before = state.get_actor(sid).model_dump()
    assert (await client.get("/inventory")).status_code == 400
    assert (await client.get("/inventory", headers={"X-Session-Id": "missing"})).status_code == 404
    assert (await client.post("/inventory/equip", headers=headers, json={"item_id": "missing"})).status_code == 404
    assert (await client.post("/inventory/pickup", headers=headers, json={"item_id": "missing"})).status_code == 404
    assert (await client.post("/map/move", headers=headers, json={"target_scene_id": "forest-path-01"})).status_code == 400
    assert state.get_actor(sid).model_dump() == actor_before
    assert state.get_scene(sid).id == "tavern-01"
    session = state._get_session(sid, False)
    session.game_phase = AdventurePhase.COMBAT
    for path, body in [("/map/move", {"target_scene_id": "village-square-01"}),
                       ("/inventory/unequip", {"slot": "armor"}), ("/character/rest", {"kind": "long"})]:
        assert (await client.post(path, headers=headers, json=body)).status_code == 409
    assert state.get_actor(sid).model_dump() == actor_before


@pytest.mark.asyncio
async def test_pickup_is_isolated_between_players(client):
    first = await create_session_and_character(client, name="一号")
    second = await create_session_and_character(client, name="二号")
    await client.post("/inventory/pickup", headers={"X-Session-Id": first}, json={"item_id": "shortsword"})
    remaining = (await client.get("/inventory", headers={"X-Session-Id": second})).json()["available_items"]
    assert any(item["id"] == "shortsword" for item in remaining)


@pytest.mark.asyncio
async def test_combat_blocks_rest_until_exit(client):
    sid = await create_session_and_character(client)
    headers = {"X-Session-Id": sid}
    state.switch_scene("forest-path-01", sid)
    state._get_session(sid, False).previous_scene_id = "village-square-01"
    assert (await client.post("/combat/start", headers=headers, json={})).status_code == 200
    assert (await client.post("/character/rest", headers=headers, json={"kind": "long"})).status_code == 409
    ended = await client.post("/combat/end", headers=headers, json={"reason": "flee"})
    assert ended.status_code == 200
    assert (await client.get("/state", headers=headers)).json()["game_phase"] == "exploration"
    assert (await client.post("/character/rest", headers=headers, json={"kind": "long"})).status_code == 200


@pytest.mark.parametrize("character_class", ["warrior", "mage", "rogue"])
def test_victory_keeps_loot_and_updates_growth(character_class, monkeypatch):
    from src.models.state import CharacterCreateRequest
    from routes.combat import CombatParticipant, CombatState, _award_victory_rewards
    from types import SimpleNamespace

    sid = state.create_session().session_id
    state.create_character(CharacterCreateRequest(name="成长", character_class=character_class), sid)
    actor = state.get_actor(sid)
    actor.experience_points = 6450
    combat = CombatState(combat_id="growth", round_number=1, turn_index=0,
                         participants=[CombatParticipant(id="enemy", name="哥布林", hp=0, hp_max=7, ac=10, initiative=1, is_player=False)],
                         initiative_order=["enemy"], current_actor_id="enemy", scene=state.get_scene(sid), status="victory")
    loot = SimpleNamespace(loot_entries=[SimpleNamespace(enemy_name="哥布林", items=[SimpleNamespace(
        item_id="proof", name="战利品凭证", description="成长测试", quantity=1)])])
    monkeypatch.setattr("routes.combat.generate_combat_loot", lambda _: loot)
    result = _award_victory_rewards(sid, combat)
    actor = state.get_actor(sid)
    assert any(item.id == "proof" for item in actor.inventory)
    assert actor.level == 5 and actor.proficiency_bonus == 3
    assert actor.hit_dice_total == 5
    assert result["level_up"]["new_level"] == 5
    for skill in actor.skills:
        assert skill.modifier == actor.abilities.modifier(skill.ability) + (3 if skill.proficient else 0)

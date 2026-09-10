"""Content-pack acceptance: author → validate → import → play → save → restore.

Replaces obsolete story-node tests: movement now follows real map exits and quests
advance through actual encounters, never through keyword-only story transitions.
"""
import json
import pytest
from src import state
from src.content import store
from src.content.schema import ModulePack
from src.game import combat_service
from src.persistence import manager
from src.module_engine import build_module_context_for_prompt
from tests.conftest import create_session_and_character


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    directory = tmp_path / "sessions"
    directory.mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", directory)
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(store, "MODULE_DIR", tmp_path / "modules")
    monkeypatch.setattr(combat_service, "roll_d20", lambda: 20)
    monkeypatch.setattr(combat_service, "resolve_attack_with_equipment", lambda actor, ac, **kw: dict(
        hit=bool(actor.character_class), damage=2 if actor.character_class else 0,
        attack_roll=20, total_attack=20, target_ac=ac, damage_rolls=[2]))


@pytest.fixture
def document():
    return dict(schema_version=1, id="moon-bridge", version="1.0", name="月桥委托", description="一个可编辑的独立冒险。",
        starting_scene_id="home", scenes={
            "home": dict(id="home", name="桥头", description="守桥人在此等候。", aliases=["月桥桥头"], character_ids=["guide"], item_ids=["blade", "coat"], exits=[dict(direction="east", target_scene_id="den")]),
            "den": dict(id="den", name="巢穴", description="两只小怪占据了巢穴。", character_ids=["foe", "foe2"], exits=[dict(direction="west", target_scene_id="home")])},
        characters={
            "guide": dict(id="guide", name="守桥人", type="friendly", dialogue="清理巢穴后回来。"),
            "foe": dict(id="foe", name="巢穴小怪", type="hostile", hp=4, weapon_id="blade", xp_reward=30, drops=[dict(item_id="blade", probability=1)]),
            "foe2": dict(id="foe2", name="巢穴头目", type="hostile", hp=4, weapon_id="blade")},
        items={
            "blade": dict(id="blade", name="月牙刃", type="weapon", damage_dice="1d6", attack_ability="dex"),
            "coat": dict(id="coat", name="护桥甲", type="armor", base_ac=15, add_dex_modifier=False),
            "tea": dict(id="tea", name="月光茶", type="consumable", effect_type="heal", effect_dice="1d1+2")},
        quests={"bridge": dict(id="bridge", name="清理巢穴", giver_id="guide", target_scene_id="den", rewards=[dict(item_id="tea", quantity=2)])},
        events={
            "welcome": dict(id="welcome", on="enter_scene", target_id="home", narration="守桥人递来一杯茶。", grants=[dict(item_id="tea")], set_flags=["arrived"]),
            "brief": dict(id="brief", on="talk", target_id="guide", narration="巢穴中还有头目。", required_flags=["arrived"], set_flags=["briefed"]),
            "clear": dict(id="clear", on="scene_cleared", target_id="den", narration="桥路恢复畅通。", required_flags=["briefed"], set_flags=["bridge_open"])})


async def activate(client, document):
    sid = await create_session_and_character(client)
    original = state._get_session(sid, False).model_dump(mode="json", exclude={"updated_at"})
    r = await client.post("/modules/import", json=document)
    assert r.status_code == 200, r.text
    r = await client.post("/modules/activate", headers={"X-Session-Id": sid}, json={"module_id": document["id"]})
    assert r.status_code == 200, r.text
    fresh = r.json()["session_id"]
    assert fresh != sid
    assert state._get_session(sid, False).model_dump(mode="json", exclude={"updated_at"}) == original
    return fresh, {"X-Session-Id": fresh}


@pytest.mark.asyncio
async def test_custom_content_playthrough_and_snapshot(client, document):
    sid, h = await activate(client, document)
    s = state._get_session(sid, False)
    assert s.scene.id == "home" and s.fired_events == ["welcome"]
    topology = (await client.get("/map", headers=h)).json()
    assert {n["id"] for n in topology["nodes"]} == {"home", "den"}
    for id in ("blade", "coat"):
        assert (await client.post("/inventory/pickup", headers=h, json={"item_id": id})).status_code == 200
        assert (await client.post("/inventory/equip", headers=h, json={"item_id": id})).status_code == 200
    assert s.actor.equipped.weapon.id == "blade" and s.actor.ac == 15
    assert (await client.post("/inventory/pickup", headers=h, json={"item_id": "blade"})).status_code == 409
    s = state._get_session(sid, False)  # A rejected transaction restores its session snapshot.
    s.actor.hp = 4
    assert (await client.post("/inventory/use", headers=h, json={"item_id": "tea"})).status_code == 200
    assert s.actor.hp == 7 and not any(i.id == "tea" for i in s.actor.inventory)
    talk = dict(scene_id="ignored", actor="ignored", intent="和守桥人说话", approach="")
    r = await client.post("/action", headers=h, json=talk)
    assert r.status_code == 200 and "巢穴中还有头目" in r.json()["narration"]
    assert s.quest_states["bridge"] == "active"
    prompt = build_module_context_for_prompt(sid)
    assert "月桥委托" in prompt and "守桥人" in prompt and "老马库斯" not in prompt
    r = await client.post("/map/move", headers=h, json={"target_scene_id": "den"})
    assert r.status_code == 200, r.text
    assert len(r.json()["combat"]["participants"]) == 3
    for id in ("foe", "foe2"):
        for _ in range(2):
            r = await client.post("/combat/action", headers=h, json={"action_type": "attack", "target_id": id})
            assert r.status_code == 200, r.text
    assert r.json()["victory"] and "bridge_open" in s.content_flags
    assert r.json()["xp_gained"] == 30
    assert r.json()["loot_gained"][0]["items"][0]["name"] == "月牙刃"
    await client.post("/combat/end", headers=h, json={"reason": "victory"})
    await client.post("/map/move", headers=h, json={"target_scene_id": "home"})
    await client.post("/action", headers=h, json=talk)
    await client.post("/action", headers=h, json=talk)
    assert s.quest_states["bridge"] == "completed"
    assert sum(i.id == "tea" for i in s.actor.inventory) == 2
    assert sorted(s.fired_events) == ["brief", "clear", "welcome"]
    summary = (await client.post("/save", headers=h, json={})).json()
    saved_dialogues = s.npc_dialogue_states["guide"].model_dump()
    # The save pins the pack: it survives catalog deletion and in-memory eviction.
    (store.MODULE_DIR / "moon-bridge.json").unlink()
    state._sessions.clear()
    loaded = await client.post(f"/load/{summary['save_id']}")
    assert loaded.status_code == 200, loaded.text
    s = state._get_session(sid, False)
    assert s.content_pack.id == "moon-bridge" and s.quest_states["bridge"] == "completed"
    assert s.npc_dialogue_states["guide"].model_dump() == saved_dialogues
    assert state.get_npc_dialogue_count("guide", sid) == saved_dialogues["dialogue_count"]
    state.record_npc_dialogue("guide", "守桥人", "player", "回来看看", sid)
    assert state.get_npc_dialogue_count("guide", sid) == saved_dialogues["dialogue_count"] + 1
    assert (await client.post("/inventory/pickup", headers=h, json={"item_id": "blade"})).status_code == 409
    r = await client.post("/map/move", headers=h, json={"target_scene_id": "den"})
    assert r.json()["combat"] is None
    assert len(s.fired_events) == 3


@pytest.mark.asyncio
async def test_no_quests_custom_consumable_in_combat_and_hostile_start(client, document):
    document["quests"] = {}
    document["starting_scene_id"] = "den"
    document["events"]["welcome"]["target_id"] = "den"
    sid, h = await activate(client, document)
    s = state._get_session(sid, False)
    assert s.game_phase.value == "combat"
    s = state._get_session(sid, False)  # A rejected transaction restores its session snapshot.
    s.actor.hp = 4
    r = await client.post("/combat/action", headers=h, json={"action_type": "item:tea"})
    assert r.status_code == 200, r.text
    assert s.actor.hp == 7 and not any(i.id == "tea" for i in s.actor.inventory)
    assert {"resource": "tea", "amount": 1} in r.json()["costs"]
    guide = (await client.get("/exploration", headers=h)).json()
    assert guide["quest"] is None and guide["quests"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("path,value,expected", [
    (("starting_scene_id",), "missing", "starting_scene_id"),
    (("schema_version",), 2, "schema_version"),
    (("scenes", "home", "character_ids"), ["guide", "foe"], "多个地点"),
    (("scenes", "home", "aliases"), ["巢穴"], "歧义"),
    (("items", "blade", "attack_ability"), "power", "str/dex"),
    (("items", "tea", "effect_dice"), "1d0", "恢复骰"),
    (("quests", "bridge", "giver_id"), "foe", "和平活人"),
    (("events", "clear", "on"), "execute_code", "events"),
    (("characters", "foe", "weapon_id"), "tea", "必须引用武器"),
    (("scenes", "den", "id"), "different", "索引一致"),
])
async def test_invalid_content_has_diagnostics_and_is_not_installed(client, document, path, value, expected):
    target = document
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    r = await client.post("/modules/validate", json=document)
    assert r.status_code == 200 and not r.json()["valid"]
    assert expected in json.dumps(r.json(), ensure_ascii=False)
    assert (await client.post("/modules/import", json=document)).status_code == 422
    assert store.get_pack(document["id"]) is None


@pytest.mark.asyncio
async def test_parser_and_import_contract(client, document):
    r = await client.post("/modules/parse", json={"source": json.dumps(document)})
    assert r.json()["valid"] and r.json()["draft"] == document
    schema = (await client.get("/modules/schema")).json()
    assert "characters" in schema["properties"] and "events" in schema["properties"]
    assert not (await client.post("/modules/parse", json={"source": '{"id":"a","id":"b"}'})).json()["valid"]
    assert not (await client.post("/modules/parse", json={"source": "一个冒险故事", "format": "prose"})).json()["valid"]
    assert (await client.post("/modules/import", json=document)).status_code == 200
    assert (await client.post("/modules/import", json=document)).json()["already_installed"]
    assert (await client.get("/modules/moon-bridge")).json()["name"] == document["name"]
    assert store.get_pack("../escape") is None


def test_builtin_has_connected_playable_content():
    pack = store.builtin()
    assert len(pack.scenes) >= 3 and len(pack.characters) >= 2 and pack.quests
    seen, pending = set(), [pack.starting_scene_id]
    while pending:
        id = pending.pop()
        if id in seen: continue
        seen.add(id)
        pending.extend(e.target_scene_id for e in pack.scenes[id].exits)
    assert seen == set(pack.scenes)
    assert ModulePack.model_validate_json(pack.model_dump_json()) == pack


def test_old_quest_snapshot_migration():
    session = state._get_session(state.DEFAULT_SESSION_ID, True)
    snapshot = session.model_dump(mode="json")
    snapshot.pop("quest_states")
    snapshot["passage_quest"] = "completed"
    assert state.SessionData.model_validate(snapshot).quest_states == {"clear-passage": "completed"}


@pytest.mark.asyncio
async def test_state_does_not_refill_spent_hit_dice(client):
    sid = await create_session_and_character(client)
    state.get_actor(sid).hit_dice_remaining = 0
    r = await client.get("/state", headers={"X-Session-Id": sid})
    assert r.status_code == 200
    assert r.json()["actor"]["hit_dice_remaining"] == 0

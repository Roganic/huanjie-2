"""Whole-scene encounters and persistent consequences, without model calls."""
import pytest
from src import state
from src.persistence import manager
from src.game import combat_service as combat
from src.game.world import world_scene
from tests.conftest import create_session_and_character


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    directory = tmp_path / "sessions"
    directory.mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", directory)
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(combat, "roll_d20", lambda: 20)
    def attack(actor, ac, **kwargs):
        return dict(hit=bool(actor.character_class), damage=2 if actor.character_class else 0,
                    attack_roll=20, total_attack=20, target_ac=ac, damage_rolls=[2])
    monkeypatch.setattr(combat, "resolve_attack_with_equipment", attack)


async def setup(client):
    sid = await create_session_and_character(client)
    return sid, {"X-Session-Id": sid}


async def move(client, h, destination):
    response = await client.post("/map/move", headers=h, json={"target_scene_id": destination})
    assert response.status_code == 200, response.text
    return response.json()


async def talk(client, h, intent):
    return await client.post("/action", headers=h, json={"scene_id": "ignored", "actor": "ignored", "intent": intent, "approach": ""})


async def passage(client, h):
    await move(client, h, "dungeon-entrance-01")
    return (await move(client, h, "combat-encounter-01"))["combat"]


@pytest.mark.asyncio
async def test_safe_scene_cannot_spawn_arbitrary_enemy(client):
    sid, h = await setup(client)
    assert (await client.post("/combat/start", headers=h, json={})).status_code == 409
    assert (await client.post("/combat/start", headers=h, json={"target_id": "invented"})).status_code == 400
    assert state._get_session(sid, False).game_phase.value == "exploration"


@pytest.mark.asyncio
async def test_all_enemies_enter_once_and_targeted_damage_skips_dead_turns(client):
    sid, h = await setup(client)
    first = await passage(client, h)
    assert {p["id"] for p in first["participants"] if not p["is_player"]} == {"goblin-01", "goblin-shaman-01", "wolf-01"}
    second = (await client.post("/combat/start", headers=h, json={})).json()
    assert first["combat_id"] == second["combat_id"]
    assert first["initiative_order"] == second["initiative_order"]
    for _ in range(3):
        hit = (await client.post("/combat/action", headers=h, json={"action_type": "attack", "target_id": "goblin-shaman-01"})).json()
    enemies = world_scene(state._get_session(sid, False)).enemies
    assert enemies["goblin-shaman-01"].hp == 0
    assert enemies["goblin-01"].hp == enemies["wolf-01"].hp == 5
    assert not hit["combat_ended"]
    assert not any(e["type"] == "attack" and e["actor_id"] == "goblin-shaman-01" for e in hit["events"])
    assert (await client.post("/combat/action", headers=h, json={"action_type": "attack", "target_id": "goblin-shaman-01"})).status_code == 409
    assert (await client.post("/map/move", headers=h, json={"target_scene_id": "dungeon-entrance-01"})).status_code == 409


@pytest.mark.asyncio
async def test_enemy_first_rolls_run_every_enemy_then_player(client, monkeypatch):
    sid, h = await setup(client)
    rolls = iter([1, 20, 19, 18])
    monkeypatch.setattr(combat, "roll_d20", lambda: next(rolls))
    started = await passage(client, h)
    assert started["current_actor_id"] == state.get_actor(sid).id
    assert len([entry for entry in started["log"] if entry["action_type"] == "attack"]) == 3
    for p in started["participants"]:
        assert p["initiative"] == p["initiative_roll"] + p["speed"]


@pytest.mark.asyncio
async def test_retreat_save_reload_reentry_preserves_enemy_wounds(client):
    sid, h = await setup(client)
    first = await passage(client, h)
    await client.post("/combat/action", headers=h, json={"action_type": "attack", "target_id": "wolf-01"})
    before = (await client.get("/combat/state", headers=h)).json()
    saved = (await client.post("/save", headers=h, json={"save_name": "多人战斗"})).json()
    state._sessions.clear()
    assert (await client.get("/combat/state", headers=h)).json() == before
    await client.post("/combat/action", headers=h, json={"action_type": "flee"})
    await client.post("/combat/end", headers=h, json={"reason": "flee"})
    assert state.get_scene(sid).id == "dungeon-entrance-01"
    again = (await move(client, h, "combat-encounter-01"))["combat"]
    assert again["combat_id"] != first["combat_id"]
    assert next(p["hp"] for p in again["participants"] if p["id"] == "wolf-01") == 3
    assert (await client.post("/load", json={"save_id": saved["save_id"]})).status_code == 200
    assert (await client.get("/combat/state", headers=h)).json() == before


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [False, True])
async def test_attack_peaceful_npc_is_blocked_without_changing_world(client, text):
    sid, h = await setup(client)
    before = state.get_actor(sid).model_dump()
    response = await talk(client, h, "攻击老马库斯") if text else await client.post("/combat/start", headers=h, json={"target_id": "tavern-keeper-01"})
    assert response.status_code == 409, response.text
    assert "暂不支持攻击" in response.json()["detail"]
    session = state._get_session(sid,False)
    assert session.game_phase.value == "exploration" and session.combat_snapshot is None
    assert not world_scene(session).aggression and not world_scene(session).enemies
    assert state.get_actor(sid).model_dump() == before
    assert (await talk(client,h,"和老马库斯说话")).json()["outcome"] == "success"


@pytest.mark.asyncio
async def test_clear_scene_deliver_quest_once_and_no_respawn(client):
    sid, h = await setup(client)
    await move(client, h, "dungeon-entrance-01")
    await talk(client, h, "和托尔金说话")
    assert (await client.get("/exploration", headers=h)).json()["quest"]["status"] == "active"
    started = (await move(client, h, "combat-encounter-01"))["combat"]
    for target in [p["id"] for p in started["participants"] if not p["is_player"]]:
        for _ in range(3):
            response = await client.post("/combat/action", headers=h, json={"action_type": "attack", "target_id": target})
            assert response.status_code == 200, response.text
    assert response.json()["victory"]
    assert state.get_actor(sid).experience_points > 0
    await client.post("/combat/end", headers=h, json={"reason": "victory"})
    guide = (await client.get("/exploration", headers=h)).json()
    assert guide["quest"]["status"] == "ready" and guide["enemy_count"] == 0 and guide["danger"] == "已清理"
    assert (await client.get("/state", headers=h)).json()["scene"]["npcs"] == []
    await move(client, h, "dungeon-entrance-01")
    def potions():
        return sum(i.id == "healing_potion" for i in state.get_actor(sid).inventory)
    before = potions()
    await talk(client, h, "和托尔金说话")
    assert potions() == before + 2
    await talk(client, h, "和托尔金说话")
    assert potions() == before + 2
    saved = (await client.post("/save", headers=h, json={})).json()
    state._sessions.clear()
    await client.post("/load", json={"save_id": saved["save_id"]})
    assert (await client.get("/exploration", headers=h)).json()["quest"]["status"] == "completed"
    xp = state.get_actor(sid).experience_points
    assert (await move(client, h, "combat-encounter-01"))["combat"] is None
    assert (await client.post("/combat/start", headers=h, json={})).status_code == 409
    assert state.get_actor(sid).experience_points == xp


@pytest.mark.asyncio
async def test_legacy_hostile_save_stays_playable_without_new_aggression(client):
    sid, h = await setup(client)
    await move(client, h, "dungeon-entrance-01")
    await talk(client, h, "和托尔金说话")
    # Restore an already hostile world from the previous version; new attacks are disabled.
    from src.game.world import make_enemy
    session = state._get_session(sid,False)
    world = world_scene(session)
    npc = next(n for n in session.scene.npcs if n.id=="wounded-adventurer-01")
    world.enemies[npc.id] = make_enemy(npc,session.content_pack)
    world.aggression = True
    state._save_session(session)
    state._sessions.clear()
    await client.post("/combat/start", headers=h, json={"target_id": "wounded-adventurer-01"})
    for _ in range(4):
        response = await client.post("/combat/action", headers=h, json={"action_type": "attack"})
        assert response.status_code == 200, response.text
    assert response.json()["xp_gained"] == 0 and response.json()["loot_gained"] == []
    await client.post("/combat/end", headers=h, json={"reason": "victory"})
    guide = (await client.get("/exploration", headers=h)).json()
    assert guide["quest"]["status"] == "failed" and guide["danger"] == "危险"
    assert guide["npcs"] == []
    assert (await talk(client, h, "和托尔金说话")).json()["outcome"] == "failure"
    assert (await client.post("/combat/start", headers=h, json={"target_id": "wounded-adventurer-01"})).status_code == 409


@pytest.mark.asyncio
async def test_text_movement_uses_same_encounter_and_rogue_no_perception(client):
    sid = await create_session_and_character(client, character_class="rogue")
    h = {"X-Session-Id": sid}
    await move(client, h, "dungeon-entrance-01")
    result = await talk(client, h, "进入地下城通道")
    assert result.status_code == 200, result.text
    assert state._get_session(sid, False).game_phase.value == "combat"
    feint = (await client.post("/combat/action", headers=h, json={"action_type": "feint"})).json()
    assert not any(e["type"] == "check" for e in feint["events"])
    assert not feint["combat_state"]["bonus_action_available"]

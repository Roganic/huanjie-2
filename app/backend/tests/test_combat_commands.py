"""Actual player adapters, resources, turns and durable combat state."""
import json
import pytest
from src import state
from src.persistence import manager
from src.game import combat_service as service
from routes import combat as routes
from tests.conftest import create_session_and_character


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "sessions"
    path.mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", path)
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "saves")
    monkeypatch.setattr(routes, "_combats", {})
    monkeypatch.setattr(service, "roll_d20", lambda: 20)
    def attack(actor, ac, **kwargs):
        return dict(hit=True, damage=2 if actor.character_class else 1, attack_roll=15,
                    total_attack=19, target_ac=ac, weapon_used="测试武器", damage_rolls=[2])
    monkeypatch.setattr(service, "resolve_attack_with_equipment", attack)


async def start(client, kind="warrior"):
    sid = await create_session_and_character(client, character_class=kind)
    headers = {"X-Session-Id": sid}
    state.switch_scene("forest-path-01", sid)
    state._get_session(sid, False).previous_scene_id = "village-square-01"
    result = await client.post("/combat/start", headers=headers, json={})
    assert result.status_code == 200, result.text
    assert result.json()["current_actor_id"] == state.get_actor(sid).id
    return sid, headers, result.json()


@pytest.mark.asyncio
async def test_surge_creates_real_extra_action_and_second_wind_syncs(client):
    sid, h, combat = await start(client)
    session = state._get_session(sid, False)
    session.actor.hp = 3
    state._save_session(session)
    result = await client.post("/combat/action", headers=h, json={"action_type":"second_wind"})
    assert result.status_code == 200, result.text
    assert result.json()["combat_state"]["bonus_action_available"] is False
    actor = state.get_actor(sid)
    assert next(p for p in result.json()["combat_state"]["participants"] if p["is_player"])["hp"] == actor.hp
    assert (await client.post("/combat/action", headers=h, json={"action_type":"second_wind"})).status_code == 409
    result = await client.post("/combat/action", headers=h, json={"action_type":"action_surge"})
    assert result.json()["combat_state"]["actions_remaining"] == 2
    before = state.get_actor(sid).hp
    first = await client.post("/combat/action", headers=h, json={"action_type":"attack"})
    assert first.json()["combat_state"]["actions_remaining"] == 1
    assert state.get_actor(sid).hp == before  # Enemy does not act between surge attacks.
    second = await client.post("/combat/action", headers=h, json={"action_type":"attack"})
    assert second.status_code == 200
    assert state.get_actor(sid).hp == before - 1
    assert any(e["actor_id"] == session.enemy.id for e in second.json()["events"])


@pytest.mark.asyncio
async def test_text_and_button_share_costs_and_reject_illegal_actions(client):
    sid, h, _ = await start(client, "mage")
    session = state._get_session(sid, False)
    session.enemy.hp = session.enemy.hp_max = 100
    state._save_session(session)
    body = dict(scene_id=session.scene.id, actor=session.actor.name, intent="施放魔法飞弹", approach="")
    first = await client.post("/action", headers=h, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["costs"] == [{"resource":"spell_slot", "level":1, "amount":1}, {"resource":"action", "amount":1}]
    second = await client.post("/combat/action", headers=h, json={"action_type":"magic_missile"})
    assert second.status_code == 200, second.text
    assert second.json()["costs"] == first.json()["costs"]
    snapshot = state.get_actor(sid).model_dump()
    assert (await client.post("/action", headers=h, json=body)).json()["outcome"] == "failure"
    assert state.get_actor(sid).model_dump() == snapshot
    assert (await client.post("/combat/action", headers=h, json={"action_type":"second_wind"})).status_code == 400
    assert (await client.post("/combat/action", headers=h, json={"action_type":"attack", "target_id":"not-here"})).status_code == 400
    assert (await client.post("/combat/action", headers=h, json={"action_type":"attack", "weapon":"invented"})).status_code == 400
    assert state.get_actor(sid).model_dump() == snapshot


@pytest.mark.asyncio
async def test_hide_then_sneak_consumes_bonus_and_breaks_hidden(client, monkeypatch):
    sid, h, _ = await start(client, "rogue")
    session = state._get_session(sid, False)
    session.enemy.hp = session.enemy.hp_max = 100
    state._save_session(session)
    monkeypatch.setattr(service, "roll_damage", lambda _: (3, [3]))
    hidden = await client.post("/combat/action", headers=h, json={"action_type":"hide"})
    assert hidden.status_code == 200
    assert "hidden" in state.get_actor(sid).conditions
    assert (await client.post("/combat/action", headers=h, json={"action_type":"hide"})).status_code == 409
    attack = (await client.post("/combat/action", headers=h, json={"action_type":"attack"})).json()
    assert attack["sneak_attack_damage"] == 3 and attack["damage"] == 5
    assert "hidden" not in state.get_actor(sid).conditions
    assert state.get_enemy(sid).hp == 95


@pytest.mark.asyncio
async def test_sse_rewards_once_and_exit_returns_to_original_scene(client):
    sid, h, original = await start(client)
    session = state._get_session(sid, False)
    session.enemy.hp = 1
    state._save_session(session)
    result = await client.post("/combat/action", headers={**h,"Accept":"text/event-stream"}, json={"action_type":"attack"})
    assert result.status_code == 200, result.text
    complete = next(block for block in result.text.split("\n\n") if block.startswith("event: complete"))
    data = json.loads(complete.split("data: ",1)[1])
    assert data["combat_ended"] and data["xp_gained"] > 0
    assert data["combat_state"]["status"] == "victory"
    xp = state.get_actor(sid).experience_points
    assert state._get_session(sid,False).game_phase.value == "ended"
    assert (await client.post("/combat/action", headers=h, json={"action_type":"attack"})).status_code == 409
    assert state.get_actor(sid).experience_points == xp
    assert (await client.post("/combat/end", headers=h,json={"reason":"victory"})).status_code == 200
    assert state.get_scene(sid).id == original["scene"]["id"]
    assert state._get_session(sid,False).game_phase.value == "exploration"


@pytest.mark.asyncio
async def test_cannot_claim_victory_or_reset_encounter(client):
    sid, h, first = await start(client)
    again = await client.post("/combat/start", headers=h,json={})
    assert again.json()["combat_id"] == first["combat_id"]
    assert (await client.post("/combat/end", headers=h,json={"reason":"victory"})).status_code == 409
    assert state.get_actor(sid).experience_points == 0


@pytest.mark.asyncio
async def test_combat_save_and_memory_restart_restore_budgets(client):
    sid, h, _ = await start(client)
    await client.post("/combat/action", headers=h, json={"action_type":"action_surge"})
    before = (await client.get("/combat/state",headers=h)).json()
    save = (await client.post("/save",headers=h,json={})).json()
    state._sessions.clear()
    routes._combats.clear()
    restored = (await client.get("/combat/state",headers=h)).json()
    assert restored == before
    await client.post("/combat/action",headers=h,json={"action_type":"attack"})
    loaded = await client.post("/load",json={"save_id":save["save_id"]})
    assert loaded.status_code == 200, loaded.text
    assert (await client.get("/combat/state",headers=h)).json() == before


@pytest.mark.asyncio
async def test_wrong_turn_no_mutation(client):
    sid, h, _ = await start(client)
    combat = routes._get_combat_state(sid)
    combat.current_actor_id = state.get_enemy(sid).id
    routes._set_combat_state(sid,combat)
    before = state.get_actor(sid).model_dump()
    assert (await client.post("/combat/action",headers=h,json={"action_type":"action_surge"})).status_code == 409
    assert state.get_actor(sid).model_dump() == before


@pytest.mark.asyncio
async def test_startup_does_not_roll_back_new_encounter_to_old_save(client):
    from src import game_state
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    await client.post("/save",headers=h,json={})
    state.switch_scene("forest-path-01", sid)
    combat = (await client.post("/combat/start",headers=h,json={})).json()
    state._sessions.clear()
    routes._combats.clear()
    restored = game_state.try_auto_load_on_startup()
    assert restored.game_phase.value == "combat"
    assert (await client.get("/combat/state",headers=h)).json()["combat_id"] == combat["combat_id"]


@pytest.mark.asyncio
async def test_full_health_short_rest_restores_features_without_hit_die(client):
    sid, h, _ = await start(client)
    await client.post("/combat/action",headers=h,json={"action_type":"action_surge"})
    await client.post("/combat/end",headers=h,json={"reason":"flee"})
    actor = state.get_actor(sid)
    actor.hp = actor.hp_max
    actor.hit_dice_remaining = 0
    state._save_session(state._get_session(sid,False))
    assert (await client.get("/character/progression",headers=h)).json()["can_short_rest"]
    result = await client.post("/character/rest",headers=h,json={"kind":"short"})
    assert result.status_code == 200, result.text
    actor = state.get_actor(sid)
    assert not actor.class_features.action_surge_used
    assert actor.hit_dice_remaining == 0


@pytest.mark.asyncio
async def test_enemy_first_initiative_executes_once_then_returns_player(client, monkeypatch):
    sid = await create_session_and_character(client)
    h = {"X-Session-Id":sid}
    state.switch_scene("forest-path-01", sid)
    rolls = iter([1,20])
    monkeypatch.setattr(service,"roll_d20",lambda:next(rolls))
    before = state.get_actor(sid).hp
    first = (await client.post("/combat/start",headers=h,json={})).json()
    assert first["initiative_order"][0] == state.get_enemy(sid).id
    assert first["current_actor_id"] == state.get_actor(sid).id
    assert state.get_actor(sid).hp == before-1
    assert len([entry for entry in first["log"] if entry["action_type"] == "attack"]) == 1
    again = (await client.post("/combat/start",headers=h,json={})).json()
    assert again == first


@pytest.mark.asyncio
async def test_defending_affects_enemy_roll_and_expires(client, monkeypatch):
    sid, h, _ = await start(client)
    received = []
    def attack(actor, ac, **kwargs):
        received.append(kwargs.get("advantage"))
        return dict(hit=False,damage=0,attack_roll=1,total_attack=1)
    monkeypatch.setattr(service,"resolve_attack_with_equipment",attack)
    result = await client.post("/combat/action",headers=h,json={"action_type":"defend"})
    assert result.status_code == 200
    assert received == [False]
    assert "defending" not in state.get_actor(sid).conditions
    assert any(e["type"]=="condition_removed" and e["delta"]=="defending" for e in result.json()["events"])

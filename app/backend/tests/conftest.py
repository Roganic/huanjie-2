"""Shared pytest fixtures and utilities."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import reset_state


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path, monkeypatch):
    """Every test gets disposable saves, sessions and memories; never touch user data."""
    from src import state
    from src.persistence import manager
    from src.save_load import manager as legacy_saves
    from src.content import store
    from src.memory import session_memory
    for name in ("runtime-sessions", "runtime-saves", "runtime-legacy-saves", "runtime-modules"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr(state, "SESSION_STORE_DIR", tmp_path / "runtime-sessions")
    monkeypatch.setattr(state, "_sessions", {})
    monkeypatch.setattr(manager, "SAVE_DIR", tmp_path / "runtime-saves")
    monkeypatch.setattr(legacy_saves, "SAVE_DIR", tmp_path / "runtime-legacy-saves")
    monkeypatch.setattr(store, "MODULE_DIR", tmp_path / "runtime-modules")
    monkeypatch.setattr(session_memory, "_memory_store", {})
    monkeypatch.delenv("KIMI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GM_API_KEY", raising=False)
    monkeypatch.setattr('src.gm.provider.CONFIG_FILE', tmp_path / 'no-gm-config')
    monkeypatch.setattr('src.gm.budget.LEDGER', tmp_path / 'usage.sqlite')
    # Transport tests use fake hosts and mock HTTP; production pricing remains
    # pinned to the provider/region whose official tariff was verified.
    from src.gm import budget
    monkeypatch.setattr(budget, 'ALLOWED_HOSTS', {
        key: {*hosts, 'example.invalid', 'provider.invalid'} for key, hosts in budget.ALLOWED_HOSTS.items()})
    monkeypatch.setattr("src.agent.narrator.KIMI_API_KEY", "")


@pytest.fixture(autouse=True)
def _fresh_state(_isolated_runtime):
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    """Create an async HTTP client for the test app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def create_session_and_character(
    client,
    name="Aldric",
    character_class="warrior",
):
    """Helper to create a session and character for tests.
    
    Returns the session_id to be used in subsequent requests.
    """
    # Create session
    resp = await client.get("/state/bootstrap")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    
    # Create character
    resp = await client.post(
        "/character/create",
        json={
            "name": name,
            "character_class": character_class,
            "ability_generation": "standard_array",
        },
        headers={"X-Session-Id": session_id},
    )
    assert resp.status_code == 200
    
    return session_id


def create_default_actor():
    """Create a default actor directly in the current session for unit tests."""
    from src.state import create_character
    from src.models.state import CharacterCreateRequest, CharacterClass
    create_character(
        CharacterCreateRequest(name="Aldric", character_class=CharacterClass.WARRIOR)
    )

@pytest.fixture
def predictable_combat(monkeypatch):
    """Fix random rolls, leaving player damage/turn/resource rules intact."""
    from src.game import combat_service as service
    original = service.resolve_attack_with_equipment
    monkeypatch.setattr(service, "roll_d20", lambda: 20)
    monkeypatch.setattr("random.randint", lambda low, high: high)
    monkeypatch.setattr("random.random", lambda: 0.0)
    def attack(actor, target_ac, **kwargs):
        if actor.character_class:
            return original(actor, target_ac, **kwargs)
        return dict(hit=False, damage=0, attack_roll=1, total_attack=1,
                    target_ac=target_ac, damage_rolls=[], weapon_used="测试敌人")
    monkeypatch.setattr(service, "resolve_attack_with_equipment", attack)


async def enter_passage(client, sid):
    headers = {"X-Session-Id": sid}
    for scene in ("dungeon-entrance-01", "combat-encounter-01"):
        result = await client.post("/map/move", headers=headers, json={"target_scene_id": scene})
        assert result.status_code == 200, result.text
    return result.json()["combat"]


def enter_passage_sync(client, sid):
    """Real encounter for synchronous HTTP tests, with durable fixture opponents."""
    from src import state
    from src.game.world import world_scene
    session = state._get_session(sid,False)
    for enemy in world_scene(session,"combat-encounter-01").enemies.values():
        enemy.hp = enemy.hp_max = 100
    for scene in ("dungeon-entrance-01","combat-encounter-01"):
        response = client.post("/map/move",headers={"X-Session-Id":sid},json={"target_scene_id":scene})
        assert response.status_code == 200,response.text

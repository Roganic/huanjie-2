"""Tests for in-memory state mutation after action resolution."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.action import Effect
from src.state import apply_effects, get_actor, get_bootstrap_state, get_scene, reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# ---------------------------------------------------------------------------
# Unit: apply_effects on actor HP
# ---------------------------------------------------------------------------

def test_hp_damage():
    assert get_actor().hp == 12
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=-3, description="test"),
    ])
    assert get_actor().hp == 9


def test_hp_heal():
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=-5, description="dmg"),
    ])
    assert get_actor().hp == 7
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=2, description="heal"),
    ])
    assert get_actor().hp == 9


def test_hp_does_not_exceed_max():
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=100, description="overheal"),
    ])
    assert get_actor().hp == 12  # hp_max


def test_hp_does_not_go_below_zero():
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=-999, description="overkill"),
    ])
    assert get_actor().hp == 0


# ---------------------------------------------------------------------------
# Unit: conditions
# ---------------------------------------------------------------------------

def test_add_condition():
    apply_effects([
        Effect(target="aldric-01", field="conditions_add", delta="frightened",
               description="test"),
    ])
    assert "frightened" in get_actor().conditions


def test_add_duplicate_condition_is_idempotent():
    eff = Effect(target="aldric-01", field="conditions_add", delta="poisoned",
                 description="test")
    apply_effects([eff, eff])
    assert get_actor().conditions.count("poisoned") == 1


def test_remove_condition():
    apply_effects([
        Effect(target="aldric-01", field="conditions_add", delta="stunned",
               description="add"),
    ])
    assert "stunned" in get_actor().conditions
    apply_effects([
        Effect(target="aldric-01", field="conditions_remove", delta="stunned",
               description="remove"),
    ])
    assert "stunned" not in get_actor().conditions


def test_remove_absent_condition_is_noop():
    apply_effects([
        Effect(target="aldric-01", field="conditions_remove", delta="invisible",
               description="noop"),
    ])
    assert get_actor().conditions == []


# ---------------------------------------------------------------------------
# Unit: scene time
# ---------------------------------------------------------------------------

def test_time_advances():
    assert get_scene().time == 0
    apply_effects([
        Effect(target="tavern-01", field="time", delta=1, description="tick"),
    ])
    assert get_scene().time == 1


def test_time_accumulates():
    apply_effects([
        Effect(target="tavern-01", field="time", delta=3, description="long"),
    ])
    apply_effects([
        Effect(target="tavern-01", field="time", delta=2, description="more"),
    ])
    assert get_scene().time == 5


# ---------------------------------------------------------------------------
# Unit: unknown effects are silently skipped
# ---------------------------------------------------------------------------

def test_unknown_target_skipped():
    apply_effects([
        Effect(target="nobody", field="hp", delta=-1, description="ghost"),
    ])
    assert get_actor().hp == 12


def test_unknown_field_skipped():
    apply_effects([
        Effect(target="aldric-01", field="xp", delta=100, description="nope"),
    ])
    # No crash; actor unchanged
    assert get_actor().hp == 12


# ---------------------------------------------------------------------------
# Unit: reset
# ---------------------------------------------------------------------------

def test_reset_restores_state():
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=-5, description="dmg"),
        Effect(target="aldric-01", field="conditions_add", delta="poisoned",
               description="add"),
        Effect(target="tavern-01", field="time", delta=3, description="tick"),
    ])
    reset_state()
    assert get_actor().hp == 12
    assert get_actor().conditions == []
    assert get_scene().time == 0


# ---------------------------------------------------------------------------
# Integration: bootstrap reflects mutations
# ---------------------------------------------------------------------------

def test_bootstrap_reflects_hp_change():
    apply_effects([
        Effect(target="aldric-01", field="hp", delta=-4, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.actor.hp == 8


def test_bootstrap_reflects_conditions():
    apply_effects([
        Effect(target="aldric-01", field="conditions_add", delta="poisoned",
               description="test"),
    ])
    state = get_bootstrap_state()
    assert "poisoned" in state.actor.conditions


def test_bootstrap_reflects_time():
    apply_effects([
        Effect(target="tavern-01", field="time", delta=2, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.scene.time == 2


# ---------------------------------------------------------------------------
# Integration: /action endpoint mutates state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_check_advances_time(client):
    """Any check (not auto-success) should advance scene time by 1."""
    async with client as c:
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle the barkeep",
            "approach": "use brute force",
            "ability": "str",
            "dc": 10,
        })
    assert get_scene().time == 1


@pytest.mark.asyncio
async def test_failed_physical_check_reduces_hp(client):
    """A failed STR/DEX/CON check should cost 1 HP."""
    async with client as c:
        # Force failure with impossibly high DC
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        })
    assert resp.json()["outcome"] == "failure"
    assert get_actor().hp == 11  # 12 - 1


@pytest.mark.asyncio
async def test_auto_success_does_not_mutate(client):
    """Auto-success actions should not change HP or time."""
    async with client as c:
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around the tavern",
            "approach": "casually look at the patrons",
        })
    assert get_actor().hp == 12
    assert get_scene().time == 0


@pytest.mark.asyncio
async def test_bootstrap_endpoint_shows_live_state(client):
    """GET /state/bootstrap should reflect mutations from prior actions."""
    async with client as c:
        # Deal damage
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        })
        # Fetch bootstrap
        resp = await c.get("/state/bootstrap")
    data = resp.json()
    assert data["actor"]["hp"] == 11
    assert data["scene"]["time"] == 1


# ---------------------------------------------------------------------------
# Integration: /state/reset endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_endpoint_restores_initial_state(client):
    """POST /state/reset should restore actor and scene to initial values."""
    async with client as c:
        # Mutate state: damage HP, add condition, advance time
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        })
        apply_effects([
            Effect(target="aldric-01", field="conditions_add", delta="exhausted",
                   description="test"),
        ])
        # Verify state is mutated
        assert get_actor().hp == 11
        assert "exhausted" in get_actor().conditions
        assert get_scene().time == 1

        # Call reset endpoint
        resp = await c.post("/state/reset")

        # Verify response status
        assert resp.status_code == 200

        # Verify state is restored
        assert get_actor().hp == 12
        assert get_actor().conditions == []
        assert get_scene().time == 0


@pytest.mark.asyncio
async def test_reset_endpoint_returns_fresh_bootstrap(client):
    """POST /state/reset should return the reset bootstrap state."""
    async with client as c:
        # Mutate state
        apply_effects([
            Effect(target="aldric-01", field="hp", delta=-7, description="dmg"),
            Effect(target="tavern-01", field="time", delta=5, description="tick"),
        ])

        # Call reset and check response
        resp = await c.post("/state/reset")
        data = resp.json()

        # Response should contain fresh initial state
        assert data["actor"]["hp"] == 12
        assert data["actor"]["hp_max"] == 12
        assert data["actor"]["conditions"] == []
        assert data["scene"]["time"] == 0
        assert data["scene"]["id"] == "tavern-01"


@pytest.mark.asyncio
async def test_reset_clears_accumulated_mutations(client):
    """Multiple mutations followed by reset should all be cleared."""
    async with client as c:
        # Apply multiple mutations
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle",
            "approach": "use brute force",
            "ability": "str",
            "dc": 10,
        })
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "another action",
            "approach": "try hard",
            "ability": "dex",
            "dc": 99,
        })
        apply_effects([
            Effect(target="aldric-01", field="conditions_add", delta="stunned",
                   description="test"),
            Effect(target="aldric-01", field="conditions_add", delta="poisoned",
                   description="test"),
        ])

        # Verify multiple mutations applied
        assert get_actor().hp < 12  # Some damage from failed check
        assert len(get_actor().conditions) == 2
        assert get_scene().time >= 2

        # Reset
        await c.post("/state/reset")

        # All cleared
        assert get_actor().hp == 12
        assert get_actor().conditions == []
        assert get_scene().time == 0

"""Tests for in-memory state mutation after action resolution."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.action import Effect
from src.models.state import NarrativeHistoryEntry
from src.state import (
    apply_effects,
    append_narrative_history,
    get_actor,
    get_bootstrap_state,
    get_narrative_context,
    get_narrative_history,
    get_scene,
    reset_state,
)
from tests.conftest import create_default_actor


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
    create_default_actor()
    assert get_actor().hp == 12
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=-3, description="test"),
    ])
    assert get_actor().hp == 9


def test_hp_heal():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=-5, description="dmg"),
    ])
    assert get_actor().hp == 7
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=2, description="heal"),
    ])
    assert get_actor().hp == 9


def test_hp_does_not_exceed_max():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=100, description="overheal"),
    ])
    assert get_actor().hp == 12  # hp_max


def test_hp_does_not_go_below_zero():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=-999, description="overkill"),
    ])
    assert get_actor().hp == 0


# ---------------------------------------------------------------------------
# Unit: conditions
# ---------------------------------------------------------------------------

def test_add_condition():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="conditions_add", delta="frightened",
               description="test"),
    ])
    assert "frightened" in get_actor().conditions


def test_add_duplicate_condition_is_idempotent():
    create_default_actor()
    eff = Effect(target=get_actor().id, field="conditions_add", delta="poisoned",
                 description="test")
    apply_effects([eff, eff])
    assert get_actor().conditions.count("poisoned") == 1


def test_remove_condition():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="conditions_add", delta="stunned",
               description="add"),
    ])
    assert "stunned" in get_actor().conditions
    apply_effects([
        Effect(target=get_actor().id, field="conditions_remove", delta="stunned",
               description="remove"),
    ])
    assert "stunned" not in get_actor().conditions


def test_remove_absent_condition_is_noop():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="conditions_remove", delta="invisible",
               description="noop"),
    ])
    assert get_actor().conditions == []


# ---------------------------------------------------------------------------
# Unit: scene time
# ---------------------------------------------------------------------------

def test_time_advances():
    assert get_scene().time == 0
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=1, description="tick"),
    ])
    assert get_scene().time == 1


def test_time_accumulates():
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=3, description="long"),
    ])
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=2, description="more"),
    ])
    assert get_scene().time == 5


# ---------------------------------------------------------------------------
# Unit: unknown effects are silently skipped
# ---------------------------------------------------------------------------

def test_unknown_target_skipped():
    create_default_actor()
    apply_effects([
        Effect(target="nobody", field="hp", delta=-1, description="ghost"),
    ])
    assert get_actor().hp == 12


def test_unknown_field_skipped():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="xp", delta=100, description="nope"),
    ])
    # No crash; actor unchanged
    assert get_actor().hp == 12


# ---------------------------------------------------------------------------
# Unit: reset
# ---------------------------------------------------------------------------

def test_reset_restores_state():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=-5, description="dmg"),
        Effect(target=get_actor().id, field="conditions_add", delta="poisoned",
               description="add"),
        Effect(target=get_scene().id, field="time", delta=3, description="tick"),
    ])
    append_narrative_history(NarrativeHistoryEntry(
        action_summary="Aldric forces a stuck chest",
        resolution_summary={"outcome": "failure"},
        narration_summary="The chest holds fast.",
    ))
    reset_state()
    assert get_actor() is None
    assert get_scene().time == 0
    assert get_narrative_history() == []


# ---------------------------------------------------------------------------
# Integration: bootstrap reflects mutations
# ---------------------------------------------------------------------------

def test_bootstrap_reflects_hp_change():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="hp", delta=-4, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.actor.hp == 8


def test_bootstrap_reflects_conditions():
    create_default_actor()
    apply_effects([
        Effect(target=get_actor().id, field="conditions_add", delta="poisoned",
               description="test"),
    ])
    state = get_bootstrap_state()
    assert "poisoned" in state.actor.conditions


def test_bootstrap_reflects_time():
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=2, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.scene.time == 2


def test_narrative_context_applies_entry_and_char_limits():
    create_default_actor()
    for idx in range(6):
        append_narrative_history(NarrativeHistoryEntry(
            action_summary=f"Action {idx}",
            resolution_summary={"outcome": "success", "index": idx},
            narration_summary="x" * 120,
        ))

    context = get_narrative_context(max_entries=5, max_chars=450)

    assert len(context) < 5
    assert context[-1].action_summary == "Action 5"
    assert sum(len(entry.model_dump_json()) for entry in context) <= 450


# ---------------------------------------------------------------------------
# Integration: /action endpoint mutates state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_action_check_advances_time(client):
    """Any check (not auto-success) should advance scene time by 1."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "arm wrestle the barkeep",
                "approach": "use brute force",
                "ability": "str",
                "dc": 10,
            },
            headers={"X-Session-Id": session_id},
        )
    assert get_scene(session_id=session_id).time == 1


@pytest.mark.asyncio
async def test_failed_physical_check_reduces_hp(client):
    """A failed STR/DEX/CON check should cost 1 HP."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        # Force failure with impossibly high DC
        resp = await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "lift the immovable boulder",
                "approach": "push with all strength",
                "ability": "str",
                "dc": 99,
            },
            headers={"X-Session-Id": session_id},
        )
    assert resp.json()["outcome"] == "failure"
    # HP reduced by 1 due to failed physical check
    assert get_actor(session_id=session_id).hp == 11


@pytest.mark.asyncio
async def test_auto_success_does_not_mutate(client):
    """Auto-success actions should not change HP or time."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "look around the tavern",
                "approach": "casually look at the patrons",
            },
            headers={"X-Session-Id": session_id},
        )
    assert get_actor(session_id=session_id).hp == 12
    assert get_scene(session_id=session_id).time == 0


@pytest.mark.asyncio
async def test_bootstrap_endpoint_shows_live_state(client):
    """GET /state/bootstrap should reflect mutations from prior actions."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        # Deal damage
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "lift the immovable boulder",
                "approach": "push with all strength",
                "ability": "str",
                "dc": 99,
            },
            headers={"X-Session-Id": session_id},
        )
        # Fetch bootstrap
        resp = await c.get("/state/bootstrap", headers={"X-Session-Id": session_id})
    data = resp.json()
    assert data["actor"]["hp"] == 11
    assert data["scene"]["time"] == 1
    assert len(data["narrative_history"]) == 1
    assert data["narrative_history"][0]["action_summary"].startswith("Aldric attempts")


# ---------------------------------------------------------------------------
# Integration: /state/reset endpoint
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_endpoint_restores_initial_state(client):
    """POST /state/reset should restore actor and scene to initial values."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        # Mutate state: damage HP, add condition, advance time
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "lift the immovable boulder",
                "approach": "push with all strength",
                "ability": "str",
                "dc": 99,
            },
            headers={"X-Session-Id": session_id},
        )
        apply_effects([
            Effect(target=get_actor(session_id=session_id).id, field="conditions_add", delta="exhausted",
                   description="test"),
        ], session_id=session_id)
        # Verify state is mutated
        assert get_actor(session_id=session_id).hp == 11
        assert "exhausted" in get_actor(session_id=session_id).conditions
        assert get_scene(session_id=session_id).time == 1

        # Call reset endpoint
        resp = await c.post("/state/reset", headers={"X-Session-Id": session_id})

        # Verify response status
        assert resp.status_code == 200

        # Verify state is restored (no actor after reset)
        assert get_actor(session_id=session_id) is None
        assert get_scene(session_id=session_id).time == 0
        assert get_narrative_history(session_id=session_id) == []


@pytest.mark.asyncio
async def test_reset_endpoint_returns_fresh_bootstrap(client):
    """POST /state/reset should return the reset bootstrap state."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        actor_id = get_actor(session_id=session_id).id
        # Mutate state
        apply_effects([
            Effect(target=actor_id, field="hp", delta=-7, description="dmg"),
            Effect(target=get_scene(session_id=session_id).id, field="time", delta=5, description="tick"),
        ], session_id=session_id)

        # Call reset and check response
        resp = await c.post("/state/reset", headers={"X-Session-Id": session_id})
        data = resp.json()

        # Response should contain fresh initial state (no actor)
        assert data["actor"] is None
        assert data["scene"]["time"] == 0
        assert data["scene"]["id"] == "character-creation-01"


@pytest.mark.asyncio
async def test_reset_clears_accumulated_mutations(client):
    """Multiple mutations followed by reset should all be cleared."""
    from tests.conftest import create_session_and_character
    async with client as c:
        session_id = await create_session_and_character(c)
        # Apply multiple mutations
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "arm wrestle",
                "approach": "use brute force",
                "ability": "str",
                "dc": 10,
            },
            headers={"X-Session-Id": session_id},
        )
        await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "another action",
                "approach": "try hard",
                "ability": "dex",
                "dc": 99,
            },
            headers={"X-Session-Id": session_id},
        )
        apply_effects([
            Effect(target=get_actor(session_id=session_id).id, field="conditions_add", delta="stunned",
                   description="test"),
            Effect(target=get_actor(session_id=session_id).id, field="conditions_add", delta="poisoned",
                   description="test"),
        ], session_id=session_id)

        # Verify multiple mutations applied
        assert get_actor(session_id=session_id).hp < 12  # Some damage from failed check
        assert len(get_actor(session_id=session_id).conditions) == 2
        assert get_scene(session_id=session_id).time >= 2

        # Reset
        await c.post("/state/reset", headers={"X-Session-Id": session_id})

        # All cleared
        assert get_actor(session_id=session_id) is None
        assert get_scene(session_id=session_id).time == 0

"""Tests for in-memory state mutation after action resolution."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.models.action import Effect
from src.models.state import CharacterClass, CharacterCreateRequest, NarrativeHistoryEntry
from src.state import (
    apply_effects,
    append_narrative_history,
    create_character,
    get_actor,
    get_bootstrap_state,
    get_narrative_context,
    get_narrative_history,
    get_scene,
    reset_state,
    set_current_session,
    reset_current_session,
)


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
def default_actor():
    """Create a default actor for unit tests."""
    create_character(CharacterCreateRequest(
        name="Aldric",
        character_class=CharacterClass.WARRIOR,
        ability_generation="standard_array",
    ))
    return get_actor()


async def _create_character_via_api(client: AsyncClient, name: str = "Aldric") -> str:
    """Create a character via API and return session_id."""
    resp = await client.post("/character/create", json={
        "name": name,
        "character_class": "warrior",
        "ability_generation": "standard_array",
    })
    assert resp.status_code == 200
    session_id = resp.headers.get("x-session-id")
    if not session_id:
        bootstrap = await client.get("/state/bootstrap")
        session_id = bootstrap.json()["session_id"]
    return session_id


# ---------------------------------------------------------------------------
# Unit: apply_effects on actor HP
# ---------------------------------------------------------------------------

def test_hp_damage(default_actor):
    assert get_actor().hp == 12
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=-3, description="test"),
    ])
    assert get_actor().hp == 9


def test_hp_heal(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=-5, description="dmg"),
    ])
    assert get_actor().hp == 7
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=2, description="heal"),
    ])
    assert get_actor().hp == 9


def test_hp_does_not_exceed_max(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=100, description="overheal"),
    ])
    assert get_actor().hp == default_actor.hp_max  # hp_max


def test_hp_does_not_go_below_zero(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=-999, description="overkill"),
    ])
    assert get_actor().hp == 0


# ---------------------------------------------------------------------------
# Unit: conditions
# ---------------------------------------------------------------------------

def test_add_condition(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="conditions_add", delta="frightened",
               description="test"),
    ])
    assert "frightened" in get_actor().conditions


def test_add_duplicate_condition_is_idempotent(default_actor):
    eff = Effect(target=default_actor.id, field="conditions_add", delta="poisoned",
                 description="test")
    apply_effects([eff, eff])
    assert get_actor().conditions.count("poisoned") == 1


def test_remove_condition(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="conditions_add", delta="stunned",
               description="add"),
    ])
    assert "stunned" in get_actor().conditions
    apply_effects([
        Effect(target=default_actor.id, field="conditions_remove", delta="stunned",
               description="remove"),
    ])
    assert "stunned" not in get_actor().conditions


def test_remove_absent_condition_is_noop(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="conditions_remove", delta="invisible",
               description="noop"),
    ])
    assert get_actor().conditions == []


# ---------------------------------------------------------------------------
# Unit: scene time
# ---------------------------------------------------------------------------

def test_time_advances(default_actor):
    assert get_scene().time == 0
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=1, description="tick"),
    ])
    assert get_scene().time == 1


def test_time_accumulates(default_actor):
    scene_id = get_scene().id
    apply_effects([
        Effect(target=scene_id, field="time", delta=3, description="long"),
    ])
    apply_effects([
        Effect(target=scene_id, field="time", delta=2, description="more"),
    ])
    assert get_scene().time == 5


# ---------------------------------------------------------------------------
# Unit: unknown effects are silently skipped
# ---------------------------------------------------------------------------

def test_unknown_target_skipped(default_actor):
    apply_effects([
        Effect(target="nobody", field="hp", delta=-1, description="ghost"),
    ])
    assert get_actor().hp == default_actor.hp


def test_unknown_field_skipped(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="xp", delta=100, description="nope"),
    ])
    # No crash; actor unchanged
    assert get_actor().hp == default_actor.hp


# ---------------------------------------------------------------------------
# Unit: reset
# ---------------------------------------------------------------------------

def test_reset_restores_state(default_actor):
    actor_id = default_actor.id
    scene_id = get_scene().id
    apply_effects([
        Effect(target=actor_id, field="hp", delta=-5, description="dmg"),
        Effect(target=actor_id, field="conditions_add", delta="poisoned",
               description="add"),
        Effect(target=scene_id, field="time", delta=3, description="tick"),
    ])
    append_narrative_history(NarrativeHistoryEntry(
        action_summary="Aldric forces a stuck chest",
        resolution_summary={"outcome": "failure"},
        narration_summary="The chest holds fast.",
    ))
    reset_state()
    create_character(CharacterCreateRequest(
        name="Aldric",
        character_class=CharacterClass.WARRIOR,
        ability_generation="standard_array",
    ))
    assert get_actor().hp == 12
    assert get_actor().conditions == []
    assert get_scene().time == 0
    assert get_narrative_history() == []


# ---------------------------------------------------------------------------
# Integration: bootstrap reflects mutations
# ---------------------------------------------------------------------------

def test_bootstrap_reflects_hp_change(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="hp", delta=-4, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.actor.hp == default_actor.hp - 4


def test_bootstrap_reflects_conditions(default_actor):
    apply_effects([
        Effect(target=default_actor.id, field="conditions_add", delta="poisoned",
               description="test"),
    ])
    state = get_bootstrap_state()
    assert "poisoned" in state.actor.conditions


def test_bootstrap_reflects_time(default_actor):
    apply_effects([
        Effect(target=get_scene().id, field="time", delta=2, description="test"),
    ])
    state = get_bootstrap_state()
    assert state.scene.time == 2


def test_narrative_context_applies_entry_and_char_limits():
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
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle the barkeep",
            "approach": "use brute force",
            "ability": "str",
            "dc": 10,
        }, headers={"X-Session-Id": session_id})
    token = set_current_session(session_id)
    try:
        assert get_scene().time == 1
    finally:
        reset_current_session(token)


@pytest.mark.asyncio
async def test_failed_physical_check_reduces_hp(client):
    """A failed STR/DEX/CON check should cost 1 HP."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        # Force failure with impossibly high DC
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        }, headers={"X-Session-Id": session_id})
    assert resp.json()["outcome"] == "failure"
    token = set_current_session(session_id)
    try:
        assert get_actor().hp == 11  # 12 - 1
    finally:
        reset_current_session(token)


@pytest.mark.asyncio
async def test_auto_success_does_not_mutate(client):
    """Auto-success actions should not change HP or time."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "look around the tavern",
            "approach": "casually look at the patrons",
        }, headers={"X-Session-Id": session_id})
    token = set_current_session(session_id)
    try:
        assert get_actor().hp == 12
        assert get_scene().time == 0
    finally:
        reset_current_session(token)


@pytest.mark.asyncio
async def test_bootstrap_endpoint_shows_live_state(client):
    """GET /state/bootstrap should reflect mutations from prior actions."""
    async with client as c:
        session_id = await _create_character_via_api(c)
        # Deal damage
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        }, headers={"X-Session-Id": session_id})
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
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        # Mutate state: damage HP, add condition, advance time
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "lift the immovable boulder",
            "approach": "push with all strength",
            "ability": "str",
            "dc": 99,
        }, headers={"X-Session-Id": session_id})
        
        token = set_current_session(session_id)
        try:
            actor_id = get_actor().id
            apply_effects([
                Effect(target=actor_id, field="conditions_add", delta="exhausted",
                       description="test"),
            ])
            # Verify state is mutated
            assert get_actor().hp == 11
            assert "exhausted" in get_actor().conditions
            assert get_scene().time == 1
        finally:
            reset_current_session(token)

        # Call reset endpoint
        resp = await c.post("/state/reset", headers={"X-Session-Id": session_id})

        # Verify response status
        assert resp.status_code == 200

        # Verify state is restored - need to recreate character since reset clears it
        create_character(CharacterCreateRequest(
            name="Aldric",
            character_class=CharacterClass.WARRIOR,
            ability_generation="standard_array",
        ), session_id=session_id)
        token = set_current_session(session_id)
        try:
            assert get_actor().hp == 12
            assert get_actor().conditions == []
            assert get_scene().time == 0
            assert get_narrative_history() == []
        finally:
            reset_current_session(token)


@pytest.mark.asyncio
async def test_reset_endpoint_returns_fresh_bootstrap(client):
    """POST /state/reset should return the reset bootstrap state."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        
        token = set_current_session(session_id)
        try:
            # Mutate state
            apply_effects([
                Effect(target=get_actor().id, field="hp", delta=-7, description="dmg"),
                Effect(target=get_scene().id, field="time", delta=5, description="tick"),
            ])
        finally:
            reset_current_session(token)

        # Call reset and check response
        resp = await c.post("/state/reset", headers={"X-Session-Id": session_id})
        data = resp.json()

        # Response should contain fresh initial state (no actor after reset)
        # After reset, there is no actor until created again
        assert data["actor"] is None
        assert data["scene"]["time"] == 0


@pytest.mark.asyncio
async def test_reset_clears_accumulated_mutations(client):
    """Multiple mutations followed by reset should all be cleared."""
    from src.state import set_current_session, reset_current_session
    async with client as c:
        session_id = await _create_character_via_api(c)
        # Apply multiple mutations
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "arm wrestle",
            "approach": "use brute force",
            "ability": "str",
            "dc": 10,
        }, headers={"X-Session-Id": session_id})
        await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "another action",
            "approach": "try hard",
            "ability": "dex",
            "dc": 99,
        }, headers={"X-Session-Id": session_id})
        
        token = set_current_session(session_id)
        try:
            actor_id = get_actor().id
            apply_effects([
                Effect(target=actor_id, field="conditions_add", delta="stunned",
                       description="test"),
                Effect(target=actor_id, field="conditions_add", delta="poisoned",
                       description="test"),
            ])

            # Verify multiple mutations applied
            assert get_actor().hp < 12  # Some damage from failed check
            assert len(get_actor().conditions) == 2
            assert get_scene().time >= 2
        finally:
            reset_current_session(token)

        # Reset
        await c.post("/state/reset", headers={"X-Session-Id": session_id})

        # All cleared - recreate character for verification
        create_character(CharacterCreateRequest(
            name="Aldric",
            character_class=CharacterClass.WARRIOR,
            ability_generation="standard_array",
        ), session_id=session_id)
        token = set_current_session(session_id)
        try:
            assert get_actor().hp == 12
            assert get_actor().conditions == []
            assert get_scene().time == 0
        finally:
            reset_current_session(token)

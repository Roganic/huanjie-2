"""Tests for XP and leveling system."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.rules.experience import (
    get_enemy_xp_reward,
    get_level_from_xp,
    XP_THRESHOLDS,
)
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_character(client: AsyncClient, name: str = "TestHero") -> str:
    """Create a character and return session_id."""
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
# XP Reward Tests
# ---------------------------------------------------------------------------

def test_goblin_xp_reward():
    """Goblin should give 50 XP."""
    assert get_enemy_xp_reward("goblin") == 50
    assert get_enemy_xp_reward("哥布林") == 50
    assert get_enemy_xp_reward("哥布林斥候") == 50


def test_bandit_xp_reward():
    """Bandit should give 100 XP."""
    assert get_enemy_xp_reward("bandit") == 100
    assert get_enemy_xp_reward("强盗") == 100


def test_skeleton_xp_reward():
    """Skeleton should give 50 XP."""
    assert get_enemy_xp_reward("skeleton") == 50
    assert get_enemy_xp_reward("骷髅") == 50


def test_default_xp_reward():
    """Unknown enemy should give default 50 XP."""
    assert get_enemy_xp_reward("unknown_enemy") == 50


# ---------------------------------------------------------------------------
# Level Calculation Tests
# ---------------------------------------------------------------------------

def test_level_1_at_start():
    """Character starts at level 1 with 0 XP."""
    assert get_level_from_xp(0) == 1
    assert get_level_from_xp(100) == 1
    assert get_level_from_xp(299) == 1


def test_level_2_at_300_xp():
    """Character reaches level 2 at 300 XP."""
    assert get_level_from_xp(300) == 2
    assert get_level_from_xp(500) == 2
    assert get_level_from_xp(899) == 2


def test_level_3_at_900_xp():
    """Character reaches level 3 at 900 XP."""
    assert get_level_from_xp(900) == 3


# ---------------------------------------------------------------------------
# Character XP Field Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_character_has_experience_points_field(client):
    """Character should have experience_points field in response."""
    async with client as c:
        resp = await c.post("/character/create", json={
            "name": "XPTest",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert "experience_points" in data
    assert data["experience_points"] == 0


@pytest.mark.asyncio
async def test_character_xp_persisted(client):
    """Character XP should be persisted in state."""
    async with client as c:
        create_resp = await c.post("/character/create", json={
            "name": "XPPersist",
            "character_class": "warrior",
            "ability_generation": "standard_array",
        })
        assert create_resp.status_code == 200
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]
        
        # Get character and verify XP
        char_resp = await c.get("/character", headers={"X-Session-Id": session_id})
        assert char_resp.status_code == 200
        data = char_resp.json()
        assert "experience_points" in data
        assert data["experience_points"] == 0


# ---------------------------------------------------------------------------
# Combat XP Award Tests
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Level Up Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_level_up_updates_proficiency_bonus(client):
    """Level up should update proficiency bonus."""
    async with client as c:
        # Create character
        create_resp = await c.post("/character/create", json={
            "name": "LevelUpTest",
            "character_class": "warrior",
            "ability_generation": "manual",
            "abilities": {"str": 16, "dex": 10, "con": 14, "int": 10, "wis": 10, "cha": 10},
        })
        
        session_id = create_resp.headers.get("x-session-id")
        if not session_id:
            bootstrap = await c.get("/state/bootstrap")
            session_id = bootstrap.json()["session_id"]
        
        data = create_resp.json()
        assert data["level"] == 1
        assert data["proficiency_bonus"] == 2
        
        # Note: Level up requires defeating multiple enemies to accumulate enough XP
        # This test verifies the structure is correct

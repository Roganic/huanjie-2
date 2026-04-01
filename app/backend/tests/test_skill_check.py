"""Tests for skill check resolution (proficient vs non-proficient)."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.state import get_actor, reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _create_session_and_character(client, name="Aldric", character_class="warrior"):
    """Helper to create a session and character."""
    # Create session via state/bootstrap endpoint
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


# ---------------------------------------------------------------------------
# Skill check - proficient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_proficient_skill_check_structure(client):
    """Proficient skill check should include correct bonus breakdown."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "climb the wall",
                "approach": "use my athletic training",
                "action_type": "skill_check",
                "skill": "athletics",  # Aldric (warrior) is proficient in athletics
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Should be a check resolution
        assert data["resolution_type"] == "check"
        assert data["check"] is not None
        
        check = data["check"]
        # Warrior: STR 15 (+2), proficient in athletics (+2 prof bonus) = +4 total
        assert check["ability"] == "str"
        assert check["skill_name"] == "athletics"
        assert check["modifier"] == 2  # STR 15 -> +2
        assert check["proficiency_bonus"] == 2  # Proficient: +2
        assert check["total"] == check["roll"] + 2 + 2
        assert "roll" in check
        assert 1 <= check["roll"] <= 20


@pytest.mark.asyncio
async def test_proficient_skill_check_uses_ability_modifier(client):
    """Proficient skill check should use governing ability modifier."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "tavern-01",
                "actor": "Aldric",
                "intent": "intimidate the thug",
                "approach": "stare menacingly",
                "action_type": "skill_check",
                "skill": "intimidation",  # CHA-based, Aldric is proficient
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        check = data["check"]
        
        # Intimidation uses CHA, Warrior has CHA 10 (+0), but proficient (+2)
        assert check["ability"] == "cha"
        assert check["modifier"] == 0  # CHA 10 -> +0
        assert check["proficiency_bonus"] == 2  # Proficient


# ---------------------------------------------------------------------------
# Skill check - non-proficient
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_proficient_skill_check_no_proficiency_bonus(client):
    """Non-proficient skill check should only use ability modifier."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "forest-01",
                "actor": "Aldric",
                "intent": "sneak past the guards",
                "approach": "move quietly through shadows",
                "action_type": "skill_check",
                "skill": "stealth",  # DEX-based, Aldric is NOT proficient
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        check = data["check"]
        # Aldric: DEX 13 (+1), NOT proficient in stealth = +1 total
        assert check["ability"] == "dex"
        assert check["skill_name"] == "stealth"
        assert check["modifier"] == 1  # DEX 13 -> +1
        assert check["proficiency_bonus"] == 0  # NOT proficient
        assert check["total"] == check["roll"] + 1 + 0


@pytest.mark.asyncio
async def test_non_proficient_arcana_uses_int(client):
    """Non-proficient arcana check should use INT modifier only."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "library-01",
                "actor": "Aldric",
                "intent": "identify the magical runes",
                "approach": "study the symbols",
                "action_type": "skill_check",
                "skill": "arcana",  # INT-based, Aldric is NOT proficient
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        check = data["check"]
        
        # Arcana uses INT, Aldric has INT 8 (-1), not proficient
        assert check["ability"] == "int"
        assert check["modifier"] == -1  # INT 8 -> -1
        assert check["proficiency_bonus"] == 0  # NOT proficient


# ---------------------------------------------------------------------------
# Skill check via skill field only (no explicit action_type)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_field_auto_routes_to_skill_check(client):
    """Providing skill field should auto-route to skill check resolver."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "track the beast",
                "approach": "look for footprints",
                "skill": "survival",  # Should auto-trigger skill check
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # Aldric is proficient in survival
        check = data["check"]
        assert check["skill_name"] == "survival"
        assert check["ability"] == "wis"
        assert check["proficiency_bonus"] == 2  # Proficient


# ---------------------------------------------------------------------------
# Skill check with explicit DC
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_check_with_explicit_dc(client):
    """Skill check should respect explicit DC parameter."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "cliff-01",
                "actor": "Aldric",
                "intent": "scale the cliff",
                "approach": "find handholds",
                "action_type": "skill_check",
                "skill": "athletics",
                "dc": 20,  # Hard DC
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["check"]["dc"] == 20


# ---------------------------------------------------------------------------
# Skill check with advantage/disadvantage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_check_with_advantage(client):
    """Skill check should support advantage."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "climb quickly",
                "approach": "use ropes and gear",
                "action_type": "skill_check",
                "skill": "athletics",
                "advantage": True,
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["check"]["advantage"] is True


@pytest.mark.asyncio
async def test_skill_check_with_disadvantage(client):
    """Skill check should support disadvantage."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "climb while injured",
                "approach": "push through the pain",
                "action_type": "skill_check",
                "skill": "athletics",
                "advantage": False,  # Disadvantage
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["check"]["advantage"] is False


# ---------------------------------------------------------------------------
# Rogue skills - proficient in different skills
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rogue_proficient_in_stealth(client):
    """Rogue should be proficient in stealth and get correct bonus."""
    async with client as c:
        session_id = await _create_session_and_character(c, name="Shadow", character_class="rogue")
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Shadow",
                "intent": "hide in shadows",
                "approach": "blend into darkness",
                "action_type": "skill_check",
                "skill": "stealth",  # Rogue is proficient
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        check = data["check"]
        
        # Rogue: DEX 15 (+2), proficient in stealth (+2) = +4
        assert check["ability"] == "dex"
        assert check["proficiency_bonus"] == 2  # Proficient


# ---------------------------------------------------------------------------
# Skill check outcome validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_skill_check_success_on_high_roll(client):
    """Skill check should succeed when total >= DC."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "do something easy",
                "approach": "try my best",
                "action_type": "skill_check",
                "skill": "athletics",
                "dc": 1,  # Very easy, should almost always succeed
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        # With DC 1 and +5 bonus (STR +3, prof +2), even roll 1 gives total 6 >= 1
        assert data["outcome"] == "success"


@pytest.mark.asyncio
async def test_skill_check_failure_on_impossible_dc(client):
    """Skill check should fail when total < DC."""
    async with client as c:
        session_id = await _create_session_and_character(c)
        resp = await c.post(
            "/action",
            json={
                "scene_id": "dungeon-01",
                "actor": "Aldric",
                "intent": "do the impossible",
                "approach": "attempt anyway",
                "action_type": "skill_check",
                "skill": "athletics",
                "dc": 50,  # Impossible, even max roll (20) + 5 = 25 < 50
            },
            headers={"X-Session-Id": session_id},
        )
        
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["outcome"] == "failure"

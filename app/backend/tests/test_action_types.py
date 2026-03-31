"""Tests for action type classification and type-specific resolution."""

import pytest
from httpx import ASGITransport, AsyncClient

from src.engine.resolver import classify_action_type, _is_auto_success, _infer_ability, _pick_dc
from src.main import app
from src.models.action import ActionType
from src.state import reset_state


@pytest.fixture(autouse=True)
def _fresh_state():
    """Reset mutable state before every test."""
    reset_state()


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


# -----------------------------------------------------------------------------
# Unit Tests: Action Type Classification
# -----------------------------------------------------------------------------

def test_classify_move_actions():
    """Movement keywords should be classified as MOVE."""
    assert classify_action_type("walk to the door", "carefully") == ActionType.MOVE
    assert classify_action_type("run away", "quickly") == ActionType.MOVE
    assert classify_action_type("climb the wall", "using rope") == ActionType.MOVE
    assert classify_action_type("jump the gap", "with a leap") == ActionType.MOVE
    assert classify_action_type("sneak past", "silently") == ActionType.MOVE


def test_classify_attack_actions():
    """Attack keywords should be classified as ATTACK."""
    assert classify_action_type("attack the goblin", "with my sword") == ActionType.ATTACK
    assert classify_action_type("shoot the target", "with bow") == ActionType.ATTACK
    assert classify_action_type("cast fireball", "at enemies") == ActionType.ATTACK
    assert classify_action_type("stab the orc", "in the back") == ActionType.ATTACK


def test_classify_social_actions():
    """Social keywords should be classified as SOCIAL."""
    assert classify_action_type("persuade the guard", "to let us pass") == ActionType.SOCIAL
    assert classify_action_type("deceive the merchant", "about the price") == ActionType.SOCIAL
    assert classify_action_type("intimidate the bandit", "with threats") == ActionType.SOCIAL
    assert classify_action_type("charm the noble", "with wit") == ActionType.SOCIAL


def test_classify_explore_actions():
    """Exploration keywords should be classified as EXPLORE."""
    assert classify_action_type("search the room", "for clues") == ActionType.EXPLORE
    assert classify_action_type("investigate the scene", "carefully") == ActionType.EXPLORE
    assert classify_action_type("look for traps", "on the door") == ActionType.EXPLORE
    assert classify_action_type("listen for enemies", "behind the door") == ActionType.EXPLORE


def test_classify_interact_actions():
    """Interaction keywords should be classified as INTERACT."""
    assert classify_action_type("open the chest", "carefully") == ActionType.INTERACT
    assert classify_action_type("pick up the key", "from the table") == ActionType.INTERACT
    assert classify_action_type("unlock the door", "with lockpicks") == ActionType.INTERACT
    assert classify_action_type("use the lever", "to open gate") == ActionType.INTERACT


def test_attack_takes_priority_over_move():
    """Attack keywords should take priority over move keywords."""
    # "charge" is in both contexts
    assert classify_action_type("charge the enemy", "with sword") == ActionType.ATTACK


def test_social_takes_priority_over_explore():
    """Social keywords should take priority when both match."""
    # Questioning someone is social, not exploration
    assert classify_action_type("question the suspect", "about the crime") == ActionType.SOCIAL


# -----------------------------------------------------------------------------
# Unit Tests: Auto-Success Rules by Type
# -----------------------------------------------------------------------------

def test_move_auto_success_trivial():
    """Trivial movement should auto-succeed."""
    assert _is_auto_success(ActionType.MOVE, "walk to the door", "casually") is True
    assert _is_auto_success(ActionType.MOVE, "sit down", "on the chair") is True


def test_move_no_auto_success_with_obstacles():
    """Movement with obstacles should not auto-succeed."""
    assert _is_auto_success(ActionType.MOVE, "climb the wall", "while guards watch") is False
    assert _is_auto_success(ActionType.MOVE, "sneak past", "hidden enemies") is False


def test_attack_never_auto_success():
    """Attacks should never auto-succeed."""
    assert _is_auto_success(ActionType.ATTACK, "attack", "with sword") is False
    assert _is_auto_success(ActionType.ATTACK, "simple attack", "easy target") is False


def test_social_never_auto_success():
    """Social actions should never auto-succeed."""
    assert _is_auto_success(ActionType.SOCIAL, "ask about the weather", "casually") is False
    assert _is_auto_success(ActionType.SOCIAL, "say hello", "friendly") is False


def test_interact_auto_success_trivial():
    """Trivial interactions should auto-succeed."""
    assert _is_auto_success(ActionType.INTERACT, "pick up the book", "from table") is True
    assert _is_auto_success(ActionType.INTERACT, "put down the bag", "gently") is True


def test_interact_no_auto_success_locked():
    """Interacting with locked objects should not auto-succeed."""
    assert _is_auto_success(ActionType.INTERACT, "open the locked chest", "carefully") is False
    assert _is_auto_success(ActionType.INTERACT, "unlock the door", "with key") is False


def test_explore_auto_success_trivial():
    """Trivial exploration should auto-succeed."""
    assert _is_auto_success(ActionType.EXPLORE, "look around", "the room") is True
    assert _is_auto_success(ActionType.EXPLORE, "look at the painting", "briefly") is True


def test_explore_no_auto_success_hidden():
    """Searching for hidden things should not auto-succeed."""
    assert _is_auto_success(ActionType.EXPLORE, "search for hidden door", "carefully") is False
    assert _is_auto_success(ActionType.EXPLORE, "look for secret", "passage") is False


# -----------------------------------------------------------------------------
# Unit Tests: Ability Inference by Type
# -----------------------------------------------------------------------------

def test_infer_ability_attack_melee():
    """Melee attacks should default to STR."""
    assert _infer_ability(ActionType.ATTACK, "attack", "with sword") == "str"
    assert _infer_ability(ActionType.ATTACK, "stab", "with dagger") == "str"


def test_infer_ability_attack_ranged():
    """Ranged attacks should use DEX."""
    assert _infer_ability(ActionType.ATTACK, "shoot", "with bow") == "dex"
    assert _infer_ability(ActionType.ATTACK, "throw", "a knife") == "dex"


def test_infer_ability_attack_spell():
    """Spell attacks should use INT or CHA."""
    assert _infer_ability(ActionType.ATTACK, "cast spell", "fireball") == "int"
    assert _infer_ability(ActionType.ATTACK, "use magic", "charm") == "cha"


def test_infer_ability_social():
    """Social actions should use CHA by default."""
    assert _infer_ability(ActionType.SOCIAL, "persuade", "the guard") == "cha"
    assert _infer_ability(ActionType.SOCIAL, "intimidate", "the bandit") == "cha"


def test_infer_ability_social_wis():
    """Insight-based social uses WIS."""
    assert _infer_ability(ActionType.SOCIAL, "calm", "empathize") == "wis"


def test_infer_ability_explore():
    """Exploration should use WIS or INT."""
    assert _infer_ability(ActionType.EXPLORE, "perceive", "enemies") == "wis"
    assert _infer_ability(ActionType.EXPLORE, "investigate", "scene") == "int"


def test_infer_ability_move():
    """Movement should use DEX or STR."""
    assert _infer_ability(ActionType.MOVE, "sneak", "quietly") == "dex"
    assert _infer_ability(ActionType.MOVE, "climb", "wall") == "str"


def test_infer_ability_interact():
    """Interaction should use DEX or INT."""
    assert _infer_ability(ActionType.INTERACT, "pick lock", "carefully") == "dex"
    assert _infer_ability(ActionType.INTERACT, "decipher", "rune") == "int"


# -----------------------------------------------------------------------------
# Unit Tests: DC Assignment by Type
# -----------------------------------------------------------------------------

def test_pick_dc_attack():
    """Attacks should default to medium DC."""
    assert _pick_dc(ActionType.ATTACK, "attack", "normally") == 15


def test_pick_dc_attack_special():
    """Special attacks (disarm, trip) should be hard."""
    assert _pick_dc(ActionType.ATTACK, "disarm", "the enemy") == 20


def test_pick_dc_social_hostile():
    """Social against hostile targets should be hard."""
    assert _pick_dc(ActionType.SOCIAL, "persuade", "hostile guard") == 20


def test_pick_dc_social_friendly():
    """Social with friendly targets should be easy."""
    assert _pick_dc(ActionType.SOCIAL, "ask", "friendly merchant") == 10


def test_pick_dc_explore_hidden():
    """Searching for hidden things should be hard."""
    assert _pick_dc(ActionType.EXPLORE, "search", "hidden door") == 20


def test_pick_dc_interact_locked():
    """Interacting with locked objects should be hard."""
    assert _pick_dc(ActionType.INTERACT, "unlock", "magical lock") == 20


def test_pick_dc_override_keywords():
    """Explicit difficulty keywords should override type defaults."""
    assert _pick_dc(ActionType.MOVE, "make easy jump", "simple") == 10
    assert _pick_dc(ActionType.MOVE, "hard climb", "difficult") == 20


# -----------------------------------------------------------------------------
# Integration Tests: API Returns Action Type
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_api_returns_action_type_move(client):
    """API response should include action_type for move actions."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "walk to the bar",
            "approach": "casually",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "move"


@pytest.mark.asyncio
async def test_api_returns_action_type_attack(client):
    """API response should include action_type for attack actions."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "with my sword",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "attack"


@pytest.mark.asyncio
async def test_api_returns_action_type_social(client):
    """API response should include action_type for social actions."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "persuade the bartender",
            "approach": "to give us a discount",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "social"


@pytest.mark.asyncio
async def test_api_returns_action_type_explore(client):
    """API response should include action_type for explore actions."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "search the room",
            "approach": "for hidden treasure",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "explore"


@pytest.mark.asyncio
async def test_api_returns_action_type_interact(client):
    """API response should include action_type for interact actions."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "unlock the chest",
            "approach": "with lockpicks",
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "interact"


@pytest.mark.asyncio
async def test_api_explicit_action_type_override(client):
    """Explicit action_type in request should be respected."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "do something",  # Vague, would be UNKNOWN
            "approach": "mysteriously",
            "action_type": "attack",  # Explicit override
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "attack"


# -----------------------------------------------------------------------------
# Integration Tests: Type-Specific Effects
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attack_success_deals_damage(client):
    """Successful attacks should deal damage effects."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "attack the enemy",
            "approach": "powerful strike",
            "dc": 5,  # Easy to succeed
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "attack"
    assert data["outcome"] == "success"
    # Should have damage effect
    damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
    assert len(damage_effects) > 0


@pytest.mark.asyncio
async def test_social_failure_creates_suspicion(client):
    """Failed social actions should create suspicion."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "tavern-01",
            "actor": "Aldric",
            "intent": "deceive the guard",
            "approach": "with a lie",
            "dc": 99,  # Impossible to succeed
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "social"
    assert data["outcome"] == "failure"
    # Should have suspicion effect
    suspicion_effects = [e for e in data["effects"] if e["delta"] == "suspicious"]
    assert len(suspicion_effects) > 0


@pytest.mark.asyncio
async def test_move_failure_with_climb_causes_damage(client):
    """Failed climb/jump should cause damage."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "climb the wall",
            "approach": "leap quickly",
            "dc": 99,  # Impossible
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "move"
    assert data["outcome"] == "failure"
    # Should have damage from fall
    damage_effects = [e for e in data["effects"] if e["field"] == "hp" and e["delta"] < 0]
    assert len(damage_effects) > 0


@pytest.mark.asyncio
async def test_explore_success_gains_information(client):
    """Successful exploration should grant information."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "search for clues",
            "approach": "investigate carefully",
            "dc": 5,  # Easy
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_type"] == "explore"
    assert data["outcome"] == "success"
    # Should have informed effect
    info_effects = [e for e in data["effects"] if e["delta"] == "informed"]
    assert len(info_effects) > 0


@pytest.mark.asyncio
async def test_narration_includes_action_type(client):
    """Narration should reference the action type."""
    async with client as c:
        resp = await c.post("/action", json={
            "scene_id": "dungeon-01",
            "actor": "Aldric",
            "intent": "attack the goblin",
            "approach": "with sword",
        })
    assert resp.status_code == 200
    data = resp.json()
    # Narration should mention the action type
    narration = data["narration"].lower()
    assert "attack" in narration

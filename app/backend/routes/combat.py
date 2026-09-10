"""Combat API endpoints for full combat flow management."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.models.action import (
    ActionRequest,
    ActionType,
    Effect,
    Outcome,
)
from src.models.state import Scene, InventoryItem, ItemType, DEFAULT_WEAPONS, DEFAULT_ARMORS, DEFAULT_CONSUMABLES
from src.state import (
    get_actor,
    get_enemy,
    get_scene,
    has_character,
    require_bootstrap_state,
    reset_current_session,
    set_combat_scene,
    set_current_session,
    _get_session,
    _SESSION_LOCK,
    _save_session,
)
from src.agent.orchestrator import resolve_action_with_agent
from src.loot import generate_combat_loot
from src.rules.experience import get_enemy_xp_reward, calculate_level_up
from src.rules.calculations import CLASS_HIT_DICE

router = APIRouter(tags=["combat"])


# ---------------------------------------------------------------------------
# Combat State Models
# ---------------------------------------------------------------------------

class CombatParticipant(BaseModel):
    """A participant in combat (player or enemy)."""
    id: str
    name: str
    hp: int
    hp_max: int
    ac: int
    initiative: int
    initiative_roll: int | None = None
    speed: int = 0
    is_player: bool
    type: str = "enemy"  # "player" or "enemy"
    conditions: list[str] = []


class CombatState(BaseModel):
    """Current state of an active combat."""
    combat_id: str
    round_number: int
    turn_index: int
    participants: list[CombatParticipant]
    initiative_order: list[str]  # Ordered list of participant IDs
    current_actor_id: str
    scene: Scene
    status: Literal["active", "victory", "defeat", "escaped"]
    log: list["CombatLogEntry"] = []
    actions_remaining: int = 1
    bonus_action_available: bool = True
    rewards: dict | None = None
    encounter_scene_id: str | None = None
    retreat_scene_id: str | None = None


class CombatLogEntry(BaseModel):
    """A single entry in the combat log."""
    actor_id: str
    action_type: str
    target_id: Optional[str] = None
    hit: Optional[bool] = None
    damage: Optional[int] = None
    narrative: str
    timestamp: int


class StartCombatRequest(BaseModel):
    """Request to start a combat encounter."""
    enemy_config: Optional[dict] = None  # Optional enemy customization
    scene_id: Optional[str] = None
    target_id: Optional[str] = None


class CombatActionRequest(BaseModel):
    """Request to perform a combat action."""
    action_type: str  # "attack", "defend", "skill", "flee"
    target_id: Optional[str] = None
    weapon: Optional[str] = None
    skill: Optional[str] = None
    ability_id: Optional[str] = None


class CombatActionResponse(BaseModel):
    """Response from a combat action."""
    action_type: str
    actor_id: str
    target_id: Optional[str] = None
    hit: Optional[bool] = None
    damage: Optional[int] = None
    sneak_attack_damage: Optional[int] = None
    effects: list[Effect] = []
    narrative: str
    combat_state: CombatState
    outcome: str = "success"
    costs: list[dict] = []
    events: list[dict] = []
    available_actions: list[dict] = []
    xp_gained: int = 0
    loot_gained: list[dict] = []
    level_up: dict | None = None
    combat_ended: bool = False
    victory: bool = False


class EndCombatRequest(BaseModel):
    """Request to end combat (flee or surrender)."""
    reason: Literal["flee", "surrender", "victory", "defeat"]


# ---------------------------------------------------------------------------
# In-memory combat state storage (per session)
# ---------------------------------------------------------------------------

_combats: dict[str, CombatState] = {}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def _roll_initiative(actor) -> int:
    """Roll initiative for an actor (d20 + DEX modifier)."""
    dex_mod = actor.abilities.modifier("dex")
    roll = random.randint(1, 20)
    return roll + dex_mod


def _actor_to_participant(actor, is_player: bool, initiative: int) -> CombatParticipant:
    """Convert an Actor to a CombatParticipant."""
    return CombatParticipant(
        id=actor.id,
        name=actor.name,
        hp=actor.hp,
        hp_max=actor.hp_max,
        ac=actor.ac,
        initiative=initiative,
        initiative_roll=initiative - actor.abilities.modifier("dex"),
        speed=actor.abilities.modifier("dex"),
        is_player=is_player,
        type="player" if is_player else "enemy",
        conditions=actor.conditions or [],
    )


def _get_combat_state(session_id: str) -> Optional[CombatState]:
    """Get combat state for a session."""
    session = _get_session(session_id, create_if_missing=False)
    if session.combat_snapshot is None:
        return None
    return CombatState.model_validate(session.combat_snapshot)


def _set_combat_state(session_id: str, state: CombatState) -> None:
    session = _get_session(session_id, create_if_missing=False)
    session.combat_snapshot = state.model_dump(mode="json")
    _combats[session_id] = state  # compatibility cache; session snapshot is authoritative
    _save_session(session)


def _clear_combat_state(session_id: str) -> None:
    session = _get_session(session_id, create_if_missing=False)
    session.combat_snapshot = None
    _combats.pop(session_id, None)
    _save_session(session)


def _sort_initiative(participants: list[CombatParticipant]) -> list[str]:
    """Sort participants by initiative (highest first)."""
    sorted_parts = sorted(participants, key=lambda p: (-p.initiative, -p.speed, not p.is_player, p.id))
    return [p.id for p in sorted_parts]


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 12) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


async def _stream_combat_response(response: CombatActionResponse) -> AsyncIterator[str]:
    """Stream combat action response with chunked narration."""
    yield _sse_event(
        "start",
        {
            "action_type": response.action_type,
            "actor_id": response.actor_id,
            "target_id": response.target_id,
            "hit": response.hit,
            "damage": response.damage,
        },
    )

    # Stream narrative in chunks
    for chunk in _chunk_text(response.narrative):
        yield _sse_event("chunk", {"field": "narrative", "delta": chunk})
        await asyncio.sleep(0.02)

    yield _sse_event("complete", response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Combat Resolution Functions
# ---------------------------------------------------------------------------

def _resolve_combat_action(
    session_id: str,
    combat: CombatState,
    req: CombatActionRequest,
) -> CombatActionResponse:
    """Resolve a single combat action and update combat state."""
    from src.game.combat_service import execute_turn
    return execute_turn(session_id, combat, req)


def _award_victory_rewards(session_id: str, combat: CombatState, *, persist: bool = True) -> dict | None:
    """Award XP and loot when combat ends in victory."""
    with _SESSION_LOCK:
        session = _get_session(session_id, create_if_missing=False)
        if session is None or session.actor is None:
            return None
        
        if combat.rewards is not None:
            return combat.rewards
        world = session.world_scenes.get(combat.encounter_scene_id)
        if world:
            from src.scene import get_scene_by_id
            from src.content.store import for_session
            original = get_scene_by_id(combat.encounter_scene_id, for_session(session))
            eligible = {n.id for n in original.npcs if n.type == "hostile"} if original else set()
        else:
            eligible = {p.id for p in combat.participants if not p.is_player}
        actor = session.actor
        
        # Find defeated enemies
        defeated_enemies: list[tuple[str, str]] = []
        for p in combat.participants:
            if not p.is_player and p.id in eligible and (not world or p.id not in world.rewarded_ids) and (p.hp <= 0 or "defeated" in p.conditions):
                defeated_enemies.append((p.id, p.name))
        
        if not defeated_enemies:
            combat.rewards = {"xp_gained": 0, "loot_gained": [], "total_xp": actor.experience_points}
            return combat.rewards
        
        # Running content supplies drops and XP; old single-enemy snapshots retain their fallback.
        from src.content.store import for_session
        pack = for_session(session) if world else None
        loot = generate_combat_loot(defeated_enemies, pack=pack) if pack else generate_combat_loot(defeated_enemies)
        loot_items_for_response: list[dict] = []
        inventory_items_to_add: list[InventoryItem] = []
        
        for entry in loot.loot_entries:
            entry_items: list[dict] = []
            for item in entry.items:
                entry_items.append({
                    "name": item.name,
                    "quantity": item.quantity,
                    "description": item.description,
                })
                if pack and item.item_id in pack.items:
                    inventory_item = pack.items[item.item_id].model_copy(deep=True)
                elif item.item_id in DEFAULT_WEAPONS:
                    inventory_item = InventoryItem.from_weapon(DEFAULT_WEAPONS[item.item_id])
                elif item.item_id in DEFAULT_ARMORS:
                    inventory_item = InventoryItem.from_armor(DEFAULT_ARMORS[item.item_id])
                elif item.item_id in DEFAULT_CONSUMABLES:
                    inventory_item = InventoryItem.from_consumable(DEFAULT_CONSUMABLES[item.item_id])
                else:
                    inventory_item = InventoryItem(id=item.item_id, name=item.name,
                                                   type=ItemType.MISC, description=item.description or "战利品")
                inventory_items_to_add.extend(inventory_item.model_copy(deep=True) for _ in range(item.quantity))
            if entry_items:
                loot_items_for_response.append({
                    "enemy_name": entry.enemy_name,
                    "items": entry_items,
                })
        
        # Add items to inventory
        if inventory_items_to_add:
            new_inventory = [*session.actor.inventory, *inventory_items_to_add]
            session.actor = session.actor.model_copy(update={"inventory": new_inventory})
        
        # Get XP reward (use first defeated enemy)
        xp_gained = sum(pack.characters[id].xp_reward for id, _ in defeated_enemies) if pack else sum(get_enemy_xp_reward(name) for _, name in defeated_enemies)
        
        from src.game.progression import grant_experience
        result = {**grant_experience(session, xp_gained), "loot_gained": loot_items_for_response}

        combat.rewards = result
        if world:
            world.rewarded_ids.extend(id for id, _ in defeated_enemies)
        if persist:
            _set_combat_state(session_id, combat)
        return result


def _get_action_intent(req: CombatActionRequest) -> str:
    """Generate intent text from combat action request."""
    if req.action_type == "attack":
        return "attack the enemy"
    elif req.action_type == "defend":
        return "take defensive stance"
    elif req.action_type == "skill":
        return f"use {req.skill or 'skill'}"
    elif req.action_type == "flee":
        return "flee from combat"
    return "act in combat"


def _get_action_approach(req: CombatActionRequest) -> str:
    """Generate approach text from combat action request."""
    if req.action_type == "attack":
        weapon = req.weapon or "weapon"
        return f"attack with {weapon}"
    elif req.action_type == "defend":
        return "raise shield and prepare to dodge"
    elif req.action_type == "skill":
        return f"use {req.skill or 'skill'} ability"
    elif req.action_type == "flee":
        return "turn and run away"
    return "act carefully"


def _check_combat_status(combat: CombatState) -> str:
    """Check if combat should end and return new status."""
    player = next((p for p in combat.participants if p.is_player), None)
    enemies = [p for p in combat.participants if not p.is_player]

    if not player or player.hp <= 0:
        return "defeat"

    if all(e.hp <= 0 or "defeated" in e.conditions for e in enemies):
        return "victory"

    return "active"


def _advance_turn(combat: CombatState) -> None:
    """Advance to next turn in initiative order."""
    combat.turn_index = (combat.turn_index + 1) % len(combat.initiative_order)
    combat.current_actor_id = combat.initiative_order[combat.turn_index]

    # If we've gone through all participants, advance round
    if combat.turn_index == 0:
        combat.round_number += 1


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.post("/combat/start")
async def start_combat(req: StartCombatRequest, request: Request):
    """Start a new combat encounter.
    
    Returns initial combat state with initiative order and participants.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    from src.game.combat_service import begin_combat, combat_view
    with _SESSION_LOCK:
        combat = begin_combat(session_id, target_id=req.target_id)
        return combat_view(session_id, combat)


@router.post("/combat/action")
async def combat_action(req: CombatActionRequest, request: Request):
    """Execute a combat action.
    
    Returns resolution result (hit, damage) and updated combat state.
    Supports streaming response for AI narration.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    with _SESSION_LOCK:
        combat = _get_combat_state(session_id)
        if not combat:
            raise HTTPException(400, "No active combat. 没有正在进行的战斗。")
        if combat.status != "active":
            raise HTTPException(409, "战斗已结束。")
        result = _resolve_combat_action(session_id, combat, req)
    if "text/event-stream" in request.headers.get("accept", ""):
        return StreamingResponse(_stream_combat_response(result), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    return {**result.model_dump(mode="json", exclude_none=True), "round_number": result.combat_state.round_number}


@router.get("/combat/state")
async def get_combat_state(request: Request):
    """Get current combat state.
    
    Returns current combat status, participants HP, turn order, etc.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    from src.game.combat_service import combat_view
    with _SESSION_LOCK:
        combat = _get_combat_state(session_id)
        if not combat:
            raise HTTPException(404, "No active combat found. 没有战斗记录。")
        return combat_view(session_id, combat)


@router.post("/combat/end")
async def end_combat(req: EndCombatRequest, request: Request):
    """End the current combat (flee or surrender).
    
    Returns final combat state and outcome.
    """
    session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")

    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc

    from src.game.combat_service import leave_combat
    with _SESSION_LOCK:
        return leave_combat(session_id, req.reason)

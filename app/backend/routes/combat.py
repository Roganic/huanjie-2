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
from src.models.state import Scene, InventoryItem, ItemType
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


class CombatActionRequest(BaseModel):
    """Request to perform a combat action."""
    action_type: str  # "attack", "defend", "skill", "flee"
    target_id: Optional[str] = None
    weapon: Optional[str] = None
    skill: Optional[str] = None


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


class EndCombatRequest(BaseModel):
    """Request to end combat (flee or surrender)."""
    reason: str  # "flee", "surrender", "victory", "defeat"


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
        is_player=is_player,
        type="player" if is_player else "enemy",
        conditions=actor.conditions or [],
    )


def _get_combat_state(session_id: str) -> Optional[CombatState]:
    """Get combat state for a session."""
    return _combats.get(session_id)


def _set_combat_state(session_id: str, state: CombatState) -> None:
    """Set combat state for a session."""
    _combats[session_id] = state


def _clear_combat_state(session_id: str) -> None:
    """Clear combat state for a session."""
    _combats.pop(session_id, None)


def _sort_initiative(participants: list[CombatParticipant]) -> list[str]:
    """Sort participants by initiative (highest first)."""
    sorted_parts = sorted(participants, key=lambda p: p.initiative, reverse=True)
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
    actor_id = combat.current_actor_id
    actor = next((p for p in combat.participants if p.id == actor_id), None)
    if not actor:
        raise ValueError(f"Actor {actor_id} not found in combat")

    # Build ActionRequest for the orchestrator
    action_req = ActionRequest(
        scene_id=combat.scene.id,
        actor=actor.name,
        intent=_get_action_intent(req),
        approach=_get_action_approach(req),
        action_type=ActionType.ATTACK if req.action_type == "attack" else ActionType.GENERIC,
        weapon=req.weapon,
        target=req.target_id,
        skill=req.skill,
    )

    # Resolve action using orchestrator
    action_resp = resolve_action_with_agent(action_req)

    # Calculate sneak attack damage for rogues
    sneak_attack_damage: Optional[int] = None
    if req.action_type == "attack":
        player_actor = get_actor(session_id=session_id)
        if player_actor and player_actor.character_class and player_actor.character_class.value == "rogue":
            # Check for advantage or ally nearby
            has_advantage = "advantage" in (player_actor.conditions or [])
            has_ally_nearby = any(
                p.is_player and p.id != actor_id 
                for p in combat.participants
            )
            if has_advantage or has_ally_nearby:
                # Roll sneak attack dice: 1d6 per 2 levels (min 1d6)
                dice_count = max(1, ((player_actor.level or 1) + 1) // 2)
                import random
                sneak_damage = sum(random.randint(1, 6) for _ in range(dice_count))
                sneak_attack_damage = sneak_damage
                # Add to existing damage if hit
                if action_resp.outcome == Outcome.SUCCESS and action_resp.attack and action_resp.attack.damage:
                    # Apply sneak attack damage to target
                    for p in combat.participants:
                        if p.id == req.target_id or p.name == req.target_id:
                            p.hp = max(0, p.hp - sneak_damage)
                            break

    # Update participant HP from effects
    for effect in action_resp.effects:
        if effect.field == "hp":
            for p in combat.participants:
                if p.id == effect.target or p.name == effect.target:
                    p.hp = max(0, min(p.hp_max, p.hp + effect.delta))
        elif effect.field == "conditions_add":
            for p in combat.participants:
                if p.id == effect.target or p.name == effect.target:
                    if effect.delta not in p.conditions:
                        p.conditions.append(effect.delta)

    # Check combat end conditions
    combat.status = _check_combat_status(combat)

    # Add log entry
    log_entry = CombatLogEntry(
        actor_id=actor_id,
        action_type=req.action_type,
        target_id=req.target_id,
        hit=action_resp.outcome == Outcome.SUCCESS if req.action_type == "attack" else None,
        damage=action_resp.attack.damage.total if action_resp.attack and action_resp.attack.damage else 0,
        narrative=action_resp.narration,
        timestamp=int(asyncio.get_event_loop().time() * 1000),
    )
    combat.log.append(log_entry)

    # Advance turn if combat continues
    if combat.status == "active":
        _advance_turn(combat)

    # Save updated combat state
    _set_combat_state(session_id, combat)

    return CombatActionResponse(
        action_type=req.action_type,
        actor_id=actor_id,
        target_id=req.target_id,
        hit=action_resp.outcome == Outcome.SUCCESS if req.action_type == "attack" else None,
        damage=action_resp.attack.damage.total if action_resp.attack and action_resp.attack.damage else 0,
        sneak_attack_damage=sneak_attack_damage,
        effects=action_resp.effects,
        narrative=action_resp.narration,
        combat_state=combat,
    )


def _award_victory_rewards(session_id: str, combat: CombatState) -> dict | None:
    """Award XP and loot when combat ends in victory."""
    with _SESSION_LOCK:
        session = _get_session(session_id, create_if_missing=False)
        if session is None or session.actor is None:
            return None
        
        actor = session.actor
        
        # Find defeated enemies
        defeated_enemies: list[tuple[str, str]] = []
        for p in combat.participants:
            if not p.is_player and (p.hp <= 0 or "defeated" in p.conditions):
                defeated_enemies.append((p.id, p.name))
        
        if not defeated_enemies:
            return None
        
        # Generate loot
        loot = generate_combat_loot(defeated_enemies)
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
                inventory_items_to_add.append(InventoryItem(
                    id=item.item_id,
                    name=item.name,
                    type=ItemType.MISC,
                    description=item.description or "战利品",
                ))
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
        enemy_name = defeated_enemies[0][1]
        xp_gained = get_enemy_xp_reward(enemy_name)
        
        # Calculate level-up
        con_modifier = actor.abilities.modifier("con")
        new_xp, level_up_result = calculate_level_up(
            current_level=actor.level,
            current_xp=actor.experience_points,
            xp_gained=xp_gained,
            con_modifier=con_modifier,
            character_class=actor.character_class,
        )
        
        # Update actor
        updates: dict = {"experience_points": new_xp}
        
        if level_up_result and level_up_result.leveled_up:
            updates["level"] = level_up_result.new_level
            updates["proficiency_bonus"] = level_up_result.new_proficiency_bonus
            # Recalculate HP max
            hit_die = CLASS_HIT_DICE[actor.character_class]
            base_hp = hit_die + con_modifier
            if level_up_result.new_level > 1:
                hp_per_level = (hit_die // 2) + 1 + con_modifier
                new_hp_max = base_hp + hp_per_level * (level_up_result.new_level - 1)
            else:
                new_hp_max = base_hp
            updates["hp_max"] = new_hp_max
            updates["hp"] = new_hp_max  # Heal to full on level up
        
        session.actor = actor.model_copy(update=updates)
        _save_session(session)
        
        result: dict = {
            "xp_gained": xp_gained,
            "total_xp": new_xp,
            "loot_gained": loot_items_for_response,
        }
        
        if level_up_result and level_up_result.leveled_up:
            result["level_up"] = {
                "old_level": level_up_result.old_level,
                "new_level": level_up_result.new_level,
                "hp_increase": level_up_result.hp_increase,
                "new_proficiency_bonus": level_up_result.new_proficiency_bonus,
            }
        
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

    token = set_current_session(session_id)
    try:
        if not has_character(session_id=session_id):
            raise HTTPException(status_code=400, detail="No character found. Create a character first.")

        # Get player and enemy actors
        player = get_actor(session_id=session_id)
        enemy = get_enemy(session_id=session_id)

        if not player:
            raise HTTPException(status_code=400, detail="Player character not found.")

        # Roll initiative for all participants
        player_init = _roll_initiative(player)
        enemy_init = _roll_initiative(enemy)

        # Create participants
        participants = [
            _actor_to_participant(player, is_player=True, initiative=player_init),
            _actor_to_participant(enemy, is_player=False, initiative=enemy_init),
        ]

        # Sort initiative order
        initiative_order = _sort_initiative(participants)

        # Set combat scene
        set_combat_scene(session_id=session_id)
        scene = get_scene(session_id=session_id)

        # Create combat state
        combat = CombatState(
            combat_id=f"combat-{session_id[:8]}",
            round_number=1,
            turn_index=0,
            participants=participants,
            initiative_order=initiative_order,
            current_actor_id=initiative_order[0],
            scene=scene,
            status="active",
        )

        _set_combat_state(session_id, combat)

        return {
            "combat_id": combat.combat_id,
            "status": combat.status,
            "round_number": combat.round_number,
            "current_actor_id": combat.current_actor_id,
            "initiative_order": combat.initiative_order,
            "participants": [p.model_dump() for p in combat.participants],
            "combatants": [p.model_dump() for p in combat.participants],
            "scene": scene.model_dump(),
        }
    finally:
        reset_current_session(token)


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

    combat = _get_combat_state(session_id)
    if not combat:
        raise HTTPException(status_code=400, detail="No active combat. Start combat first.")

    if combat.status != "active":
        raise HTTPException(status_code=400, detail=f"Combat already ended: {combat.status}")

    token = set_current_session(session_id)
    try:
        result = _resolve_combat_action(session_id, combat, req)

        # Check if client accepts streaming
        accepts_stream = "text/event-stream" in request.headers.get("accept", "")
        if not accepts_stream:
            response_data = result.model_dump(exclude_none=True)
            # Add victory result fields if combat ended
            if combat.status == "victory":
                victory_result = _award_victory_rewards(session_id, combat)
                if victory_result:
                    response_data["loot_gained"] = victory_result.get("loot_gained", [])
                    response_data["xp_gained"] = victory_result.get("xp_gained", 0)
                    response_data["total_xp"] = victory_result.get("total_xp", 0)
                    if "level_up" in victory_result:
                        response_data["level_up"] = victory_result["level_up"]
                    response_data["victory"] = True
                else:
                    response_data["loot_gained"] = []
                    response_data["xp_gained"] = 0
            else:
                response_data["loot_gained"] = []
            response_data["combat_ended"] = combat.status != "active"
            return response_data

        return StreamingResponse(
            _stream_combat_response(result),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    finally:
        reset_current_session(token)


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

    combat = _get_combat_state(session_id)
    if not combat:
        raise HTTPException(status_code=404, detail="No active combat found.")

    return {
        "combat_id": combat.combat_id,
        "status": combat.status,
        "round_number": combat.round_number,
        "turn_index": combat.turn_index,
        "current_actor_id": combat.current_actor_id,
        "initiative_order": combat.initiative_order,
        "participants": [p.model_dump() for p in combat.participants],
        "combatants": [p.model_dump() for p in combat.participants],
        "log": [entry.model_dump() for entry in combat.log[-10:]],  # Last 10 entries
    }


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

    combat = _get_combat_state(session_id)
    if not combat:
        raise HTTPException(status_code=404, detail="No active combat found.")

    # Update combat status based on end reason
    if req.reason == "flee":
        combat.status = "escaped"
    elif req.reason == "surrender":
        combat.status = "defeat"
    elif req.reason == "victory":
        combat.status = "victory"
    elif req.reason == "defeat":
        combat.status = "defeat"

    _set_combat_state(session_id, combat)

    response = {
        "combat_id": combat.combat_id,
        "status": combat.status,
        "final_round": combat.round_number,
        "participants": [p.model_dump() for p in combat.participants],
    }

    # Clear combat state after reporting
    _clear_combat_state(session_id)

    return response

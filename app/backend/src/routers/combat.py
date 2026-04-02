"""Combat router for managing combat state and actions."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from enum import Enum
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..engine.dice import get_weapon_damage, roll_d20, roll_damage
from ..models.state import Actor, AdventurePhase
from ..state import (
    apply_effects,
    check_and_update_combat_status,
    get_actor,
    get_enemy,
    get_game_phase,
    get_scene,
    require_bootstrap_state,
    reset_current_session,
    set_combat_scene,
    set_current_session,
    set_exploration_phase,
    _get_session,
    _resolve_session_id,
    _SESSION_LOCK,
    _save_session,
)

router = APIRouter(tags=["combat"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CombatStatus(str, Enum):
    ACTIVE = "active"
    VICTORY = "victory"
    DEFEAT = "defeat"
    ESCAPED = "escaped"


class CombatActionType(str, Enum):
    ATTACK = "attack"
    DEFEND = "defend"
    SKILL = "skill"
    FLEE = "flee"


class CombatParticipant(BaseModel):
    id: str
    name: str
    hp: int
    hp_max: int
    ac: int
    initiative: int
    is_player: bool
    conditions: list[str]


class CombatLogEntry(BaseModel):
    actor_id: str
    action_type: str
    target_id: Optional[str] = None
    hit: Optional[bool] = None
    damage: Optional[int] = None
    narrative: str
    timestamp: int


class CombatState(BaseModel):
    combat_id: str
    round_number: int
    turn_index: int
    participants: list[CombatParticipant]
    initiative_order: list[str]
    current_actor_id: str
    scene: dict  # Simplified scene info
    status: CombatStatus
    log: list[CombatLogEntry]


class StartCombatRequest(BaseModel):
    enemy_id: Optional[str] = None


class StartCombatResponse(BaseModel):
    combat_state: CombatState
    game_phase: AdventurePhase


class CombatActionRequest(BaseModel):
    action_type: CombatActionType
    target_id: Optional[str] = None
    weapon: str = "longsword"


class CombatActionResult(BaseModel):
    action_type: CombatActionType
    actor_id: str
    target_id: Optional[str] = None
    hit: Optional[bool] = None
    damage: Optional[int] = None
    effects: list[dict]
    narrative: str
    combat_state: CombatState
    game_phase: AdventurePhase


class EndCombatRequest(BaseModel):
    reason: str = "flee"  # flee, surrender, victory, defeat


class EndCombatResponse(BaseModel):
    status: CombatStatus
    game_phase: AdventurePhase


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _calculate_initiative(actor: Actor) -> int:
    """Roll initiative for an actor."""
    dex_mod = actor.abilities.modifier("dex")
    return roll_d20() + dex_mod


def _actor_to_participant(actor: Actor, is_player: bool, initiative: int) -> CombatParticipant:
    """Convert an Actor to a CombatParticipant."""
    return CombatParticipant(
        id=actor.id,
        name=actor.name,
        hp=actor.hp,
        hp_max=actor.hp_max,
        ac=actor.ac,
        initiative=initiative,
        is_player=is_player,
        conditions=list(actor.conditions),
    )


def _build_combat_state(
    session,
    combat_id: str = "combat-01",
    round_number: int = 1,
    turn_index: int = 0,
    log: Optional[list[CombatLogEntry]] = None,
) -> CombatState:
    """Build current combat state from session."""
    actor = session.actor
    enemy = session.enemy
    
    participants = []
    if actor:
        actor_initiative = _calculate_initiative(actor)
        participants.append(_actor_to_participant(actor, True, actor_initiative))
    if enemy:
        enemy_initiative = _calculate_initiative(enemy)
        participants.append(_actor_to_participant(enemy, False, enemy_initiative))
    
    # Sort by initiative (highest first)
    participants.sort(key=lambda p: p.initiative, reverse=True)
    initiative_order = [p.id for p in participants]
    current_actor_id = initiative_order[turn_index % len(initiative_order)] if initiative_order else ""
    
    # Determine combat status
    status = CombatStatus.ACTIVE
    if enemy and enemy.hp <= 0:
        status = CombatStatus.VICTORY
    elif actor and actor.hp <= 0:
        status = CombatStatus.DEFEAT
    
    return CombatState(
        combat_id=combat_id,
        round_number=round_number,
        turn_index=turn_index,
        participants=participants,
        initiative_order=initiative_order,
        current_actor_id=current_actor_id,
        scene={
            "id": session.scene.id,
            "name": session.scene.name,
            "description": session.scene.description,
        },
        status=status,
        log=log or [],
    )


def _resolve_enemy_turn(combat_state: CombatState, enemy: Actor, player: Actor) -> tuple[str, list, CombatState]:
    """Resolve enemy AI turn."""
    # Simple AI: always attack the player
    action_type = "attack"
    
    # Roll attack
    str_mod = enemy.abilities.modifier("str")
    prof_bonus = enemy.proficiency_bonus
    hit_roll = roll_d20()
    total_attack = hit_roll + str_mod + prof_bonus
    
    if total_attack >= player.ac:
        # Hit! Roll damage (1d6 + str_mod for dagger)
        damage_total, _ = roll_damage("1d6")
        damage = max(1, damage_total + str_mod)
        narrative = f"{enemy.name} 用匕首刺中了 {player.name}，造成 {damage} 点伤害！"
        
        # Apply damage effect
        from ..models.action import Effect
        effects = [Effect(
            target=player.id,
            field="hp",
            delta=-damage,
            description=f"{enemy.name} hits {player.name} for {damage} damage.",
        )]
        hit = True
    else:
        narrative = f"{enemy.name} 试图攻击 {player.name}，但没命中！"
        effects = []
        hit = False
        damage = None
    
    # Advance turn
    combat_state.turn_index += 1
    if combat_state.turn_index >= len(combat_state.initiative_order):
        combat_state.turn_index = 0
        combat_state.round_number += 1
    combat_state.current_actor_id = combat_state.initiative_order[combat_state.turn_index]
    
    return narrative, effects, combat_state


# ---------------------------------------------------------------------------
# SSE Helpers
# ---------------------------------------------------------------------------

def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunk_text(text: str, size: int = 12) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


async def _stream_combat_action(narrative: str, result: CombatActionResult) -> AsyncIterator[str]:
    """Stream combat action narrative."""
    for chunk in _chunk_text(narrative):
        yield _sse_event("chunk", {"field": "narrative", "delta": chunk})
        await asyncio.sleep(0.02)
    yield _sse_event("complete", result.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/combat/start", response_model=StartCombatResponse)
async def start_combat(req: StartCombatRequest, request: Request):
    """Start a new combat encounter."""
    from ..state import DEFAULT_SESSION_ID
    
    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID
    
    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    token = set_current_session(session_id)
    try:
        # Set combat scene and phase
        set_combat_scene(session_id)
        
        # Get the updated session
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        session.game_phase = AdventurePhase.COMBAT
        _save_session(session)
        
        combat_state = _build_combat_state(session)
        
        return StartCombatResponse(
            combat_state=combat_state,
            game_phase=AdventurePhase.COMBAT,
        )
    finally:
        reset_current_session(token)


@router.post("/combat/action")
async def combat_action(req: CombatActionRequest, request: Request):
    """Execute a combat action."""
    from ..state import DEFAULT_SESSION_ID, apply_effects
    from ..models.action import Effect
    
    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID
    
    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    token = set_current_session(session_id)
    try:
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        actor = session.actor
        enemy = session.enemy
        
        if not actor:
            raise HTTPException(status_code=400, detail="No player character found")
        
        if req.action_type == CombatActionType.FLEE:
            # Fleeing ends combat
            session.game_phase = AdventurePhase.EXPLORATION
            _save_session(session)
            
            combat_state = _build_combat_state(session)
            combat_state.status = CombatStatus.ESCAPED
            
            result = CombatActionResult(
                action_type=CombatActionType.FLEE,
                actor_id=actor.id,
                narrative="你成功逃离了战斗！",
                combat_state=combat_state,
                game_phase=AdventurePhase.EXPLORATION,
                effects=[],
            )
            
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            if not accepts_stream:
                return result
            return StreamingResponse(
                _stream_combat_action(result.narrative, result),
                media_type="text/event-stream",
            )
        
        if req.action_type == CombatActionType.ATTACK:
            # Determine target
            target_id = req.target_id or (enemy.id if enemy else None)
            if not target_id:
                raise HTTPException(status_code=400, detail="No target specified")
            
            target = enemy if target_id == enemy.id else None
            if not target:
                raise HTTPException(status_code=400, detail="Target not found")
            
            # Resolve attack
            weapon = req.weapon or "longsword"
            damage_dice = get_weapon_damage(weapon)
            
            # Determine attack ability
            finesse_weapons = {"dagger", "rapier", "scimitar", "shortsword"}
            ranged_weapons = {"shortbow", "longbow", "light_crossbow", "heavy_crossbow"}
            weapon_lower = weapon.lower()
            if weapon_lower in finesse_weapons or weapon_lower in ranged_weapons:
                ability = "dex"
            else:
                ability = "str"
            
            modifier = actor.abilities.modifier(ability)
            prof = actor.proficiency_bonus
            
            hit_roll = roll_d20()
            total_attack = hit_roll + modifier + prof
            
            effects_list = []
            hit = total_attack >= target.ac
            damage = None
            
            if hit:
                # Roll damage
                damage_total, _ = roll_damage(damage_dice)
                damage = max(1, damage_total + modifier)
                
                # Apply damage to target
                with _SESSION_LOCK:
                    session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
                    new_hp = max(0, session.enemy.hp - damage)
                    session.enemy = session.enemy.model_copy(update={"hp": new_hp})
                    _save_session(session)
                
                narrative = f"{actor.name} 使用 {weapon} 攻击 {target.name}，命中！造成 {damage} 点伤害。"
            else:
                narrative = f"{actor.name} 使用 {weapon} 攻击 {target.name}，但没命中。"
            
            # Check if enemy defeated
            enemy_defeated = session.enemy.hp <= 0
            if enemy_defeated:
                narrative += f" {target.name} 被击败了！"
                session.game_phase = AdventurePhase.EXPLORATION
                _save_session(session)
            
            # Build combat state
            combat_state = _build_combat_state(session)
            if enemy_defeated:
                combat_state.status = CombatStatus.VICTORY
            
            result = CombatActionResult(
                action_type=CombatActionType.ATTACK,
                actor_id=actor.id,
                target_id=target.id,
                hit=hit,
                damage=damage,
                narrative=narrative,
                combat_state=combat_state,
                game_phase=session.game_phase,
                effects=[{"target": target.id, "field": "hp", "delta": -(damage or 0)}] if damage else [],
            )
            
            accepts_stream = "text/event-stream" in request.headers.get("accept", "")
            if not accepts_stream:
                return result
            return StreamingResponse(
                _stream_combat_action(narrative, result),
                media_type="text/event-stream",
            )
        
        # Defend or skill - simple implementation
        combat_state = _build_combat_state(session)
        
        # Advance turn
        combat_state.turn_index += 1
        if combat_state.turn_index >= len(combat_state.initiative_order):
            combat_state.turn_index = 0
            combat_state.round_number += 1
        combat_state.current_actor_id = combat_state.initiative_order[combat_state.turn_index]
        
        narrative = f"{actor.name} 采取了 {req.action_type.value} 行动。"
        
        result = CombatActionResult(
            action_type=req.action_type,
            actor_id=actor.id,
            narrative=narrative,
            combat_state=combat_state,
            game_phase=session.game_phase,
            effects=[],
        )
        
        accepts_stream = "text/event-stream" in request.headers.get("accept", "")
        if not accepts_stream:
            return result
        return StreamingResponse(
            _stream_combat_action(narrative, result),
            media_type="text/event-stream",
        )
        
    finally:
        reset_current_session(token)


@router.post("/combat/end", response_model=EndCombatResponse)
async def end_combat(req: EndCombatRequest, request: Request):
    """End the current combat."""
    from ..state import DEFAULT_SESSION_ID
    
    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID
    
    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    token = set_current_session(session_id)
    try:
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        
        # Map reason to status
        status_map = {
            "flee": CombatStatus.ESCAPED,
            "surrender": CombatStatus.DEFEAT,
            "victory": CombatStatus.VICTORY,
            "defeat": CombatStatus.DEFEAT,
        }
        status = status_map.get(req.reason, CombatStatus.ESCAPED)
        
        # Reset to exploration phase
        session.game_phase = AdventurePhase.EXPLORATION
        _save_session(session)
        
        return EndCombatResponse(
            status=status,
            game_phase=AdventurePhase.EXPLORATION,
        )
    finally:
        reset_current_session(token)


@router.get("/combat/state")
async def get_combat_state(request: Request):
    """Get current combat state."""
    from ..state import DEFAULT_SESSION_ID
    
    explicit_session_id = request.headers.get("X-Session-Id") or request.query_params.get("session_id")
    session_id = explicit_session_id or DEFAULT_SESSION_ID
    
    if explicit_session_id:
        try:
            require_bootstrap_state(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    
    token = set_current_session(session_id)
    try:
        session = _get_session(_resolve_session_id(session_id), create_if_missing=True)
        combat_state = _build_combat_state(session)
        
        return {
            "combat_state": combat_state,
            "game_phase": session.game_phase,
        }
    finally:
        reset_current_session(token)

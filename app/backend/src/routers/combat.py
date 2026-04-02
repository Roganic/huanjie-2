"""Combat endpoints for turn-based combat."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from combat import (
    Combatant,
    CombatantType,
    CombatOutcome,
    clear_combat_state,
    execute_attack_action,
    load_combat_state,
    next_turn,
    save_combat_state,
    start_combat,
)
from src.state import (
    get_actor,
    get_bootstrap_state,
    get_enemy,
    require_bootstrap_state,
    set_combat_scene,
    set_current_session,
    reset_current_session,
    _SESSION_LOCK,
    _get_session,
    _save_session,
    _ADVENTURE_SCENE_INIT,
    Scene,
)

router = APIRouter(prefix="/combat", tags=["combat"])


def _request_session_id(request: Request) -> str | None:
    return request.headers.get("X-Session-Id") or request.query_params.get("session_id")


def _resolve_session_id_or_404(request: Request) -> str:
    session_id = _request_session_id(request)
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id.")
    try:
        require_bootstrap_state(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Session not found or expired.") from exc
    return session_id


def _actor_to_combatant(actor, combatant_type: CombatantType) -> Combatant:
    return Combatant(
        id=actor.id,
        name=actor.name,
        type=combatant_type,
        hp=actor.hp,
        hp_max=actor.hp_max,
        ac=actor.ac,
        abilities={
            "str": actor.abilities.str_,
            "dex": actor.abilities.dex,
            "con": actor.abilities.con,
            "int": actor.abilities.int_,
            "wis": actor.abilities.wis,
            "cha": actor.abilities.cha,
        },
        proficiency_bonus=actor.proficiency_bonus,
        conditions=list(actor.conditions),
    )


def _default_weapon_for_actor(actor) -> str:
    class_value = (actor.character_class.value if actor.character_class else "warrior")
    return {
        "warrior": "longsword",
        "rogue": "shortsword",
        "mage": "dagger",
    }.get(class_value, "longsword")


def _sync_hp_to_session(combat_state, session_id: str) -> None:
    with _SESSION_LOCK:
        session = _get_session(session_id, create_if_missing=False)
        player = combat_state.get_players()[0] if combat_state.get_players() else None
        if player is not None and session.actor is not None:
            session.actor = session.actor.model_copy(update={"hp": player.hp})
        for enemy in combat_state.get_enemies():
            if session.enemy.id == enemy.id:
                session.enemy = session.enemy.model_copy(update={"hp": enemy.hp})
                break
        _save_session(session)


def _generate_narrative(result, attacker_name: str, target_name: str) -> str:
    if result.hit:
        dmg = result.damage.total if result.damage else 0
        return f"{attacker_name} 攻击 {target_name}，命中！造成 {dmg} 点伤害。"
    else:
        return f"{attacker_name} 攻击 {target_name}，但未命中。"


def _run_enemy_turn(combat_state) -> dict | None:
    """Run a simple enemy AI turn. Returns action result dict or None."""
    if combat_state.outcome != CombatOutcome.ONGOING:
        return None

    current = combat_state.current_combatant()
    if current is None or current.type != CombatantType.ENEMY:
        return None

    player = combat_state.get_players()[0] if combat_state.get_players() else None
    if player is None or not player.is_alive():
        return None

    weapon = "dagger"
    result = execute_attack_action(combat_state, current.id, player.id, weapon)
    narrative = _generate_narrative(result, current.name, player.name)
    next_turn(combat_state)
    return {
        "actor": current.name,
        "hit": result.hit,
        "damage": result.damage.total if result.hit and result.damage else 0,
        "updated_hp": player.hp,
        "narrative": narrative,
    }


@router.post("/start")
async def combat_start(request: Request):
    """Initialize combat with current actor and enemy."""
    session_id = _resolve_session_id_or_404(request)
    token = set_current_session(session_id)
    try:
        actor = get_actor(session_id=session_id)
        if actor is None:
            raise HTTPException(status_code=400, detail="No character found.")

        enemy = get_enemy(session_id=session_id)
        combatants = [
            _actor_to_combatant(actor, CombatantType.PLAYER),
            _actor_to_combatant(enemy, CombatantType.ENEMY),
        ]
        combat_state = start_combat(session_id, combatants)
        save_combat_state(combat_state)
        set_combat_scene(session_id=session_id)

        # If enemy wins initiative, run their turn immediately so it's player's turn
        enemy_start_action = None
        current = combat_state.current_combatant()
        if current is not None and current.type == CombatantType.ENEMY:
            enemy_start_action = _run_enemy_turn(combat_state)
            if combat_state.outcome == CombatOutcome.ONGOING:
                _sync_hp_to_session(combat_state, session_id)
                save_combat_state(combat_state)

        return {
            "session_id": session_id,
            "round_number": combat_state.round_number,
            "current_turn": combat_state.current_combatant().id if combat_state.current_combatant() else None,
            "turn_order": combat_state.turn_order,
            "combatants": [
                {
                    "id": c.id,
                    "name": c.name,
                    "type": c.type.value,
                    "hp": c.hp,
                    "hp_max": c.hp_max,
                    "ac": c.ac,
                    "initiative": c.initiative,
                    "status": c.status.value,
                }
                for c in combat_state.combatants
            ],
            "outcome": combat_state.outcome.value,
            "log": combat_state.log,
            "enemy_start_action": enemy_start_action,
        }
    finally:
        reset_current_session(token)


@router.get("/state")
async def combat_state_endpoint(request: Request):
    """Get current combat state."""
    session_id = _resolve_session_id_or_404(request)
    combat_state = load_combat_state(session_id)
    if combat_state is None:
        raise HTTPException(status_code=404, detail="No active combat found.")

    return {
        "session_id": session_id,
        "round_number": combat_state.round_number,
        "current_turn": combat_state.current_combatant().id if combat_state.current_combatant() else None,
        "turn_order": combat_state.turn_order,
        "combatants": [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type.value,
                "hp": c.hp,
                "hp_max": c.hp_max,
                "ac": c.ac,
                "initiative": c.initiative,
                "status": c.status.value,
            }
            for c in combat_state.combatants
        ],
        "outcome": combat_state.outcome.value,
        "log": combat_state.log,
    }


@router.post("/action")
async def combat_action(request: Request):
    """Execute a combat action (attack or skill check)."""
    from pydantic import BaseModel

    class CombatActionRequest(BaseModel):
        action_type: str  # "attack" or "skill_check"
        target_id: str | None = None
        weapon: str | None = None
        skill: str | None = None

    session_id = _resolve_session_id_or_404(request)
    body = await request.json()
    req = CombatActionRequest.model_validate(body)

    token = set_current_session(session_id)
    try:
        combat_state = load_combat_state(session_id)
        if combat_state is None:
            raise HTTPException(status_code=404, detail="No active combat found.")

        if combat_state.outcome != CombatOutcome.ONGOING:
            raise HTTPException(status_code=400, detail=f"Combat already ended: {combat_state.outcome.value}")

        current = combat_state.current_combatant()
        if current is None or current.type != CombatantType.PLAYER:
            raise HTTPException(status_code=400, detail="Not the player's turn.")

        actor = get_actor(session_id=session_id)
        if actor is None:
            raise HTTPException(status_code=400, detail="No character found.")

        enemy = get_enemy(session_id=session_id)
        target_id = req.target_id or enemy.id
        target = combat_state.get_combatant(target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Target not found.")

        if req.action_type == "attack":
            weapon = req.weapon or _default_weapon_for_actor(actor)
            result = execute_attack_action(combat_state, current.id, target.id, weapon)
            player_narrative = _generate_narrative(result, current.name, target.name)
            response = {
                "hit": result.hit,
                "damage": result.damage.total if result.hit and result.damage else 0,
                "updated_hp": target.hp,
                "narrative": player_narrative,
                "outcome": combat_state.outcome.value,
                "actor": current.name,
                "target": target.name,
            }
        elif req.action_type == "skill_check":
            # Simple skill check in combat (always succeeds for prototype)
            skill_name = req.skill or "perception"
            player_narrative = f"{current.name} 在战斗中尝试 {skill_name} 检定。"
            response = {
                "hit": None,
                "damage": 0,
                "updated_hp": target.hp,
                "narrative": player_narrative,
                "outcome": combat_state.outcome.value,
                "actor": current.name,
                "target": target.name,
            }
            next_turn(combat_state)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown action_type: {req.action_type}")

        # After player action (attack auto-advances in execute_attack_action for action budget,
        # but we still need to advance turn for non-attack or after attack)
        if req.action_type == "attack":
            next_turn(combat_state)

        # Run enemy turn(s) if needed
        enemy_actions = []
        if combat_state.outcome == CombatOutcome.ONGOING:
            enemy_result = _run_enemy_turn(combat_state)
            if enemy_result:
                enemy_actions.append(enemy_result)

        # Sync HP back to session
        _sync_hp_to_session(combat_state, session_id)
        save_combat_state(combat_state)

        response["round_number"] = combat_state.round_number
        response["current_turn"] = combat_state.current_combatant().id if combat_state.current_combatant() else None
        response["turn_order"] = combat_state.turn_order
        response["enemy_actions"] = enemy_actions
        response["combat_ended"] = combat_state.outcome != CombatOutcome.ONGOING
        response["victory"] = combat_state.outcome == CombatOutcome.VICTORY

        return response
    finally:
        reset_current_session(token)


@router.post("/end")
async def combat_end(request: Request):
    """End combat and persist HP changes."""
    session_id = _resolve_session_id_or_404(request)
    token = set_current_session(session_id)
    try:
        combat_state = load_combat_state(session_id)
        if combat_state is not None:
            _sync_hp_to_session(combat_state, session_id)
            clear_combat_state(session_id)

        with _SESSION_LOCK:
            session = _get_session(session_id, create_if_missing=False)
            if session.actor is not None:
                session.scene = Scene(**{**_ADVENTURE_SCENE_INIT, "actors": [session.actor.id]})
            _save_session(session)

        return get_bootstrap_state(session_id=session_id)
    finally:
        reset_current_session(token)

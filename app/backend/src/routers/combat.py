"""Combat endpoints for turn-based combat."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from combat import (
    Combatant,
    CombatantType,
    CombatOutcome,
    clear_combat_state,
    execute_attack_action,
    execute_enemy_turn,
    load_combat_state,
    next_turn,
    run_all_enemy_turns,
    save_combat_state,
    start_combat,
)
from src.rules.calculations import CLASS_HIT_DICE, proficiency_bonus
from src.rules.experience import (
    get_enemy_xp_reward,
    calculate_level_up,
    get_xp_progress,
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
from src.combat import (
    format_weapon_name_for_combat,
    get_weapon_for_combat,
    get_damage_dice_for_combat,
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
    """Get the default weapon name for combat actions.
    
    Priority:
    1. Use equipped weapon if available
    2. Fall back to class default
    """
    # First try to use equipped weapon
    equipped_weapon = get_weapon_for_combat(actor)
    if equipped_weapon is not None:
        return equipped_weapon.name
    
    # Fall back to class default
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
    """Run a single enemy AI turn using the new enemy AI system.
    
    Returns action result dict with full D&D 5e attack details or None.
    """
    if combat_state.outcome != CombatOutcome.ONGOING:
        return None

    current = combat_state.current_combatant()
    if current is None or current.type != CombatantType.ENEMY:
        return None

    # Skip if enemy is dead/defeated
    if not current.is_alive():
        return None

    # Execute enemy turn using new AI system
    result = execute_enemy_turn(current, combat_state)
    if result is None:
        return None

    # Advance to next turn
    next_turn(combat_state)
    
    # Return full action details including D&D 5e resolution fields
    return result.to_dict()


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
            "combat_id": f"combat-{session_id}",
            "session_id": session_id,
            "round_number": combat_state.round_number,
            "current_turn": combat_state.current_combatant().id if combat_state.current_combatant() else None,
            "current_actor_id": combat_state.current_combatant().id if combat_state.current_combatant() else None,
            "turn_order": combat_state.turn_order,
            "initiative_order": combat_state.turn_order,
            "status": "active" if combat_state.outcome == CombatOutcome.ONGOING else combat_state.outcome.value,
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
                    "is_player": c.type == CombatantType.PLAYER,
                }
                for c in combat_state.combatants
            ],
            "participants": [
                {
                    "id": c.id,
                    "name": c.name,
                    "type": c.type.value,
                    "hp": c.hp,
                    "hp_max": c.hp_max,
                    "ac": c.ac,
                    "initiative": c.initiative,
                    "status": c.status.value,
                    "is_player": c.type == CombatantType.PLAYER,
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
        "combat_id": f"combat-{session_id}",
        "session_id": session_id,
        "round_number": combat_state.round_number,
        "turn_index": combat_state.current_turn_index,
        "current_actor_id": combat_state.current_combatant().id if combat_state.current_combatant() else None,
        "current_turn": combat_state.current_combatant().id if combat_state.current_combatant() else None,
        "turn_order": combat_state.turn_order,
        "initiative_order": combat_state.turn_order,
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
                "is_player": c.type == CombatantType.PLAYER,
            }
            for c in combat_state.combatants
        ],
        "participants": [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type.value,
                "hp": c.hp,
                "hp_max": c.hp_max,
                "ac": c.ac,
                "initiative": c.initiative,
                "status": c.status.value,
                "is_player": c.type == CombatantType.PLAYER,
            }
            for c in combat_state.combatants
        ],
        "status": combat_state.outcome.value,
        "outcome": combat_state.outcome.value,
        "log": combat_state.log,
    }


def _award_xp_on_victory(session_id: str, combat_state) -> dict | None:
    """Award XP when enemy is defeated. Returns level_up info if applicable."""
    from src.rules.experience import get_enemy_xp_reward, calculate_level_up
    
    with _SESSION_LOCK:
        session = _get_session(session_id, create_if_missing=False)
        if session.actor is None:
            return None
        
        actor = session.actor
        
        # Check if enemy was defeated (HP <= 0 or has 'defeated' condition)
        enemy_defeated = False
        enemy_name = ""
        for combatant in combat_state.combatants:
            if combatant.type == CombatantType.ENEMY:
                if combatant.hp <= 0 or combatant.status.value == "defeated":
                    enemy_defeated = True
                    enemy_name = combatant.name
                    break
        
        # Also check session enemy
        if not enemy_defeated and session.enemy.hp <= 0:
            enemy_defeated = True
            enemy_name = session.enemy.name
        
        if not enemy_defeated:
            return None
        
        # Get XP reward
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
        updates = {"experience_points": new_xp}
        
        if level_up_result and level_up_result.leveled_up:
            updates["level"] = level_up_result.new_level
            updates["proficiency_bonus"] = level_up_result.new_proficiency_bonus
            # Recalculate HP max based on new level
            hit_die = CLASS_HIT_DICE[actor.character_class]
            # Calculate new HP max: base at level 1 + increases per level
            # Simple formula: (hit_die + con_mod) at level 1 + avg per additional level
            base_hp = hit_die + con_modifier
            if level_up_result.new_level > 1:
                hp_per_level = (hit_die // 2) + 1 + con_modifier
                new_hp_max = base_hp + hp_per_level * (level_up_result.new_level - 1)
            else:
                new_hp_max = base_hp
            updates["hp_max"] = new_hp_max
            # Also heal to full on level up
            updates["hp"] = new_hp_max
        
        session.actor = actor.model_copy(update=updates)
        _save_session(session)
        
        result = {
            "xp_gained": xp_gained,
            "total_xp": new_xp,
        }
        
        if level_up_result and level_up_result.leveled_up:
            result["level_up"] = {
                "old_level": level_up_result.old_level,
                "new_level": level_up_result.new_level,
                "hp_increase": level_up_result.hp_increase,
                "new_proficiency_bonus": level_up_result.new_proficiency_bonus,
            }
        
        return result


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
            raise HTTPException(status_code=400, detail="No active combat found.")

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
            
            # Determine sneak attack eligibility for rogues
            sneak_attack = False
            sneak_attack_dice = "1d6"
            if actor.character_class and actor.character_class.value == "rogue":
                has_advantage = "advantage" in actor.conditions
                has_ally_nearby = any(
                    c.type == CombatantType.PLAYER and c.id != current.id
                    for c in combat_state.combatants
                )
                if has_advantage or has_ally_nearby:
                    sneak_attack = True
                    # 1d6 per 2 levels (minimum 1d6)
                    dice_count = max(1, ((actor.level or 1) + 1) // 2)
                    sneak_attack_dice = f"{dice_count}d6"
            
            result = execute_attack_action(
                combat_state, current.id, target.id, weapon,
                sneak_attack=sneak_attack,
                sneak_attack_dice=sneak_attack_dice,
            )
            
            # Get weapon info for response
            weapon_info = get_weapon_for_combat(actor, req.weapon)
            weapon_display_name = weapon_info.name if weapon_info else weapon
            player_narrative = _generate_narrative(result, current.name, target.name)
            response = {
                "action_type": "attack",
                "actor_id": current.id,
                "target_id": target.id,
                "hit": result.hit,
                "damage": result.damage.total if result.hit and result.damage else 0,
                "updated_hp": target.hp,
                "narrative": player_narrative,
                "outcome": combat_state.outcome.value,
                "actor": current.name,
                "target": target.name,
            }
            if result.sneak_attack_damage is not None:
                response["sneak_attack_damage"] = result.sneak_attack_damage.total
        elif req.action_type == "skill_check":
            # Simple skill check in combat (always succeeds for prototype)
            skill_name = req.skill or "perception"
            player_narrative = f"{current.name} 在战斗中尝试 {skill_name} 检定。"
            response = {
                "action_type": "skill_check",
                "actor_id": current.id,
                "target_id": target.id,
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

        # Run all enemy turns until it's player's turn again or combat ends
        enemy_actions = []
        while combat_state.outcome == CombatOutcome.ONGOING:
            current = combat_state.current_combatant()
            if current is None or current.type != CombatantType.ENEMY:
                break
            
            # Skip dead enemies
            if not current.is_alive():
                next_turn(combat_state)
                continue
            
            enemy_result = _run_enemy_turn(combat_state)
            if enemy_result:
                enemy_actions.append(enemy_result)
            else:
                # Could not execute turn, skip to next
                next_turn(combat_state)

        # Award XP if victory
        xp_result = None
        if combat_state.outcome == CombatOutcome.VICTORY:
            xp_result = _award_xp_on_victory(session_id, combat_state)

        # Sync HP back to session
        _sync_hp_to_session(combat_state, session_id)
        save_combat_state(combat_state)

        response["round_number"] = combat_state.round_number
        response["current_turn"] = combat_state.current_combatant().id if combat_state.current_combatant() else None
        response["turn_order"] = combat_state.turn_order
        response["enemy_actions"] = enemy_actions
        response["combat_ended"] = combat_state.outcome != CombatOutcome.ONGOING
        response["victory"] = combat_state.outcome == CombatOutcome.VICTORY
        
        # Add combat_state for test compatibility
        response["combat_state"] = {
            "combat_id": f"combat-{session_id}",
            "round_number": combat_state.round_number,
            "current_actor_id": combat_state.current_combatant().id if combat_state.current_combatant() else None,
            "participants": [
                {
                    "id": c.id,
                    "name": c.name,
                    "hp": c.hp,
                    "hp_max": c.hp_max,
                    "ac": c.ac,
                    "initiative": c.initiative,
                    "is_player": c.type == CombatantType.PLAYER,
                    "conditions": list(c.conditions),
                }
                for c in combat_state.combatants
            ],
            "status": "active" if combat_state.outcome == CombatOutcome.ONGOING else combat_state.outcome.value,
            "log": combat_state.log,
        }
        
        # Add XP and level-up info to response
        if xp_result:
            response["xp_gained"] = xp_result.get("xp_gained", 0)
            if "level_up" in xp_result:
                response["level_up"] = xp_result["level_up"]

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

"""Combat engine core logic."""

from __future__ import annotations

from .models import (
    ActionBudget,
    AttackResult,
    Combatant,
    CombatantStatus,
    CombatantType,
    CombatOutcome,
    CombatState,
    DamageDetail,
    DiceRoller,
    DamageRoller,
)


# Weapon ability mapping (finesse weapons can use DEX, others use STR)
FINESSE_WEAPONS = {"dagger", "rapier", "scimitar", "shortsword"}
RANGED_WEAPONS = {"shortbow", "longbow", "light_crossbow", "heavy_crossbow"}

# Predefined weapon damage dice for common weapon types
WEAPON_DAMAGE = {
    "dagger": "1d4",
    "shortsword": "1d6",
    "longsword": "1d8",
    "greatsword": "2d6",
    "battleaxe": "1d8",
    "greataxe": "1d12",
    "club": "1d4",
    "mace": "1d6",
    "spear": "1d6",
    "halberd": "1d10",
    "rapier": "1d8",
    "scimitar": "1d6",
    "quarterstaff": "1d6",
    "handaxe": "1d6",
    "light_crossbow": "1d8",
    "shortbow": "1d6",
    "longbow": "1d8",
    "heavy_crossbow": "1d10",
}


def get_weapon_damage(weapon: str) -> str:
    """Get damage dice expression for a weapon type."""
    return WEAPON_DAMAGE.get(weapon.lower(), "1d6")


def infer_attack_ability(weapon: str) -> str:
    """Determine ability modifier for attack based on weapon type."""
    weapon_lower = weapon.lower()
    if weapon_lower in FINESSE_WEAPONS:
        return "dex"
    if weapon_lower in RANGED_WEAPONS:
        return "dex"
    return "str"


def roll_initiative(
    combatants: list[Combatant],
    dice_roller: DiceRoller | None = None,
) -> list[Combatant]:
    """Roll initiative for all combatants and return them sorted.

    Initiative = d20 + DEX modifier. Sorted descending by initiative.
    """
    roller = dice_roller or _default_d20
    for c in combatants:
        c.initiative = roller() + c.dexterity_modifier()
    return sorted(combatants, key=lambda c: c.initiative, reverse=True)


def start_combat(
    session_id: str,
    combatants: list[Combatant],
    dice_roller: DiceRoller | None = None,
) -> CombatState:
    """Initialize a combat state, roll initiative, and set up turn order."""
    ordered = roll_initiative(combatants, dice_roller=dice_roller)
    turn_order = [c.id for c in ordered if c.is_alive()]

    state = CombatState(
        session_id=session_id,
        combatants=ordered,
        turn_order=turn_order,
        current_turn_index=0,
        round_number=1,
        outcome=CombatOutcome.ONGOING,
    )

    _reset_action_budget(state.current_combatant())
    state.add_log(f"Combat started! Round 1 — {ordered[0].name}'s turn.")
    return state


def resolve_attack(
    attacker: Combatant,
    target: Combatant,
    weapon: str,
    dice_roller: DiceRoller | None = None,
    damage_roller: DamageRoller | None = None,
) -> AttackResult:
    """Resolve a melee or ranged attack.

    Attack roll: d20 + ability modifier + proficiency bonus
    If hit: roll damage dice + ability modifier
    """
    roller = dice_roller or _default_d20
    dmg_roller = damage_roller or _default_damage_roll

    ability = infer_attack_ability(weapon)
    ability_mod = attacker.ability_modifier(ability)
    prof_bonus = attacker.proficiency_bonus

    hit_roll = roller()
    total_attack = hit_roll + ability_mod + prof_bonus
    hit = total_attack >= target.ac

    damage_detail = None
    if hit:
        damage_expr = get_weapon_damage(weapon)
        rolls_total, rolls = dmg_roller(damage_expr)
        damage_modifier = ability_mod
        damage_total = max(1, rolls_total + damage_modifier)
        damage_detail = DamageDetail(
            dice_expression=damage_expr,
            rolls=rolls,
            modifier=damage_modifier,
            total=damage_total,
        )

    return AttackResult(
        hit_roll=hit_roll,
        total_attack=total_attack,
        target_ac=target.ac,
        hit=hit,
        damage=damage_detail,
    )


def apply_damage(
    combat_state: CombatState,
    target: Combatant,
    damage: int,
) -> None:
    """Apply damage to a combatant and update their status if HP drops to 0."""
    target.hp = max(0, target.hp - damage)
    if target.hp == 0:
        if target.type == CombatantType.ENEMY:
            target.status = CombatantStatus.DEAD
            combat_state.add_log(f"{target.name} has been slain.")
        else:
            target.status = CombatantStatus.INCAPACITATED
            combat_state.add_log(f"{target.name} has fallen unconscious.")


def check_combat_end(combat_state: CombatState) -> CombatOutcome:
    """Check if combat has ended and return the outcome.

    VICTORY: all enemies are dead (HP <= 0 or status dead)
    DEFEAT: all player characters are incapacitated or dead
    """
    alive_enemies = [c for c in combat_state.get_enemies() if c.is_alive()]
    active_players = [c for c in combat_state.get_players() if c.can_act()]

    if not alive_enemies:
        return CombatOutcome.VICTORY
    if not active_players:
        return CombatOutcome.DEFEAT
    return CombatOutcome.ONGOING


def next_turn(combat_state: CombatState) -> None:
    """Advance to the next combatant's turn, skipping dead combatants."""
    if not combat_state.turn_order:
        return

    # Reset current combatant's action budget before leaving
    current = combat_state.current_combatant()
    if current is not None:
        current.action_budget = ActionBudget()

    # Advance turn index
    combat_state.current_turn_index = (
        combat_state.current_turn_index + 1
    ) % len(combat_state.turn_order)

    # Skip dead combatants
    start_index = combat_state.current_turn_index
    while True:
        candidate = combat_state.current_combatant()
        if candidate is None or candidate.is_alive():
            break
        combat_state.current_turn_index = (
            combat_state.current_turn_index + 1
        ) % len(combat_state.turn_order)
        if combat_state.current_turn_index == start_index:
            break

    # Increment round when we wrap around
    if combat_state.current_turn_index == 0:
        combat_state.round_number += 1

    # Reset new current combatant's budget
    _reset_action_budget(combat_state.current_combatant())


def execute_attack_action(
    combat_state: CombatState,
    attacker_id: str,
    target_id: str,
    weapon: str,
    dice_roller: DiceRoller | None = None,
    damage_roller: DamageRoller | None = None,
) -> AttackResult:
    """Full attack action execution: resolve attack, apply damage, check end."""
    attacker = combat_state.get_combatant(attacker_id)
    target = combat_state.get_combatant(target_id)
    if attacker is None or target is None:
        raise ValueError("Attacker or target not found in combat state")

    result = resolve_attack(
        attacker, target, weapon,
        dice_roller=dice_roller,
        damage_roller=damage_roller,
    )

    if result.hit and result.damage is not None:
        apply_damage(combat_state, target, result.damage.total)
        combat_state.add_log(
            f"{attacker.name} hits {target.name} for {result.damage.total} damage."
        )
    else:
        combat_state.add_log(
            f"{attacker.name} attacks {target.name} but misses."
        )

    # Deduct the action cost
    attacker.action_budget.action = False

    # Check combat end
    combat_state.outcome = check_combat_end(combat_state)
    return result


def _reset_action_budget(combatant: Combatant | None) -> None:
    if combatant is not None:
        combatant.action_budget = ActionBudget()


def _default_d20() -> int:
    import random
    return random.randint(1, 20)


def _default_damage_roll(dice_expr: str) -> tuple[int, list[int]]:
    import random
    import re

    match = re.match(r"(\d+)d(\d+)([+-]\d+)?", dice_expr.strip())
    if not match:
        raise ValueError(f"Invalid dice expression: {dice_expr}")

    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    return max(0, total), rolls

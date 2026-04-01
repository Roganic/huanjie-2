"""Combat engine core for D&D 5e style turn-based combat."""

from .engine import (
    apply_damage,
    check_combat_end,
    execute_attack_action,
    get_weapon_damage,
    infer_attack_ability,
    next_turn,
    resolve_attack,
    roll_initiative,
    start_combat,
)
from .models import (
    ActionBudget,
    AttackResult,
    Combatant,
    CombatantStatus,
    CombatantType,
    CombatOutcome,
    CombatState,
    DamageDetail,
    DamageRoller,
    DiceRoller,
)
from .state import (
    clear_combat_state,
    load_combat_state,
    reset_all_combat_states,
    save_combat_state,
)

__all__ = [
    "ActionBudget",
    "apply_damage",
    "AttackResult",
    "check_combat_end",
    "Combatant",
    "CombatantStatus",
    "CombatantType",
    "CombatOutcome",
    "CombatState",
    "clear_combat_state",
    "DamageDetail",
    "DamageRoller",
    "DiceRoller",
    "execute_attack_action",
    "get_weapon_damage",
    "infer_attack_ability",
    "load_combat_state",
    "next_turn",
    "reset_all_combat_states",
    "resolve_attack",
    "roll_initiative",
    "save_combat_state",
    "start_combat",
]

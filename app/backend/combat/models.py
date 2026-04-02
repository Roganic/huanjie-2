"""Combat engine data models."""

from __future__ import annotations

from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, Field


class CombatantType(str, Enum):
    PLAYER = "player"
    ENEMY = "enemy"


class CombatantStatus(str, Enum):
    ACTIVE = "active"
    INCAPACITATED = "incapacitated"
    DEAD = "dead"


class ActionBudget(BaseModel):
    """Tracks remaining actions for the current turn."""

    move: bool = True
    action: bool = True
    bonus_action: bool = True

    def reset(self) -> None:
        self.move = True
        self.action = True
        self.bonus_action = True


class Combatant(BaseModel):
    """A single participant in combat."""

    id: str
    name: str
    type: CombatantType
    hp: int
    hp_max: int
    ac: int
    abilities: dict[str, int] = Field(default_factory=dict)
    proficiency_bonus: int = 2
    conditions: list[str] = Field(default_factory=list)
    initiative: int = 0
    initiative_roll: int = 0
    status: CombatantStatus = CombatantStatus.ACTIVE
    action_budget: ActionBudget = Field(default_factory=ActionBudget)

    def ability_modifier(self, ability: str) -> int:
        """Return the D&D 5e ability modifier for a given ability."""
        score = self.abilities.get(ability, 10)
        return (score - 10) // 2

    def dexterity_modifier(self) -> int:
        return self.ability_modifier("dex")

    def is_alive(self) -> bool:
        return self.status != CombatantStatus.DEAD

    def can_act(self) -> bool:
        return self.status == CombatantStatus.ACTIVE


class DamageDetail(BaseModel):
    """Details of damage dealt."""

    dice_expression: str
    rolls: list[int]
    modifier: int = 0
    total: int


class AttackResult(BaseModel):
    """Result of an attack roll."""

    hit_roll: int
    total_attack: int
    target_ac: int
    hit: bool
    damage: Optional[DamageDetail] = None


class CombatOutcome(str, Enum):
    ONGOING = "ongoing"
    VICTORY = "victory"
    DEFEAT = "defeat"


class CombatState(BaseModel):
    """Full state of an ongoing combat encounter."""

    session_id: str
    combatants: list[Combatant] = Field(default_factory=list)
    turn_order: list[str] = Field(default_factory=list)
    current_turn_index: int = 0
    round_number: int = 1
    outcome: CombatOutcome = CombatOutcome.ONGOING
    log: list[str] = Field(default_factory=list)

    def current_combatant(self) -> Optional[Combatant]:
        if not self.turn_order:
            return None
        return self.get_combatant(self.turn_order[self.current_turn_index])

    def get_combatant(self, combatant_id: str) -> Optional[Combatant]:
        for c in self.combatants:
            if c.id == combatant_id:
                return c
        return None

    def get_players(self) -> list[Combatant]:
        return [c for c in self.combatants if c.type == CombatantType.PLAYER]

    def get_enemies(self) -> list[Combatant]:
        return [c for c in self.combatants if c.type == CombatantType.ENEMY]

    def add_log(self, message: str) -> None:
        self.log.append(message)


DiceRoller = Callable[[], int]
DamageRoller = Callable[[str], tuple[int, list[int]]]

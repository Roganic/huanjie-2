"""Enemy AI decision making for combat.

Implements basic enemy AI that:
- Prioritizes attacking the player with lowest HP
- Uses appropriate weapons based on enemy type
- Follows D&D 5e attack resolution
"""

from __future__ import annotations

from typing import Callable, Optional

from .models import Combatant, CombatantType, CombatState, DamageDetail


# Enemy type configurations with weapon stats
ENEMY_TYPE_CONFIG = {
    "goblin_scout": {
        "weapon": "dagger",
        "attack_ability": "dex",  # Finesse weapon
        "damage_dice": "1d4",
        "attack_bonus": 4,  # +2 dex + 2 prof
    },
    "goblin_warrior": {
        "weapon": "scimitar",
        "attack_ability": "dex",
        "damage_dice": "1d6",
        "attack_bonus": 4,
    },
    "goblin_shaman": {
        "weapon": "quarterstaff",
        "attack_ability": "str",
        "damage_dice": "1d6",
        "attack_bonus": 2,  # Weaker attack
    },
    "wolf": {
        "weapon": "bite",
        "attack_ability": "str",
        "damage_dice": "1d6",
        "attack_bonus": 4,
    },
    "bandit": {
        "weapon": "shortsword",
        "attack_ability": "dex",
        "damage_dice": "1d6",
        "attack_bonus": 4,
    },
    "orc": {
        "weapon": "greataxe",
        "attack_ability": "str",
        "damage_dice": "1d12",
        "attack_bonus": 5,
    },
    "skeleton": {
        "weapon": "shortsword",
        "attack_ability": "dex",
        "damage_dice": "1d6",
        "attack_bonus": 4,
    },
    "zombie": {
        "weapon": "slam",
        "attack_ability": "str",
        "damage_dice": "1d6",
        "attack_bonus": 3,
    },
    # Default fallback
    "default": {
        "weapon": "dagger",
        "attack_ability": "str",
        "damage_dice": "1d6",
        "attack_bonus": 3,
    },
}


def get_enemy_config(enemy: Combatant) -> dict:
    """Get enemy configuration based on enemy type or ID."""
    enemy_id = enemy.id.lower()
    enemy_name = enemy.name.lower()
    
    # Try to match by ID or name
    for type_key, config in ENEMY_TYPE_CONFIG.items():
        if type_key in enemy_id or type_key in enemy_name:
            return config
    
    # Check for common keywords in name
    if "goblin" in enemy_name:
        if "shaman" in enemy_name or "法师" in enemy_name:
            return ENEMY_TYPE_CONFIG["goblin_shaman"]
        elif "scout" in enemy_name or "斥候" in enemy_name:
            return ENEMY_TYPE_CONFIG["goblin_scout"]
        else:
            return ENEMY_TYPE_CONFIG["goblin_warrior"]
    elif "wolf" in enemy_name or "狼" in enemy_name:
        return ENEMY_TYPE_CONFIG["wolf"]
    elif "orc" in enemy_name or "兽人" in enemy_name:
        return ENEMY_TYPE_CONFIG["orc"]
    elif "skeleton" in enemy_name or "骷髅" in enemy_name:
        return ENEMY_TYPE_CONFIG["skeleton"]
    elif "zombie" in enemy_name or "僵尸" in enemy_name:
        return ENEMY_TYPE_CONFIG["zombie"]
    elif "bandit" in enemy_name or "强盗" in enemy_name:
        return ENEMY_TYPE_CONFIG["bandit"]
    
    return ENEMY_TYPE_CONFIG["default"]


def find_target_for_enemy(enemy: Combatant, combat_state: CombatState) -> Optional[Combatant]:
    """Find the best target for an enemy to attack.
    
    Strategy: Attack the player with the lowest HP (prioritizing weak targets).
    If all players have the same HP, attack the first available one.
    """
    players = combat_state.get_players()
    alive_players = [p for p in players if p.is_alive() and p.hp > 0]
    
    if not alive_players:
        return None
    
    # Sort by HP (lowest first), then pick the first one
    # This prioritizes weakened targets
    sorted_players = sorted(alive_players, key=lambda p: p.hp)
    return sorted_players[0]


def roll_d20() -> int:
    """Roll a d20."""
    import random
    return random.randint(1, 20)


def roll_damage(dice_expr: str) -> tuple[int, list[int]]:
    """Roll damage dice.
    
    Args:
        dice_expr: Dice expression like "1d6", "1d8+2", "2d6"
        
    Returns:
        Tuple of (total, list of individual rolls)
    """
    import random
    import re
    
    match = re.match(r"(\d+)d(\d+)(?:\s*([+-])\s*(\d+))?", dice_expr.strip())
    if not match:
        raise ValueError(f"Invalid dice expression: {dice_expr}")
    
    num_dice = int(match.group(1))
    die_size = int(match.group(2))
    modifier = 0
    
    if match.group(3) and match.group(4):
        sign = 1 if match.group(3) == "+" else -1
        modifier = sign * int(match.group(4))
    
    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    total = sum(rolls) + modifier
    return max(0, total), rolls


def calculate_attack_bonus(enemy: Combatant, config: dict) -> int:
    """Calculate total attack bonus for an enemy."""
    ability = config["attack_ability"]
    ability_mod = enemy.ability_modifier(ability)
    prof_bonus = enemy.proficiency_bonus
    return ability_mod + prof_bonus


class EnemyActionResult:
    """Result of an enemy's combat action."""
    
    def __init__(
        self,
        enemy_id: str,
        enemy_name: str,
        target_id: str,
        target_name: str,
        weapon: str,
        roll: int,
        attack_total: int,
        target_ac: int,
        hit: bool,
        damage: Optional[DamageDetail] = None,
        target_hp_after: int = 0,
        narrative: str = "",
    ):
        self.enemy_id = enemy_id
        self.enemy_name = enemy_name
        self.target_id = target_id
        self.target_name = target_name
        self.weapon = weapon
        self.roll = roll
        self.attack_total = attack_total
        self.target_ac = target_ac
        self.hit = hit
        self.damage = damage
        self.target_hp_after = target_hp_after
        self.narrative = narrative
    
    def to_dict(self) -> dict:
        """Convert result to dictionary for API response."""
        return {
            "enemy_id": self.enemy_id,
            "enemy_name": self.enemy_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "weapon": self.weapon,
            "roll": self.roll,
            "attack_total": self.attack_total,
            "target_ac": self.target_ac,
            "hit": self.hit,
            "damage": self.damage.total if self.damage else 0,
            "damage_detail": self.damage.model_dump() if self.damage else None,
            "target_hp_after": self.target_hp_after,
            "narrative": self.narrative,
        }


def execute_enemy_turn(
    enemy: Combatant,
    combat_state: CombatState,
    dice_roller: Optional[Callable[[], int]] = None,
    damage_roller: Optional[Callable[[str], tuple[int, list[int]]]] = None,
) -> Optional[EnemyActionResult]:
    """Execute a full turn for an enemy combatant.
    
    This includes:
    1. Finding the best target
    2. Rolling attack (d20 + attack bonus)
    3. Comparing against target AC
    4. Rolling damage on hit
    5. Applying damage
    
    Returns:
        EnemyActionResult with full details, or None if enemy cannot act.
    """
    if not enemy.can_act() or enemy.hp <= 0:
        return None
    
    # Get enemy configuration
    config = get_enemy_config(enemy)
    weapon = config["weapon"]
    damage_dice = config["damage_dice"]
    
    # Find target
    target = find_target_for_enemy(enemy, combat_state)
    if target is None:
        return None
    
    # Roll attack
    roller = dice_roller or roll_d20
    hit_roll = roller()
    attack_bonus = calculate_attack_bonus(enemy, config)
    total_attack = hit_roll + attack_bonus
    target_ac = target.ac
    hit = total_attack >= target_ac
    
    # Resolve damage if hit
    damage_detail = None
    target_hp_after = target.hp
    
    if hit:
        dmg_roller = damage_roller or roll_damage
        damage_rolls_total, rolls = dmg_roller(damage_dice)
        ability = config["attack_ability"]
        damage_modifier = enemy.ability_modifier(ability)
        damage_total = max(1, damage_rolls_total + damage_modifier)
        
        damage_detail = DamageDetail(
            dice_expression=damage_dice,
            rolls=rolls,
            modifier=damage_modifier,
            total=damage_total,
        )
        
        # Apply damage
        target_hp_after = max(0, target.hp - damage_total)
        target.hp = target_hp_after
        
        # Check if target is defeated
        if target_hp_after == 0:
            from .models import CombatantStatus
            if target.type == CombatantType.PLAYER:
                target.status = CombatantStatus.INCAPACITATED
            else:
                target.status = CombatantStatus.DEAD
    
    # Generate narrative
    if hit:
        if damage_detail:
            narrative = f"{enemy.name} 使用 {weapon} 攻击 {target.name}，命中！造成 {damage_detail.total} 点伤害。"
        else:
            narrative = f"{enemy.name} 攻击 {target.name}，命中！"
    else:
        narrative = f"{enemy.name} 使用 {weapon} 攻击 {target.name}，但未命中。"
    
    return EnemyActionResult(
        enemy_id=enemy.id,
        enemy_name=enemy.name,
        target_id=target.id,
        target_name=target.name,
        weapon=weapon,
        roll=hit_roll,
        attack_total=total_attack,
        target_ac=target_ac,
        hit=hit,
        damage=damage_detail,
        target_hp_after=target_hp_after,
        narrative=narrative,
    )


def run_all_enemy_turns(
    combat_state: CombatState,
    dice_roller: Optional[Callable[[], int]] = None,
    damage_roller: Optional[Callable[[str], tuple[int, list[int]]]] = None,
) -> list[EnemyActionResult]:
    """Run turns for all active enemies.
    
    Returns list of action results for all enemies that acted.
    Skips dead enemies and enemies that cannot find a valid target.
    """
    results = []
    
    for enemy in combat_state.get_enemies():
        # Skip dead or defeated enemies
        if not enemy.is_alive():
            continue
        
        # Execute enemy turn
        result = execute_enemy_turn(
            enemy,
            combat_state,
            dice_roller=dice_roller,
            damage_roller=damage_roller,
        )
        
        if result:
            results.append(result)
    
    return results

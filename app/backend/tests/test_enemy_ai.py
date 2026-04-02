"""Unit tests for enemy AI decision making and combat actions."""

import pytest

from combat import (
    Combatant,
    CombatantStatus,
    CombatantType,
    CombatOutcome,
    CombatState,
    DamageDetail,
    EnemyActionResult,
    execute_enemy_turn,
    get_enemy_config,
    run_all_enemy_turns,
    start_combat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(
    name: str = "Aldric",
    hp: int = 20,
    ac: int = 16,
    dex: int = 13,
    str_: int = 15,
) -> Combatant:
    return Combatant(
        id=f"player-{name.lower()}",
        name=name,
        type=CombatantType.PLAYER,
        hp=hp,
        hp_max=hp,
        ac=ac,
        abilities={"str": str_, "dex": dex, "con": 14, "int": 8, "wis": 12, "cha": 10},
        proficiency_bonus=2,
    )


def _make_enemy(
    name: str = "Goblin",
    enemy_id: str = None,
    hp: int = 7,
    ac: int = 12,
    dex: int = 14,
    str_: int = 8,
) -> Combatant:
    enemy_id = enemy_id or f"enemy-{name.lower()}"
    return Combatant(
        id=enemy_id,
        name=name,
        type=CombatantType.ENEMY,
        hp=hp,
        hp_max=hp,
        ac=ac,
        abilities={"str": str_, "dex": dex, "con": 10, "int": 10, "wis": 8, "cha": 8},
        proficiency_bonus=2,
    )


# ---------------------------------------------------------------------------
# Enemy Configuration Tests
# ---------------------------------------------------------------------------

def test_get_enemy_config_goblin_scout():
    """Goblin scout should have dagger and dex-based attack."""
    enemy = _make_enemy(name="Goblin Scout", enemy_id="goblin-scout-01")
    config = get_enemy_config(enemy)
    
    assert config["weapon"] == "dagger"
    assert config["attack_ability"] == "dex"
    assert config["damage_dice"] == "1d4"


def test_get_enemy_config_goblin_shaman():
    """Goblin shaman should have quarterstaff and str-based attack."""
    enemy = _make_enemy(name="Goblin Shaman", enemy_id="goblin-shaman-01")
    config = get_enemy_config(enemy)
    
    assert config["weapon"] == "quarterstaff"
    assert config["attack_ability"] == "str"
    assert config["damage_dice"] == "1d6"


def test_get_enemy_config_wolf():
    """Wolf should have bite attack."""
    enemy = _make_enemy(name="Wolf", enemy_id="wolf-01")
    config = get_enemy_config(enemy)
    
    assert config["weapon"] == "bite"
    assert config["damage_dice"] == "1d6"


def test_get_enemy_config_orc():
    """Orc should have greataxe with high damage."""
    enemy = _make_enemy(name="Orc Warrior", enemy_id="orc-01")
    config = get_enemy_config(enemy)
    
    assert config["weapon"] == "greataxe"
    assert config["damage_dice"] == "1d12"
    assert config["attack_ability"] == "str"


def test_get_enemy_config_name_matching():
    """Enemy config should match based on name keywords."""
    # Chinese name matching
    enemy = _make_enemy(name="哥布林斥候", enemy_id="goblin-01")
    config = get_enemy_config(enemy)
    assert config["weapon"] == "dagger"
    
    # Another variant
    enemy = _make_enemy(name="座狼", enemy_id="wolf-01")
    config = get_enemy_config(enemy)
    assert config["weapon"] == "bite"


# ---------------------------------------------------------------------------
# Target Selection Tests
# ---------------------------------------------------------------------------

def test_enemy_targets_lowest_hp_player():
    """Enemy should prioritize attacking the player with lowest HP."""
    player1 = _make_player(name="Aldric", hp=20)
    player2 = _make_player(name="Mira", hp=5)  # Lower HP
    enemy = _make_enemy(name="Goblin")
    
    state = CombatState(
        session_id="s1",
        combatants=[player1, player2, enemy],
        turn_order=[enemy.id, player1.id, player2.id],
    )
    
    # Enemy should target Mira (lowest HP)
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,  # Guaranteed hit
        damage_roller=lambda expr: (4, [4]),
    )
    
    assert result is not None
    assert result.target_id == player2.id
    assert result.target_name == "Mira"


def test_enemy_skips_dead_players():
    """Enemy should not target dead players."""
    player1 = _make_player(name="Aldric", hp=0)
    player1.status = CombatantStatus.INCAPACITATED
    player2 = _make_player(name="Mira", hp=10)
    enemy = _make_enemy(name="Goblin")
    
    state = CombatState(
        session_id="s1",
        combatants=[player1, player2, enemy],
        turn_order=[enemy.id, player1.id, player2.id],
    )
    
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (3, [3]),
    )
    
    assert result is not None
    assert result.target_id == player2.id


# ---------------------------------------------------------------------------
# Attack Resolution Tests
# ---------------------------------------------------------------------------

def test_enemy_attack_hit_resolution():
    """Enemy attack should include full D&D 5e resolution details on hit."""
    player = _make_player(name="Aldric", ac=12)
    enemy = _make_enemy(name="Goblin", dex=14)  # +2 DEX mod, +2 prof = +4 total
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    # Roll 10 + 4 = 14 >= AC 12 -> hit
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (4, [4]),
    )
    
    assert result is not None
    assert result.hit is True
    assert result.roll == 10
    assert result.attack_total == 14  # 10 + 2 (DEX) + 2 (prof)
    assert result.target_ac == 12
    assert result.damage is not None
    assert result.damage.total > 0


def test_enemy_attack_miss_resolution():
    """Enemy attack should show miss details when attack fails."""
    player = _make_player(name="Aldric", ac=20)  # High AC
    enemy = _make_enemy(name="Goblin", dex=14)  # +4 bonus
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    # Roll 5 + 4 = 9 < AC 20 -> miss
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 5,
    )
    
    assert result is not None
    assert result.hit is False
    assert result.roll == 5
    assert result.attack_total == 9
    assert result.damage is None


def test_enemy_attack_applies_damage():
    """Enemy attack hit should reduce player HP."""
    player = _make_player(name="Aldric", hp=20, ac=10)
    enemy = _make_enemy(name="Goblin")
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,  # Hit
        damage_roller=lambda expr: (4, [4]),
    )
    
    assert result is not None
    assert result.hit is True
    assert player.hp < 20  # HP should be reduced
    assert result.target_hp_after == player.hp


def test_enemy_damage_includes_ability_modifier():
    """Enemy damage should include ability modifier."""
    player = _make_player(name="Aldric", ac=10)
    enemy = _make_enemy(name="Goblin", dex=16)  # +3 DEX mod
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (4, [4]),  # Base 4 damage
    )
    
    assert result is not None
    assert result.hit is True
    # Dagger: 1d4 (rolled 4) + 3 DEX = 7 damage
    assert result.damage.total == 7


# ---------------------------------------------------------------------------
# Result Structure Tests
# ---------------------------------------------------------------------------

def test_enemy_action_result_to_dict():
    """EnemyActionResult should convert to dict with all required fields."""
    damage = DamageDetail(
        dice_expression="1d6",
        rolls=[4],
        modifier=2,
        total=6,
    )
    
    result = EnemyActionResult(
        enemy_id="enemy-001",
        enemy_name="Goblin",
        target_id="player-001",
        target_name="Aldric",
        weapon="dagger",
        roll=15,
        attack_total=19,
        target_ac=14,
        hit=True,
        damage=damage,
        target_hp_after=14,
        narrative="Goblin hits Aldric!",
    )
    
    data = result.to_dict()
    
    assert data["enemy_id"] == "enemy-001"
    assert data["enemy_name"] == "Goblin"
    assert data["target_id"] == "player-001"
    assert data["target_name"] == "Aldric"
    assert data["weapon"] == "dagger"
    assert data["roll"] == 15
    assert data["attack_total"] == 19
    assert data["target_ac"] == 14
    assert data["hit"] is True
    assert data["damage"] == 6
    assert data["damage_detail"] is not None
    assert data["target_hp_after"] == 14
    assert data["narrative"] == "Goblin hits Aldric!"


# ---------------------------------------------------------------------------
# Dead Enemy Handling Tests
# ---------------------------------------------------------------------------

def test_dead_enemy_cannot_act():
    """Dead enemy should not be able to take actions."""
    player = _make_player(name="Aldric")
    enemy = _make_enemy(name="Goblin", hp=0)
    enemy.status = CombatantStatus.DEAD
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    result = execute_enemy_turn(enemy, state)
    assert result is None


def test_run_all_enemy_turns_skips_dead():
    """run_all_enemy_turns should skip dead enemies."""
    player = _make_player(name="Aldric")
    enemy1 = _make_enemy(name="Goblin 1", hp=0)
    enemy1.status = CombatantStatus.DEAD
    enemy2 = _make_enemy(name="Goblin 2", hp=7)
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy1, enemy2],
        turn_order=[player.id, enemy1.id, enemy2.id],
    )
    
    results = run_all_enemy_turns(
        state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (3, [3]),
    )
    
    # Only enemy2 should act
    assert len(results) == 1
    assert results[0].enemy_id == enemy2.id


# ---------------------------------------------------------------------------
# Multiple Enemies Tests
# ---------------------------------------------------------------------------

def test_run_all_enemy_turns_multiple_enemies():
    """run_all_enemy_turns should handle multiple living enemies."""
    player = _make_player(name="Aldric", hp=30)
    enemy1 = _make_enemy(name="Goblin 1")
    enemy2 = _make_enemy(name="Goblin 2")
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy1, enemy2],
        turn_order=[enemy1.id, enemy2.id, player.id],
    )
    
    results = run_all_enemy_turns(
        state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (3, [3]),
    )
    
    # Both enemies should act
    assert len(results) == 2
    enemy_ids = {r.enemy_id for r in results}
    assert enemy1.id in enemy_ids
    assert enemy2.id in enemy_ids


# ---------------------------------------------------------------------------
# Narrative Tests
# ---------------------------------------------------------------------------

def test_hit_narrative_includes_details():
    """Hit narrative should mention enemy, weapon, target, and damage."""
    player = _make_player(name="Aldric", ac=10)
    enemy = _make_enemy(name="Goblin")
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (4, [4]),
    )
    
    assert result is not None
    assert result.hit is True
    assert enemy.name in result.narrative
    assert player.name in result.narrative
    assert "命中" in result.narrative or "hit" in result.narrative.lower()


def test_miss_narrative_includes_details():
    """Miss narrative should mention the miss."""
    player = _make_player(name="Aldric", ac=20)
    enemy = _make_enemy(name="Goblin")
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy],
        turn_order=[enemy.id, player.id],
    )
    
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 5,
    )
    
    assert result is not None
    assert result.hit is False
    assert "未命中" in result.narrative or "miss" in result.narrative.lower()

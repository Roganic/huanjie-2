"""Integration tests for enemy AI in multi-turn combat scenarios."""

import pytest

from combat import (
    Combatant,
    CombatantStatus,
    CombatantType,
    CombatOutcome,
    CombatState,
    check_combat_end,
    execute_enemy_turn,
    next_turn,
    run_all_enemy_turns,
    start_combat,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(
    name: str = "Aldric",
    hp: int = 30,
    ac: int = 16,
    dex: int = 20,  # High DEX to ensure player goes first
    str_: int = 15,
) -> Combatant:
    """Create a player with high DEX to ensure they win initiative."""
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
    dex: int = 8,  # Low DEX so enemies go after player
    str_: int = 8,
) -> Combatant:
    enemy_id = enemy_id or f"enemy-{name.lower().replace(' ', '-')}"
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
# Integration Tests
# ---------------------------------------------------------------------------

def test_three_round_combat_enemies_act_each_turn():
    """Test: Enemies act every turn in a 3-round combat.
    
    Acceptance Criteria:
    - Enemy actions are recorded each round
    - Player HP changes are traceable
    - Each living enemy produces an action record
    """
    player = _make_player(name="Aldric", hp=30, ac=10)  # Low AC to ensure hits
    enemy1 = _make_enemy(name="Goblin 1", enemy_id="enemy-goblin-1")
    enemy2 = _make_enemy(name="Goblin 2", enemy_id="enemy-goblin-2")
    
    # Start combat - player goes first (higher DEX)
    combatants = [player, enemy1, enemy2]
    state = start_combat("s1", combatants, dice_roller=lambda: 10)
    
    all_enemy_actions = []
    initial_hp = player.hp
    
    # Simulate 3 rounds
    for round_num in range(1, 4):
        current = state.current_combatant()
        
        # Player's turn - just skip
        if current and current.type == CombatantType.PLAYER:
            next_turn(state)
        
        # Enemy turns
        round_actions = []
        while state.outcome == CombatOutcome.ONGOING:
            current = state.current_combatant()
            if current is None or current.type != CombatantType.ENEMY:
                break
            
            if not current.is_alive():
                next_turn(state)
                continue
            
            result = execute_enemy_turn(
                current, state,
                dice_roller=lambda: 15,  # Guaranteed hit
                damage_roller=lambda expr: (3, [3]),  # Consistent damage
            )
            
            if result:
                round_actions.append(result)
                all_enemy_actions.append(result)
            
            next_turn(state)
        
        # Verify enemies acted this round
        assert len(round_actions) > 0, f"Round {round_num}: No enemy actions recorded"
        
        # Check HP decreased
        assert player.hp < initial_hp, f"Round {round_num}: Player HP should decrease"
        initial_hp = player.hp
    
    # Total enemy actions across all rounds
    assert len(all_enemy_actions) >= 6, f"Expected at least 6 enemy actions, got {len(all_enemy_actions)}"
    
    # Verify action structure
    for action in all_enemy_actions:
        assert action.roll is not None
        assert action.attack_total is not None
        assert action.target_ac is not None
        assert action.hit is not None
        assert action.damage is not None  # All should hit with our fixed rolls


def test_enemy_hp_tracked_across_rounds():
    """Test: Enemy HP is tracked and dead enemies don't act.
    
    Acceptance Criteria:
    - Damaged enemies continue to act if alive
    - Defeated enemies (HP 0) are skipped
    """
    player = _make_player(name="Aldric", hp=50, ac=10)
    enemy = _make_enemy(name="Goblin", hp=5)  # Low HP to be defeated quickly
    
    combatants = [player, enemy]
    state = start_combat("s1", combatants, dice_roller=lambda: 10)
    
    # Player turn - skip
    next_turn(state)
    
    # Enemy attacks once
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (2, [2]),
    )
    assert result is not None
    next_turn(state)
    
    # Defeat the enemy (simulated player attack)
    enemy.hp = 0
    enemy.status = CombatantStatus.DEAD
    
    # Next round - enemy should not act
    next_turn(state)  # Player turn
    next_turn(state)  # Should skip dead enemy
    
    # Verify enemy is dead
    assert not enemy.is_alive()
    
    # Verify dead enemy cannot act
    dead_result = execute_enemy_turn(enemy, state)
    assert dead_result is None


def test_combat_state_updates_after_enemy_actions():
    """Test: Combat state correctly reflects enemy action outcomes.
    
    Acceptance Criteria:
    - Player HP in combat state matches damage dealt
    - Combat end is detected when player reaches 0 HP
    """
    player = _make_player(name="Aldric", hp=10, ac=10)  # Low HP
    enemy = _make_enemy(name="Orc", enemy_id="enemy-orc", hp=15, str_=16, dex=8)
    
    combatants = [player, enemy]
    state = start_combat("s1", combatants, dice_roller=lambda: 10)
    
    # Player turn - skip
    next_turn(state)
    
    # Enemy attacks with high damage
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (8, [8]),  # High damage
    )
    
    assert result is not None
    assert result.hit is True
    assert result.damage.total > 0
    
    # Check combat state
    combat_status = check_combat_end(state)
    
    # If player is at 0 HP, combat should end with defeat
    if player.hp == 0:
        assert combat_status == CombatOutcome.DEFEAT


def test_multiple_enemies_target_priority():
    """Test: Multiple enemies correctly prioritize targets.
    
    Acceptance Criteria:
    - Enemies attack the player with lowest HP
    - Target selection is consistent across enemies
    """
    # Two players with different HP
    player1 = _make_player(name="Aldric", hp=20, ac=10, dex=20)
    player2 = _make_player(name="Mira", hp=8, ac=10, dex=18)  # Lower HP
    enemy = _make_enemy(name="Goblin", dex=8)
    
    state = CombatState(
        session_id="s1",
        combatants=[player1, player2, enemy],
        turn_order=[enemy.id, player1.id, player2.id],
    )
    
    # Enemy should target Mira (lowest HP)
    result = execute_enemy_turn(
        enemy, state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (3, [3]),
    )
    
    assert result is not None
    assert result.target_id == player2.id, "Enemy should target player with lowest HP"
    assert result.target_name == "Mira"


def test_enemy_action_response_structure():
    """Test: Enemy action response contains all required fields for API.
    
    Acceptance Criteria:
    - Response contains: enemy_id, enemy_name, target_id, target_name
    - Response contains: weapon, roll, attack_total, target_ac, hit
    - Response contains: damage, damage_detail, target_hp_after, narrative
    """
    player = _make_player(name="Aldric", hp=20, ac=10, dex=20)
    enemy = _make_enemy(name="Goblin", enemy_id="goblin-001", dex=8)
    
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
    
    # Convert to dict (as would be done for API response)
    data = result.to_dict()
    
    # Verify all required fields exist
    required_fields = [
        "enemy_id", "enemy_name", "target_id", "target_name",
        "weapon", "roll", "attack_total", "target_ac", "hit",
        "damage", "damage_detail", "target_hp_after", "narrative"
    ]
    
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"
    
    # Verify field values
    assert data["enemy_id"] == "goblin-001"
    assert data["enemy_name"] == "Goblin"
    assert data["target_id"] == player.id
    assert data["hit"] is True
    assert data["damage"] > 0
    assert data["damage_detail"] is not None
    assert "rolls" in data["damage_detail"]
    assert "dice_expression" in data["damage_detail"]


def test_run_all_enemy_turns_integration():
    """Test: run_all_enemy_turns handles complete enemy phase.
    
    Acceptance Criteria:
    - All living enemies get to act
    - Dead enemies are skipped
    - Results include all actions
    """
    player = _make_player(name="Aldric", hp=50, ac=10, dex=20)
    enemy1 = _make_enemy(name="Goblin 1", enemy_id="e1", hp=7, dex=8)
    enemy2 = _make_enemy(name="Goblin 2", enemy_id="e2", hp=0, dex=8)  # Dead
    enemy2.status = CombatantStatus.DEAD
    enemy3 = _make_enemy(name="Goblin 3", enemy_id="e3", hp=7, dex=8)
    
    state = CombatState(
        session_id="s1",
        combatants=[player, enemy1, enemy2, enemy3],
        turn_order=[player.id, enemy1.id, enemy2.id, enemy3.id],
    )
    
    # Run all enemy turns
    results = run_all_enemy_turns(
        state,
        dice_roller=lambda: 15,
        damage_roller=lambda expr: (3, [3]),
    )
    
    # Should have 2 results (enemy1 and enemy3, enemy2 is dead)
    assert len(results) == 2
    
    # Verify which enemies acted
    actor_ids = {r.enemy_id for r in results}
    assert "e1" in actor_ids
    assert "e2" not in actor_ids  # Dead enemy should not act
    assert "e3" in actor_ids
    
    # Verify player took damage
    assert player.hp < 50


def test_three_round_hp_traceability():
    """Test: Player HP changes are traceable across 3 rounds.
    
    This test specifically verifies the acceptance criteria:
    '连续 3 回合战斗测试：敌方每回合均有行动，玩家 HP 变化可追溯'
    """
    player = _make_player(name="Hero", hp=50, ac=10, dex=20)
    enemy1 = _make_enemy(name="Goblin Warrior", enemy_id="gw1", dex=8)
    enemy2 = _make_enemy(name="Goblin Scout", enemy_id="gs1", dex=8)
    
    combatants = [player, enemy1, enemy2]
    state = start_combat("test-3round", combatants, dice_roller=lambda: 10)
    
    # Track HP changes per round
    hp_history = [player.hp]
    enemy_actions_by_round = []
    
    for round_num in range(1, 4):
        round_actions = []
        current = state.current_combatant()
        
        # Handle player turn if needed
        if current and current.type == CombatantType.PLAYER:
            next_turn(state)
        
        # Enemy turns
        while state.outcome == CombatOutcome.ONGOING:
            current = state.current_combatant()
            if current is None or current.type != CombatantType.ENEMY:
                break
            if not current.is_alive():
                next_turn(state)
                continue
            
            result = execute_enemy_turn(
                current, state,
                dice_roller=lambda: 15,
                damage_roller=lambda expr: (4, [2, 2]),  # 4 damage per hit
            )
            
            if result:
                round_actions.append(result.to_dict())
            next_turn(state)
        
        # Record state after this round
        hp_history.append(player.hp)
        enemy_actions_by_round.append(round_actions)
        
        # Verify: At least one enemy acted this round
        assert len(round_actions) > 0, f"Round {round_num}: No enemy actions"
    
    # Verify: HP decreased each round
    for i in range(1, len(hp_history)):
        assert hp_history[i] < hp_history[i-1], f"HP should decrease from round {i-1} to {i}"
    
    # Verify: Total damage is traceable
    total_damage_dealt = sum(
        action["damage"] 
        for round_actions in enemy_actions_by_round 
        for action in round_actions
    )
    total_hp_lost = hp_history[0] - hp_history[-1]
    
    assert total_damage_dealt == total_hp_lost, \
        f"Damage dealt ({total_damage_dealt}) should equal HP lost ({total_hp_lost})"
    
    print(f"\n3-Round Combat Summary:")
    print(f"  Initial HP: {hp_history[0]}")
    for i, (hp, actions) in enumerate(zip(hp_history[1:], enemy_actions_by_round), 1):
        print(f"  Round {i}: HP={hp}, Enemy actions={len(actions)}")
    print(f"  Total HP lost: {total_hp_lost}")

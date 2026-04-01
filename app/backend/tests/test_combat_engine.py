"""Unit tests for the combat engine core."""

import pytest

from combat import (
    ActionBudget,
    Combatant,
    CombatantStatus,
    CombatantType,
    CombatOutcome,
    CombatState,
    apply_damage,
    check_combat_end,
    execute_attack_action,
    next_turn,
    resolve_attack,
    roll_initiative,
    save_combat_state,
    load_combat_state,
    clear_combat_state,
    reset_all_combat_states,
    start_combat,
)


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset combat state store before every test."""
    reset_all_combat_states()
    yield
    reset_all_combat_states()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_player(
    name: str = "Aldric",
    hp: int = 10,
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
    hp: int = 7,
    ac: int = 12,
    dex: int = 14,
    str_: int = 8,
) -> Combatant:
    return Combatant(
        id=f"enemy-{name.lower()}",
        name=name,
        type=CombatantType.ENEMY,
        hp=hp,
        hp_max=hp,
        ac=ac,
        abilities={"str": str_, "dex": dex, "con": 10, "int": 10, "wis": 8, "cha": 8},
        proficiency_bonus=2,
    )


# ---------------------------------------------------------------------------
# CombatState & Combatant data structures
# ---------------------------------------------------------------------------

def test_combat_state_structure():
    """CombatState must support multiple combatants."""
    p1 = _make_player("Aldric")
    p2 = _make_player("Mira")
    e1 = _make_enemy("Goblin")

    state = CombatState(
        session_id="sess-1",
        combatants=[p1, p2, e1],
        turn_order=[p1.id, p2.id, e1.id],
    )

    assert len(state.combatants) == 3
    assert state.get_combatant(p1.id) == p1
    assert state.get_combatant(e1.id) == e1
    assert state.get_players() == [p1, p2]
    assert state.get_enemies() == [e1]


def test_combatant_ability_modifier():
    """Ability modifiers are derived from scores, not hardcoded."""
    c = Combatant(
        id="c1", name="Test", type=CombatantType.PLAYER,
        hp=10, hp_max=10, ac=10,
        abilities={"str": 15, "dex": 14, "con": 10, "int": 8, "wis": 12, "cha": 16},
    )
    assert c.ability_modifier("str") == 2
    assert c.ability_modifier("dex") == 2
    assert c.ability_modifier("con") == 0
    assert c.ability_modifier("int") == -1
    assert c.ability_modifier("wis") == 1
    assert c.ability_modifier("cha") == 3


# ---------------------------------------------------------------------------
# Initiative
# ---------------------------------------------------------------------------

def test_initiative_rolls_and_sorts():
    """Initiative = d20 + DEX modifier and sorted descending."""
    p1 = _make_player(name="Aldric", dex=14)  # +2
    e1 = _make_enemy(name="Goblin", dex=10)   # +0

    # Fixed dice rolls: player rolls 10, enemy rolls 15
    def _roller_seq():
        return next(_roller_seq.gen)
    _roller_seq.gen = iter([10, 15])

    ordered = roll_initiative([p1, e1], dice_roller=_roller_seq)

    # Expected: p1 = 10 + 2 = 12, e1 = 15 + 0 = 15
    assert ordered[0].id == e1.id
    assert ordered[0].initiative == 15
    assert ordered[1].id == p1.id
    assert ordered[1].initiative == 12


def test_start_combat_sets_up_state():
    """start_combat initializes turn order and round tracking."""
    p1 = _make_player("Aldric", dex=14)
    e1 = _make_enemy("Goblin", dex=10)

    def _roller():
        return 10

    state = start_combat("sess-1", [p1, e1], dice_roller=_roller)
    assert state.session_id == "sess-1"
    assert state.round_number == 1
    assert state.current_combatant().id == p1.id  # 12 > 10
    assert state.current_combatant().action_budget.action is True


# ---------------------------------------------------------------------------
# Attack resolution
# ---------------------------------------------------------------------------

def test_attack_hit_when_total_ge_ac():
    """Attack hits when total_attack >= target AC."""
    attacker = _make_player(str_=15)  # +2 STR
    target = _make_enemy(ac=10)

    # Roll 8 + 2 (STR) + 2 (prof) = 12 >= 10 -> hit
    result = resolve_attack(
        attacker, target, "longsword",
        dice_roller=lambda: 8,
        damage_roller=lambda expr: (5, [5]),
    )
    assert result.hit is True
    assert result.hit_roll == 8
    assert result.total_attack == 12
    assert result.damage is not None
    assert result.damage.total == 7  # 5 + 2 str mod


def test_attack_miss_when_total_lt_ac():
    """Attack misses when total_attack < target AC."""
    attacker = _make_player(str_=15)  # +2 STR
    target = _make_enemy(ac=16)

    # Roll 8 + 2 + 2 = 12 < 16 -> miss
    result = resolve_attack(
        attacker, target, "longsword",
        dice_roller=lambda: 8,
    )
    assert result.hit is False
    assert result.damage is None


def test_damage_only_rolled_on_hit():
    """Damage dice are only rolled when the attack hits."""
    attacker = _make_player(str_=15)
    target = _make_enemy(ac=20)

    damage_rolled = [False]

    def _dmg(expr):
        damage_rolled[0] = True
        return (4, [4])

    result = resolve_attack(
        attacker, target, "longsword",
        dice_roller=lambda: 10,
        damage_roller=_dmg,
    )
    # 10 + 2 + 2 = 14 < 20 -> miss
    assert result.hit is False
    assert result.damage is None
    assert damage_rolled[0] is False


def test_finesse_weapon_uses_dex():
    """Finesse weapons use DEX modifier for attack and damage."""
    attacker = _make_player(dex=16, str_=10)  # +3 DEX, +0 STR
    target = _make_enemy(ac=10)

    result = resolve_attack(
        attacker, target, "rapier",
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (4, [4]),
    )
    # 10 + 3 (DEX) + 2 (prof) = 15 >= 10
    assert result.hit is True
    assert result.total_attack == 15
    assert result.damage.total == 7  # 4 + 3 dex mod


def test_ranged_weapon_uses_dex():
    """Ranged weapons use DEX modifier for attack and damage."""
    attacker = _make_player(dex=16, str_=10)
    target = _make_enemy(ac=10)

    result = resolve_attack(
        attacker, target, "shortbow",
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (3, [3]),
    )
    assert result.hit is True
    assert result.total_attack == 15
    assert result.damage.total == 6  # 3 + 3 dex mod


# ---------------------------------------------------------------------------
# HP changes & death/unconscious
# ---------------------------------------------------------------------------

def test_hp_reduction_on_damage():
    """HP is correctly reduced when damage is applied."""
    state = CombatState(session_id="s1")
    target = _make_enemy(hp=10)
    apply_damage(state, target, 4)
    assert target.hp == 6


def test_enemy_dies_at_zero_hp():
    """Enemy reaches 0 HP -> status becomes DEAD."""
    state = CombatState(session_id="s1")
    enemy = _make_enemy(hp=7)
    apply_damage(state, enemy, 7)
    assert enemy.hp == 0
    assert enemy.status == CombatantStatus.DEAD


def test_player_incapacitated_at_zero_hp():
    """Player reaches 0 HP -> status becomes INCAPACITATED."""
    state = CombatState(session_id="s1")
    player = _make_player(hp=10)
    apply_damage(state, player, 10)
    assert player.hp == 0
    assert player.status == CombatantStatus.INCAPACITATED


def test_hp_does_not_go_negative():
    """HP should bottom out at 0."""
    state = CombatState(session_id="s1")
    enemy = _make_enemy(hp=5)
    apply_damage(state, enemy, 10)
    assert enemy.hp == 0


# ---------------------------------------------------------------------------
# Combat end detection
# ---------------------------------------------------------------------------

def test_victory_when_all_enemies_dead():
    """All enemies dead -> VICTORY."""
    state = CombatState(
        session_id="s1",
        combatants=[
            _make_player("Aldric"),
            _make_enemy("Goblin", hp=0),
        ],
    )
    state.combatants[1].status = CombatantStatus.DEAD
    assert check_combat_end(state) == CombatOutcome.VICTORY


def test_defeat_when_all_players_incapacitated():
    """All players incapacitated -> DEFEAT."""
    state = CombatState(
        session_id="s1",
        combatants=[
            _make_player("Aldric", hp=0),
            _make_enemy("Goblin"),
        ],
    )
    state.combatants[0].status = CombatantStatus.INCAPACITATED
    assert check_combat_end(state) == CombatOutcome.DEFEAT


def test_ongoing_when_both_sides_active():
    """Both sides have active combatants -> ONGOING."""
    state = CombatState(
        session_id="s1",
        combatants=[
            _make_player("Aldric"),
            _make_enemy("Goblin"),
        ],
    )
    assert check_combat_end(state) == CombatOutcome.ONGOING


def test_victory_updates_state_outcome():
    """execute_attack_action updates state.outcome when all enemies die."""
    player = _make_player("Aldric", str_=15)
    enemy = _make_enemy("Goblin", hp=2)
    state = start_combat("s1", [player, enemy], dice_roller=lambda: 10)

    result = execute_attack_action(
        state, player.id, enemy.id, "longsword",
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (5, [5]),
    )
    assert result.hit is True
    assert state.outcome == CombatOutcome.VICTORY


# ---------------------------------------------------------------------------
# Turn structure & action budget
# ---------------------------------------------------------------------------

def test_action_budget_tracks_usage():
    """Action budget decrements after attack action."""
    player = _make_player("Aldric", str_=15)
    enemy = _make_enemy("Goblin")
    state = start_combat("s1", [player, enemy], dice_roller=lambda: 10)

    assert player.action_budget.action is True
    execute_attack_action(
        state, player.id, enemy.id, "longsword",
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (1, [1]),
    )
    assert player.action_budget.action is False


def test_next_turn_advances_and_resets_budget():
    """next_turn advances turn index and resets action budgets."""
    p1 = _make_player("Aldric")
    p2 = _make_player("Mira")
    state = CombatState(
        session_id="s1",
        combatants=[p1, p2],
        turn_order=[p1.id, p2.id],
        current_turn_index=0,
    )
    p1.action_budget.action = False

    next_turn(state)
    assert state.current_turn_index == 1
    assert p1.action_budget.action is True  # reset
    assert state.current_combatant().id == p2.id


def test_next_turn_skips_dead_combatants():
    """next_turn skips combatants with DEAD status."""
    p1 = _make_player("Aldric")
    e1 = _make_enemy("Goblin")
    e2 = _make_enemy("Orc")
    e1.status = CombatantStatus.DEAD

    state = CombatState(
        session_id="s1",
        combatants=[p1, e1, e2],
        turn_order=[p1.id, e1.id, e2.id],
        current_turn_index=0,
    )

    next_turn(state)
    # Should skip e1 (dead) and land on e2
    assert state.current_turn_index == 2
    assert state.current_combatant().id == e2.id


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_combat_state_persists_across_requests():
    """Combat state can be saved and loaded by session_id."""
    player = _make_player("Aldric")
    enemy = _make_enemy("Goblin")
    state = start_combat("sess-persist", [player, enemy], dice_roller=lambda: 10)

    save_combat_state(state)
    loaded = load_combat_state("sess-persist")

    assert loaded is not None
    assert loaded.session_id == "sess-persist"
    assert len(loaded.combatants) == 2
    assert loaded.get_combatant(player.id).hp == player.hp

    # Mutate original, reload should be independent
    player.hp = 1
    reloaded = load_combat_state("sess-persist")
    assert reloaded.get_combatant(player.id).hp == player.hp_max


def test_clear_combat_state():
    """Clearing a combat state removes it from persistence."""
    state = start_combat("sess-clear", [_make_player()], dice_roller=lambda: 10)
    save_combat_state(state)
    assert load_combat_state("sess-clear") is not None

    clear_combat_state("sess-clear")
    assert load_combat_state("sess-clear") is None


# ---------------------------------------------------------------------------
# Integration: full attack through execute_attack_action
# ---------------------------------------------------------------------------

def test_execute_attack_applies_damage_and_logs():
    """execute_attack_action updates target HP, logs, and checks end conditions."""
    player = _make_player("Aldric", str_=15)
    enemy = _make_enemy("Goblin", hp=10)
    state = start_combat("s1", [player, enemy], dice_roller=lambda: 10)

    result = execute_attack_action(
        state, player.id, enemy.id, "longsword",
        dice_roller=lambda: 10,
        damage_roller=lambda expr: (4, [4]),
    )
    assert result.hit is True
    assert enemy.hp == 4  # 10 - (4+2 str)
    assert any("hits" in msg for msg in state.log)
    assert state.outcome == CombatOutcome.ONGOING


def test_execute_attack_miss_no_damage():
    """execute_attack_action with a miss does no damage."""
    player = _make_player("Aldric", str_=15)
    enemy = _make_enemy("Goblin", hp=10, ac=20)
    state = start_combat("s1", [player, enemy], dice_roller=lambda: 10)

    result = execute_attack_action(
        state, player.id, enemy.id, "longsword",
        dice_roller=lambda: 10,
    )
    assert result.hit is False
    assert enemy.hp == 10
    assert any("misses" in msg for msg in state.log)

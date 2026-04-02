"""Tests for the rest system (short/long rest)."""

import pytest
from src.rest_system import (
    perform_short_rest,
    perform_long_rest,
    initialize_actor_rest_resources,
    get_hit_die_size,
    roll_hit_die,
    can_rest_in_current_phase,
)
from src.models.state import Actor, AbilityScores, CharacterClass


class TestHitDieSize:
    """Test hit die size by class."""
    
    def test_warrior_hit_die(self):
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=12,
            hp_max=12,
        )
        assert get_hit_die_size(actor.character_class) == 10
    
    def test_mage_hit_die(self):
        actor = Actor(
            id="test-mage",
            name="Test Mage",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(str=8, dex=13, con=12, int=15, wis=14, cha=10),
            hp=8,
            hp_max=8,
        )
        assert get_hit_die_size(actor.character_class) == 6
    
    def test_rogue_hit_die(self):
        actor = Actor(
            id="test-rogue",
            name="Test Rogue",
            character_class=CharacterClass.ROGUE,
            abilities=AbilityScores(str=10, dex=15, con=13, int=12, wis=14, cha=8),
            hp=10,
            hp_max=10,
        )
        assert get_hit_die_size(actor.character_class) == 8


class TestShortRest:
    """Test short rest mechanics."""
    
    def test_short_rest_restores_hp(self):
        """Short rest should restore HP using hit dice."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=5,  # Damaged
            hp_max=12,
            hit_dice_remaining=1,
            hit_dice_total=1,
        )
        
        updated_actor, result = perform_short_rest(actor)
        
        assert result["success"] is True
        assert result["hp_gained"] > 0
        assert updated_actor.hp > actor.hp
        assert updated_actor.hp <= actor.hp_max
        assert updated_actor.hit_dice_remaining == 0
    
    def test_short_rest_consumes_hit_die(self):
        """Short rest should consume one hit die."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=5,
            hp_max=12,
            hit_dice_remaining=2,
            hit_dice_total=2,
        )
        
        updated_actor, result = perform_short_rest(actor)
        
        assert result["success"] is True
        assert updated_actor.hit_dice_remaining == 1
    
    def test_short_rest_fails_when_no_hit_dice(self):
        """Short rest should fail when no hit dice remaining."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=5,
            hp_max=12,
            hit_dice_remaining=0,
            hit_dice_total=1,
        )
        
        updated_actor, result = perform_short_rest(actor)
        
        assert result["success"] is False
        assert "没有剩余的生命骰" in result["message"]
        assert updated_actor.hp == actor.hp  # HP unchanged
    
    def test_short_rest_fails_when_hp_full(self):
        """Short rest should fail when HP is already full."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=12,  # Full HP
            hp_max=12,
            hit_dice_remaining=1,
            hit_dice_total=1,
        )
        
        updated_actor, result = perform_short_rest(actor)
        
        assert result["success"] is False
        assert "HP已满" in result["message"]


class TestLongRest:
    """Test long rest mechanics."""
    
    def test_long_rest_restores_full_hp(self):
        """Long rest should restore HP to maximum."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=3,  # Damaged
            hp_max=12,
            hit_dice_remaining=0,  # No hit dice left
            hit_dice_total=1,
        )
        
        updated_actor, result = perform_long_rest(actor)
        
        assert result["success"] is True
        assert updated_actor.hp == actor.hp_max
        assert result["hp_gained"] == 9
    
    def test_long_rest_restores_hit_dice(self):
        """Long rest should restore all hit dice."""
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=5,
            hp_max=12,
            hit_dice_remaining=0,
            hit_dice_total=1,
        )
        
        updated_actor, result = perform_long_rest(actor)
        
        assert result["success"] is True
        assert updated_actor.hit_dice_remaining == updated_actor.hit_dice_total


class TestInitializeRestResources:
    """Test initialization of rest resources."""
    
    def test_warrior_initialization(self):
        actor = Actor(
            id="test-warrior",
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(str=16, dex=12, con=14, int=10, wis=12, cha=8),
            hp=12,
            hp_max=12,
            level=1,
        )
        
        initialized = initialize_actor_rest_resources(actor)
        
        assert initialized.hit_dice_total == 1
        assert initialized.hit_dice_remaining == 1
    
    def test_mage_initialization_with_spell_slots(self):
        actor = Actor(
            id="test-mage",
            name="Test Mage",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(str=8, dex=13, con=12, int=15, wis=14, cha=10),
            hp=8,
            hp_max=8,
            level=1,
        )
        
        initialized = initialize_actor_rest_resources(actor)
        
        assert initialized.hit_dice_total == 1
        assert initialized.hit_dice_remaining == 1
        assert initialized.spell_slots == {"1": 2}
        assert initialized.spell_slots_max == {"1": 2}


class TestCanRestInPhase:
    """Test rest phase restrictions."""
    
    def test_can_rest_in_exploration(self):
        can_rest, error = can_rest_in_current_phase("exploration")
        assert can_rest is True
        assert error == ""
    
    def test_cannot_rest_in_combat(self):
        can_rest, error = can_rest_in_current_phase("combat")
        assert can_rest is False
        assert "战斗" in error
    
    def test_cannot_rest_in_ended(self):
        can_rest, error = can_rest_in_current_phase("ended")
        assert can_rest is False

"""Unit tests for D&D 5e rules calculation engine."""

from __future__ import annotations

import pytest

from src.rules.calculations import (
    ability_modifier,
    calculate_ac,
    calculate_max_hp,
    calculate_skill_modifier,
    CharacterClass,
    proficiency_bonus,
)


class TestAbilityModifier:
    """Test ability modifier calculation: floor((score-10)/2)"""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (3, -4),   # (3 - 10) // 2 = -3.5 floored to -4
            (8, -1),   # (8 - 10) // 2 = -1
            (9, -1),   # (9 - 10) // 2 = -0.5 floored to -1
            (10, 0),   # (10 - 10) // 2 = 0
            (11, 0),   # (11 - 10) // 2 = 0.5 floored to 0
            (14, 2),   # (14 - 10) // 2 = 2
            (15, 2),   # (15 - 10) // 2 = 2.5 floored to 2
            (18, 4),   # (18 - 10) // 2 = 4
        ],
    )
    def test_ability_modifier_values(self, score: int, expected: int):
        """Verify ability modifier formula for key values."""
        assert ability_modifier(score) == expected

    def test_ability_modifier_10_is_zero(self):
        """Score 10 should give modifier +0."""
        assert ability_modifier(10) == 0

    def test_ability_modifier_15_is_plus_two(self):
        """Score 15 should give modifier +2."""
        assert ability_modifier(15) == 2

    def test_ability_modifier_8_is_minus_one(self):
        """Score 8 should give modifier -1."""
        assert ability_modifier(8) == -1


class TestProficiencyBonus:
    """Test proficiency bonus calculation by level."""

    @pytest.mark.parametrize(
        "level,expected",
        [
            (1, 2),   # Level 1-4: +2
            (2, 2),
            (3, 2),
            (4, 2),
            (5, 3),   # Level 5-8: +3
            (6, 3),
            (7, 3),
            (8, 3),
            (9, 4),   # Level 9-12: +4
            (12, 4),
            (13, 5),  # Level 13-16: +5
            (16, 5),
            (17, 6),  # Level 17-20: +6
            (20, 6),
        ],
    )
    def test_proficiency_bonus_by_level(self, level: int, expected: int):
        """Verify proficiency bonus scales correctly with level."""
        assert proficiency_bonus(level) == expected

    def test_level_1_to_4_is_plus_two(self):
        """Level 1-4 should have proficiency bonus +2."""
        for level in range(1, 5):
            assert proficiency_bonus(level) == 2

    def test_level_5_to_8_is_plus_three(self):
        """Level 5-8 should have proficiency bonus +3."""
        for level in range(5, 9):
            assert proficiency_bonus(level) == 3


class TestCalculateMaxHP:
    """Test HP calculation per class hit die."""

    def test_warrior_level_1_con_plus_two(self):
        """Warrior 1st level with CON +2 (CON 14) should have 12 HP."""
        result = calculate_max_hp(CharacterClass.WARRIOR, con_modifier=2)
        assert result == 12  # 10 (d10 max) + 2

    def test_mage_level_1_con_zero(self):
        """Mage 1st level with CON +0 (CON 10) should have 6 HP."""
        result = calculate_max_hp(CharacterClass.MAGE, con_modifier=0)
        assert result == 6  # 6 (d6 max) + 0

    def test_rogue_level_1_con_plus_one(self):
        """Rogue 1st level with CON +1 (CON 12) should have 9 HP."""
        result = calculate_max_hp(CharacterClass.ROGUE, con_modifier=1)
        assert result == 9  # 8 (d8 max) + 1

    def test_warrior_with_negative_con_modifier(self):
        """Warrior with CON 8 (-1) should have 9 HP."""
        result = calculate_max_hp(CharacterClass.WARRIOR, con_modifier=-1)
        assert result == 9  # 10 - 1


class TestCalculateAC:
    """Test Armor Class calculation."""

    def test_unarmored_dex_14(self):
        """DEX 14 (+2) unarmored should have AC 12."""
        result = calculate_ac(dex_modifier=2)
        assert result == 12  # 10 + 2

    def test_unarmored_dex_14_with_shield(self):
        """DEX 14 (+2) unarmored with shield should have AC 14."""
        result = calculate_ac(dex_modifier=2, has_shield=True)
        assert result == 14  # 10 + 2 + 2

    def test_unarmored_dex_10(self):
        """DEX 10 (+0) unarmored should have AC 10."""
        result = calculate_ac(dex_modifier=0)
        assert result == 10

    def test_custom_base_ac(self):
        """Custom base AC with DEX modifier."""
        result = calculate_ac(dex_modifier=2, base_ac=11)  # Leather armor
        assert result == 13  # 11 + 2


class TestCalculateSkillModifier:
    """Test skill modifier calculation."""

    def test_proficient_skill(self):
        """Proficient skill adds proficiency bonus."""
        result = calculate_skill_modifier(
            ability_modifier=3,  # STR 16
            is_proficient=True,
            prof_bonus=2,
        )
        assert result == 5  # 3 + 2

    def test_non_proficient_skill(self):
        """Non-proficient skill uses only ability modifier."""
        result = calculate_skill_modifier(
            ability_modifier=3,  # STR 16
            is_proficient=False,
            prof_bonus=2,
        )
        assert result == 3  # 3 only

    def test_proficient_with_negative_ability(self):
        """Proficient with negative ability modifier."""
        result = calculate_skill_modifier(
            ability_modifier=-1,  # CHA 8
            is_proficient=True,
            prof_bonus=2,
        )
        assert result == 1  # -1 + 2

    def test_higher_proficiency_bonus(self):
        """Level 5 character with +3 proficiency bonus."""
        result = calculate_skill_modifier(
            ability_modifier=2,  # DEX 14
            is_proficient=True,
            prof_bonus=3,
        )
        assert result == 5  # 2 + 3

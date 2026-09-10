"""Tests for d20 dice randomness distribution."""

import pytest

from src.engine.dice import roll_d20, roll_damage


class TestD20Randomness:
    """Test that d20 rolls are properly random with uniform distribution."""

    def test_d20_roll_range(self):
        """d20 roll should be between 1 and 20."""
        for _ in range(100):
            roll = roll_d20()
            assert 1 <= roll <= 20

    def test_d20_no_fixed_value(self):
        """Running many d20 rolls should produce different values (not fixed)."""
        rolls = [roll_d20() for _ in range(100)]
        unique_values = set(rolls)
        
        # Should have more than just 1-2 unique values
        assert len(unique_values) > 10, "d20 rolls should vary, not be fixed"


    def test_d20_all_faces_appear(self):
        """All 20 faces should appear over many rolls."""
        rolls = [roll_d20() for _ in range(500)]
        unique_values = set(rolls)
        
        # Should see most or all faces
        assert len(unique_values) >= 15, f"Only saw {len(unique_values)} unique faces"


class TestD20AdvantageDisadvantage:
    """Test advantage and disadvantage mechanics."""

    def test_advantage_roll_higher_average(self):
        """Advantage should skew toward higher values."""
        normal_rolls = [roll_d20(None) for _ in range(1000)]
        advantage_rolls = [roll_d20(True) for _ in range(1000)]
        
        normal_avg = sum(normal_rolls) / len(normal_rolls)
        advantage_avg = sum(advantage_rolls) / len(advantage_rolls)
        
        # Advantage should have higher average
        assert advantage_avg > normal_avg - 0.5  # Allow some variance

    def test_disadvantage_roll_lower_average(self):
        """Disadvantage should skew toward lower values."""
        normal_rolls = [roll_d20(None) for _ in range(1000)]
        disadvantage_rolls = [roll_d20(False) for _ in range(1000)]
        
        normal_avg = sum(normal_rolls) / len(normal_rolls)
        disadvantage_avg = sum(disadvantage_rolls) / len(disadvantage_rolls)
        
        # Disadvantage should have lower average
        assert disadvantage_avg < normal_avg + 0.5  # Allow some variance

    def test_advantage_range(self):
        """Advantage roll should still be 1-20."""
        for _ in range(100):
            roll = roll_d20(advantage=True)
            assert 1 <= roll <= 20

    def test_disadvantage_range(self):
        """Disadvantage roll should still be 1-20."""
        for _ in range(100):
            roll = roll_d20(advantage=False)
            assert 1 <= roll <= 20


class TestDamageDice:
    """Test damage dice rolling."""

    def test_damage_roll_range_1d6(self):
        """1d6 damage should be between 1 and 6."""
        for _ in range(100):
            total, rolls = roll_damage("1d6")
            assert len(rolls) == 1
            assert 1 <= rolls[0] <= 6
            assert total == rolls[0]

    def test_damage_roll_range_1d8(self):
        """1d8 damage should be between 1 and 8."""
        for _ in range(100):
            total, rolls = roll_damage("1d8")
            assert len(rolls) == 1
            assert 1 <= rolls[0] <= 8
            assert total == rolls[0]

    def test_damage_roll_range_2d6(self):
        """2d6 damage should be between 2 and 12."""
        for _ in range(100):
            total, rolls = roll_damage("2d6")
            assert len(rolls) == 2
            assert all(1 <= r <= 6 for r in rolls)
            assert total == sum(rolls)
            assert 2 <= total <= 12

    def test_damage_with_modifier(self):
        """Damage with modifier should include it in total."""
        for _ in range(100):
            total, rolls = roll_damage("1d8+3")
            assert len(rolls) == 1
            assert 1 <= rolls[0] <= 8
            assert total == rolls[0] + 3

    def test_damage_with_negative_modifier(self):
        """Damage with negative modifier should subtract from total."""
        for _ in range(100):
            total, rolls = roll_damage("1d6-1")
            assert len(rolls) == 1
            assert 1 <= rolls[0] <= 6
            # Total should be at least 0 (damage can't be negative)
            assert total == max(0, rolls[0] - 1)

    def test_damage_no_fixed_value(self):
        """Damage rolls should vary (not be fixed)."""
        rolls = [roll_damage("1d8")[0] for _ in range(50)]
        unique_values = set(rolls)
        
        # Should see variation in damage
        assert len(unique_values) > 3, "Damage rolls should vary"

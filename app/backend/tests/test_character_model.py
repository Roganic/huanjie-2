"""Unit tests for the Character data model."""

from __future__ import annotations

import pytest

from src.models.character import (
    AbilityScores,
    Character,
    CharacterClass,
    Equipment,
)


class TestCharacterCreation:
    """Test basic character creation."""

    def test_create_warrior(self):
        """Can create a warrior character."""
        char = Character(
            name="Test Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 16, "dex": 14, "con": 14,
                "int": 10, "wis": 12, "cha": 10
            })
        )
        assert char.name == "Test Warrior"
        assert char.character_class == CharacterClass.WARRIOR
        assert char.level == 1

    def test_create_mage(self):
        """Can create a mage character."""
        char = Character(
            name="Test Mage",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 8, "dex": 13, "con": 12,
                "int": 15, "wis": 14, "cha": 10
            })
        )
        assert char.character_class == CharacterClass.MAGE

    def test_create_rogue(self):
        """Can create a rogue character."""
        char = Character(
            name="Test Rogue",
            character_class=CharacterClass.ROGUE,
            abilities=AbilityScores(**{
                "str": 10, "dex": 15, "con": 13,
                "int": 12, "wis": 14, "cha": 8
            })
        )
        assert char.character_class == CharacterClass.ROGUE


class TestAbilityModifiers:
    """Test computed ability modifiers."""

    def test_modifiers_computed_from_scores(self):
        """Modifiers are computed from ability scores."""
        char = Character(
            name="Mod Test",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 16, "dex": 14, "con": 14,
                "int": 10, "wis": 12, "cha": 8
            })
        )
        assert char.str_modifier == 3   # (16-10)//2
        assert char.dex_modifier == 2   # (14-10)//2
        assert char.con_modifier == 2   # (14-10)//2
        assert char.int_modifier == 0   # (10-10)//2
        assert char.wis_modifier == 1   # (12-10)//2
        assert char.cha_modifier == -1  # (8-10)//2


class TestProficiencyBonus:
    """Test proficiency bonus calculation."""

    def test_level_1_proficiency(self):
        """Level 1 has +2 proficiency bonus."""
        char = Character(
            name="Level 1",
            character_class=CharacterClass.WARRIOR,
            level=1,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.proficiency_bonus == 2

    def test_level_5_proficiency(self):
        """Level 5 has +3 proficiency bonus."""
        char = Character(
            name="Level 5",
            character_class=CharacterClass.WARRIOR,
            level=5,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.proficiency_bonus == 3

    def test_level_9_proficiency(self):
        """Level 9 has +4 proficiency bonus."""
        char = Character(
            name="Level 9",
            character_class=CharacterClass.WARRIOR,
            level=9,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.proficiency_bonus == 4


class TestMaxHP:
    """Test HP calculation by class."""

    def test_warrior_hp_con_plus_two(self):
        """Warrior level 1, CON +2 (CON 14) should have 12 HP."""
        char = Character(
            name="Warrior",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 14,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.max_hp == 12  # 10 (d10) + 2

    def test_mage_hp_con_zero(self):
        """Mage level 1, CON +0 (CON 10) should have 6 HP."""
        char = Character(
            name="Mage",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.max_hp == 6  # 6 (d6) + 0

    def test_rogue_hp_con_zero(self):
        """Rogue level 1, CON +0 (CON 10) should have 8 HP."""
        char = Character(
            name="Rogue",
            character_class=CharacterClass.ROGUE,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.max_hp == 8  # 8 (d8) + 0

    def test_initial_hp_equals_max(self):
        """Current HP should default to max HP."""
        char = Character(
            name="HP Test",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 14,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.current_hp == char.max_hp
        assert char.current_hp == 12


class TestACCalculation:
    """Test Armor Class calculation."""

    def test_unarmored_dex_14(self):
        """DEX 14 (+2), unarmored: AC 12."""
        char = Character(
            name="AC Test",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 10, "dex": 14, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert char.ac == 12  # 10 + 2

    def test_unarmored_dex_14_with_shield(self):
        """DEX 14 (+2), unarmored with shield: AC 14."""
        char = Character(
            name="AC Shield Test",
            character_class=CharacterClass.MAGE,
            abilities=AbilityScores(**{
                "str": 10, "dex": 14, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            }),
            equipment=Equipment(has_shield=True)
        )
        assert char.ac == 14  # 10 + 2 + 2

    def test_warrior_heavy_armor_no_dex(self):
        """Warrior with heavy armor uses base AC, no DEX."""
        char = Character(
            name="Warrior AC",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 10, "dex": 8, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            }),
            equipment=Equipment(armor_base_ac=16)
        )
        assert char.ac == 16  # Heavy armor base AC, DEX ignored


class TestSkillModifiers:
    """Test skill modifier calculation."""

    def test_skill_uses_ability_modifier(self):
        """Skill modifier equals ability modifier when not proficient."""
        char = Character(
            name="Skill Test",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 16, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            }),
            skill_proficiencies=set()  # No proficiencies
        )
        # Athletics uses STR, no proficiency
        athletics = next(s for s in char.skills if s.name == "athletics")
        assert athletics.modifier == 3  # STR mod only

    def test_proficient_skill_adds_bonus(self):
        """Proficient skill adds proficiency bonus."""
        char = Character(
            name="Skill Test",
            character_class=CharacterClass.WARRIOR,
            level=1,
            abilities=AbilityScores(**{
                "str": 16, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            }),
            skill_proficiencies={"athletics"}  # Proficient in athletics
        )
        # Athletics uses STR, with proficiency
        athletics = next(s for s in char.skills if s.name == "athletics")
        assert athletics.modifier == 5  # STR mod (3) + prof (2)

    def test_skill_list_has_all_skills(self):
        """Character has all 18 skills defined."""
        char = Character(
            name="Skill Test",
            character_class=CharacterClass.WARRIOR,
            abilities=AbilityScores(**{
                "str": 10, "dex": 10, "con": 10,
                "int": 10, "wis": 10, "cha": 10
            })
        )
        assert len(char.skills) == 18
        skill_names = {s.name for s in char.skills}
        expected = {
            "athletics", "acrobatics", "sleight_of_hand", "stealth",
            "arcana", "history", "investigation", "nature", "religion",
            "animal_handling", "insight", "medicine", "perception", "survival",
            "deception", "intimidation", "performance", "persuasion"
        }
        assert skill_names == expected


class TestCharacterCard:
    """Test character card export format."""

    def test_to_card_structure(self):
        """Character card has expected structure."""
        char = Character(
            name="Card Test",
            character_class=CharacterClass.WARRIOR,
            level=1,
            abilities=AbilityScores(**{
                "str": 16, "dex": 14, "con": 14,
                "int": 10, "wis": 12, "cha": 10
            })
        )
        card = char.to_card()
        
        assert card["name"] == "Card Test"
        assert card["class"] == "warrior"
        assert card["level"] == 1
        assert card["proficiency_bonus"] == 2
        
        # Attributes
        assert "attributes" in card
        for attr in ["str", "dex", "con", "int", "wis", "cha"]:
            assert attr in card["attributes"]
            assert "score" in card["attributes"][attr]
            assert "modifier" in card["attributes"][attr]
        
        # HP
        assert "hp" in card
        assert card["hp"]["max"] == char.max_hp
        assert card["hp"]["current"] == char.current_hp
        
        # AC
        assert "ac" in card
        
        # Skills
        assert "skills" in card
        assert len(card["skills"]) > 0
        for skill in card["skills"]:
            assert "name" in skill
            assert "ability" in skill
            assert "proficient" in skill
            assert "modifier" in skill

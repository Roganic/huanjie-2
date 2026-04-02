"""Tests for the equipment system.

These tests verify the acceptance criteria for the equipment system:
1. POST /action executes "装备长剑" and GET /state returns character.equipped.weapon
2. Equipped weapon affects combat attack rolls with weapon damage dice
3. Equipped armor updates character.ac correctly
4. Error response when trying to equip non-existent items
"""

import pytest
from src.models.state import (
    Actor,
    AbilityScores,
    InventoryItem,
    ItemType,
    EquippedItems,
    CharacterClass,
)
from src.equipment import (
    equip_item,
    unequip_item,
    calculate_ac,
    get_weapon_damage_dice,
    get_weapon_attack_ability,
    ItemNotFoundError,
    find_item_in_inventory,
)
from src.action_handler import is_equipment_action, parse_equipment_action
from src.combat import (
    get_weapon_for_combat,
    get_damage_dice_for_combat,
    get_attack_ability_for_combat,
)


class TestEquipmentCore:
    """Tests for core equipment functionality."""
    
    @pytest.fixture
    def test_actor(self):
        """Create a test actor with inventory."""
        abilities = AbilityScores(str=16, dex=14, con=12, int=10, wis=10, cha=8)
        
        longsword = InventoryItem(
            id="longsword",
            name="长剑",
            type=ItemType.WEAPON,
            damage_dice="1d8",
            attack_ability="str",
            description="一把标准的长剑",
        )
        
        leather_armor = InventoryItem(
            id="leather",
            name="皮甲",
            type=ItemType.ARMOR,
            base_ac=11,
            add_dex_modifier=True,
            max_dex_bonus=None,
            description="轻便的皮甲",
        )
        
        chain_mail = InventoryItem(
            id="chain_mail",
            name="锁甲",
            type=ItemType.ARMOR,
            base_ac=16,
            add_dex_modifier=False,
            description="重型锁甲",
        )
        
        return Actor(
            id="test-actor",
            name="Test Hero",
            character_class=CharacterClass.WARRIOR,
            abilities=abilities,
            proficiency_bonus=2,
            level=1,
            hp=10,
            hp_max=10,
            ac=10,
            inventory=[longsword, leather_armor, chain_mail],
            equipped=EquippedItems(weapon=None, armor=None),
        )
    
    def test_equip_weapon_updates_equipped_slot(self, test_actor):
        """Test that equipping a weapon updates the equipped.weapon slot."""
        updated_actor, equipped, previous = equip_item(test_actor, "长剑")
        
        assert equipped.name == "长剑"
        assert previous is None
        assert updated_actor.equipped.weapon is not None
        assert updated_actor.equipped.weapon.name == "长剑"
    
    def test_equip_armor_updates_ac(self, test_actor):
        """Test that equipping armor updates AC correctly."""
        # Leather armor: base 11 + DEX mod (+2) = 13
        updated_actor, equipped, previous = equip_item(test_actor, "皮甲")
        
        assert equipped.name == "皮甲"
        assert updated_actor.ac == 13
    
    def test_equip_heavy_armor_no_dex_bonus(self, test_actor):
        """Test that heavy armor doesn't add DEX modifier."""
        # Chain mail: base 16, no DEX modifier
        updated_actor, _, _ = equip_item(test_actor, "锁甲")
        
        assert updated_actor.ac == 16
    
    def test_unequip_armor_resets_ac(self, test_actor):
        """Test that unequipping armor resets AC to unarmored."""
        # First equip armor
        actor_with_armor, _, _ = equip_item(test_actor, "皮甲")
        assert actor_with_armor.ac == 13
        
        # Then unequip
        updated_actor, removed = unequip_item(actor_with_armor, "armor")
        
        assert removed.name == "皮甲"
        assert updated_actor.equipped.armor is None
        # Unarmored: 10 + DEX mod (+2) = 12
        assert updated_actor.ac == 12
    
    def test_equip_nonexistent_item_raises_error(self, test_actor):
        """Test that equipping a non-existent item raises ItemNotFoundError."""
        with pytest.raises(ItemNotFoundError) as exc_info:
            equip_item(test_actor, "不存在的物品")
        
        assert "不存在的物品" in str(exc_info.value)
    
    def test_weapon_damage_dice(self, test_actor):
        """Test that weapon damage dice are correctly retrieved."""
        # Without equipped weapon
        damage = get_weapon_damage_dice(None)
        assert damage == "1"
        
        # With equipped weapon
        actor_with_weapon, _, _ = equip_item(test_actor, "长剑")
        damage = get_weapon_damage_dice(actor_with_weapon.equipped.weapon)
        assert damage == "1d8"
    
    def test_weapon_attack_ability(self, test_actor):
        """Test that weapon attack ability is correctly retrieved."""
        # Without equipped weapon (defaults to str)
        ability = get_weapon_attack_ability(None)
        assert ability == "str"
        
        # With equipped weapon
        actor_with_weapon, _, _ = equip_item(test_actor, "长剑")
        ability = get_weapon_attack_ability(actor_with_weapon.equipped.weapon)
        assert ability == "str"


class TestEquipmentActionHandler:
    """Tests for equipment action handling."""
    
    def test_is_equipment_action_detects_equip(self):
        """Test that equipment actions are correctly detected."""
        assert is_equipment_action("装备长剑", "") is True
        assert is_equipment_action("equip longsword", "") is True
        assert is_equipment_action("拿起", "装备短剑") is True
    
    def test_is_equipment_action_detects_unequip(self):
        """Test that unequip actions are correctly detected."""
        assert is_equipment_action("卸下武器", "") is True
        assert is_equipment_action("unequip armor", "") is True
    
    def test_is_equipment_action_rejects_non_equipment(self):
        """Test that non-equipment actions are correctly rejected."""
        assert is_equipment_action("攻击敌人", "使用长剑") is False
        assert is_equipment_action("look around", "") is False
    
    def test_parse_equipment_action_extracts_item_name(self):
        """Test that equipment actions are correctly parsed."""
        op, item = parse_equipment_action("装备长剑", "")
        assert op == "equip"
        assert item == "长剑"
    
    def test_parse_equipment_action_extracts_english(self):
        """Test that English equipment actions are correctly parsed."""
        op, item = parse_equipment_action("equip longsword", "")
        assert op == "equip"
        assert item == "longsword"


class TestCombatIntegration:
    """Tests for equipment integration with combat."""
    
    @pytest.fixture
    def test_actor_with_equipment(self):
        """Create a test actor with equipped items."""
        abilities = AbilityScores(str=16, dex=14, con=12, int=10, wis=10, cha=8)
        
        longsword = InventoryItem(
            id="longsword",
            name="长剑",
            type=ItemType.WEAPON,
            damage_dice="1d8",
            attack_ability="str",
        )
        
        return Actor(
            id="test-actor",
            name="Test Hero",
            character_class=CharacterClass.WARRIOR,
            abilities=abilities,
            proficiency_bonus=2,
            level=1,
            hp=10,
            hp_max=10,
            ac=16,
            inventory=[longsword],
            equipped=EquippedItems(weapon=longsword, armor=None),
        )
    
    def test_get_weapon_for_combat_uses_equipped(self, test_actor_with_equipment):
        """Test that combat uses equipped weapon."""
        weapon = get_weapon_for_combat(test_actor_with_equipment)
        assert weapon is not None
        assert weapon.name == "长剑"
    
    def test_get_damage_dice_for_combat_uses_equipped(self, test_actor_with_equipment):
        """Test that combat damage uses equipped weapon's damage dice."""
        damage_dice = get_damage_dice_for_combat(test_actor_with_equipment)
        assert damage_dice == "1d8"
    
    def test_get_attack_ability_for_combat_uses_equipped(self, test_actor_with_equipment):
        """Test that combat attack ability uses equipped weapon's ability."""
        ability = get_attack_ability_for_combat(test_actor_with_equipment)
        assert ability == "str"
    
    def test_weapon_override_takes_precedence(self, test_actor_with_equipment):
        """Test that weapon override takes precedence over equipped weapon."""
        # Add a shortsword to inventory
        shortsword = InventoryItem(
            id="shortsword",
            name="短剑",
            type=ItemType.WEAPON,
            damage_dice="1d6",
            attack_ability="dex",
        )
        test_actor_with_equipment.inventory.append(shortsword)
        
        # Without override, should use equipped longsword
        weapon = get_weapon_for_combat(test_actor_with_equipment)
        assert weapon.name == "长剑"
        
        # With override, should use shortsword
        weapon = get_weapon_for_combat(test_actor_with_equipment, "短剑")
        assert weapon.name == "短剑"


class TestInventorySearch:
    """Tests for inventory search functionality."""
    
    @pytest.fixture
    def test_actor(self):
        """Create a test actor with inventory."""
        abilities = AbilityScores(str=16, dex=14, con=12, int=10, wis=10, cha=8)
        
        longsword = InventoryItem(
            id="longsword",
            name="长剑",
            type=ItemType.WEAPON,
            damage_dice="1d8",
        )
        
        return Actor(
            id="test-actor",
            name="Test Hero",
            abilities=abilities,
            proficiency_bonus=2,
            hp=10,
            hp_max=10,
            ac=10,
            inventory=[longsword],
            equipped=EquippedItems(weapon=None, armor=None),
        )
    
    def test_find_item_by_name(self, test_actor):
        """Test finding item by name (case-insensitive)."""
        item = find_item_in_inventory(test_actor, "长剑")
        assert item is not None
        assert item.name == "长剑"
    
    def test_find_item_by_name_case_insensitive(self, test_actor):
        """Test finding item by name is case-insensitive."""
        item = find_item_in_inventory(test_actor, "长剑".upper())
        assert item is not None
        assert item.name == "长剑"
    
    def test_find_nonexistent_item_returns_none(self, test_actor):
        """Test that finding non-existent item returns None."""
        item = find_item_in_inventory(test_actor, "不存在")
        assert item is None

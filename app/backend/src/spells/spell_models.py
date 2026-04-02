"""Spell data models."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class DamageType(str, Enum):
    """Types of spell damage."""
    FORCE = "force"           # 力场
    FIRE = "fire"             # 火焰
    COLD = "cold"             # 冷冻
    LIGHTNING = "lightning"   # 闪电
    THUNDER = "thunder"       # 雷鸣
    ACID = "acid"             # 强酸
    POISON = "poison"         # 毒素
    NECROTIC = "necrotic"     # 死灵
    RADIANT = "radiant"       # 光耀
    PSYCHIC = "psychic"       # 心灵


class SpellSchool(str, Enum):
    """D&D 5e spell schools."""
    EVOCATION = "evocation"       # 塑能
    CONJURATION = "conjuration"   # 咒法
    TRANSMUTATION = "transmutation"  # 变化
    ENCHANTMENT = "enchantment"   # 惑控
    ILLUSION = "illusion"         # 幻术
    DIVINATION = "divination"     # 预言
    ABJURATION = "abjuration"     # 防护
    NECROMANCY = "necromancy"     # 死灵


class SpellSlot(BaseModel):
    """Spell slot information for a character."""
    level: int           # Spell level (1-9)
    max: int             # Maximum slots at this level
    current: int         # Current available slots
    
    model_config = {"populate_by_name": True}


class SpellCastResult(BaseModel):
    """Result of casting a spell."""
    success: bool
    spell_name: str
    slot_level: int
    target: Optional[str] = None
    damage: Optional[int] = None
    damage_type: Optional[DamageType] = None
    damage_rolls: list[int] = []
    damage_modifier: int = 0
    saving_throw_required: bool = False
    saving_throw_ability: Optional[str] = None
    saving_throw_dc: Optional[int] = None
    hit: Optional[bool] = None  # For attack roll spells
    attack_roll: Optional[int] = None  # d20 roll for attack
    attack_total: Optional[int] = None  # Total attack roll
    target_ac: Optional[int] = None
    auto_hit: bool = False  # For spells like Magic Missile that always hit
    narrative: str = ""
    effects: list[dict] = []
    error_message: Optional[str] = None
    
    model_config = {"populate_by_name": True}


class Spell(BaseModel):
    """Spell definition."""
    id: str
    name: str
    name_cn: str                    # Chinese name
    level: int                      # Spell level (0 = cantrip, 1-9)
    school: SpellSchool
    damage_dice: Optional[str] = None      # e.g., "1d4", "3d6"
    damage_type: Optional[DamageType] = None
    num_projectiles: int = 1        # For multi-projectile spells like Magic Missile
    saving_throw_ability: Optional[str] = None  # For spells requiring saves (dex/con/etc)
    saving_throw_dc_base: int = 8   # Base DC before proficiency and ability mod
    requires_attack_roll: bool = False  # True for spells like Ray of Frost
    auto_hit: bool = False          # True for spells like Magic Missile
    range_ft: int = 60              # Range in feet
    casting_time: str = "1 action"
    description: str = ""
    # Healing spells
    healing_dice: Optional[str] = None     # e.g., "1d8"
    healing_bonus_ability: Optional[str] = None  # Ability for healing bonus (int/wis/etc)
    
    # Class spell lists this spell belongs to
    available_to: list[str] = []    # ["mage", "cleric", etc.]
    
    model_config = {"populate_by_name": True}
    
    def get_spell_dc(self, spell_attack_ability_mod: int, proficiency_bonus: int) -> int:
        """Calculate spell save DC."""
        return self.saving_throw_dc_base + proficiency_bonus + spell_attack_ability_mod
    
    def get_attack_bonus(self, spell_attack_ability_mod: int, proficiency_bonus: int) -> int:
        """Calculate spell attack bonus."""
        return proficiency_bonus + spell_attack_ability_mod

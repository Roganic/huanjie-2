"""Spell system for mage characters."""

from .spell_models import Spell, SpellSlot, SpellCastResult, DamageType, SpellSchool
from .spell_registry import SPELLS, get_spell, get_spells_for_class
from .spell_resolver import cast_spell, can_cast_spell, consume_spell_slot, restore_spell_slots

__all__ = [
    "Spell",
    "SpellSlot", 
    "SpellCastResult",
    "DamageType",
    "SpellSchool",
    "SPELLS",
    "get_spell",
    "get_spells_for_class",
    "cast_spell",
    "can_cast_spell",
    "consume_spell_slot",
    "restore_spell_slots",
]

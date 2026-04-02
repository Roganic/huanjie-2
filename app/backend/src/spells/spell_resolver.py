"""Spell resolution logic."""

from __future__ import annotations

import random
import re
from typing import Optional

from ..engine.dice import roll_d20, roll_damage
from ..models.state import Actor
from .spell_models import Spell, SpellCastResult, SpellSlot
from .spell_registry import get_spell


def can_cast_spell(actor: Actor, spell: Spell) -> tuple[bool, str]:
    """Check if the actor can cast the spell.
    
    Returns:
        (can_cast, error_message)
    """
    # Check if actor is a spellcaster
    if actor.character_class is None or actor.character_class.value != "mage":
        return False, "只有法师职业可以施放法术。"
    
    # Cantrips (level 0) can always be cast
    if spell.level == 0:
        return True, ""
    
    # Check spell slots
    if actor.spell_slots is None or len(actor.spell_slots) == 0:
        return False, f"你没有 {spell.level} 环法术位。"
    
    # Find appropriate slot
    for slot in actor.spell_slots:
        if slot.level == spell.level and slot.current > 0:
            return True, ""
    
    return False, f"你没有剩余的 {spell.level} 环法术位。"


def consume_spell_slot(actor: Actor, slot_level: int) -> bool:
    """Consume a spell slot of the given level.
    
    Returns:
        True if a slot was consumed, False otherwise
    """
    if actor.spell_slots is None:
        return False
    
    for slot in actor.spell_slots:
        if slot.level == slot_level and slot.current > 0:
            slot.current -= 1
            return True
    
    return False


def restore_spell_slots(actor: Actor, rest_type: str = "long") -> bool:
    """Restore spell slots after rest.
    
    Args:
        actor: The actor to restore slots for
        rest_type: "short" or "long"
    
    Returns:
        True if any slots were restored
    """
    if actor.spell_slots is None:
        return False
    
    # Short rest does not restore spell slots for mages in D&D 5e
    # (unless they have features like Arcane Recovery, which we skip for now)
    if rest_type == "short":
        return False
    
    # Long rest restores all spell slots
    restored = False
    for slot in actor.spell_slots:
        if slot.current < slot.max:
            slot.current = slot.max
            restored = True
    
    return restored


def _calculate_spell_attack_mod(actor: Actor) -> int:
    """Calculate spell attack ability modifier (INT for mages)."""
    return actor.abilities.modifier("int")


def _calculate_spell_dc(actor: Actor, spell: Spell) -> int:
    """Calculate spell save DC."""
    spell_attack_mod = _calculate_spell_attack_mod(actor)
    return spell.get_spell_dc(spell_attack_mod, actor.proficiency_bonus)


def cast_spell(
    caster: Actor,
    spell_name: str,
    target: Optional[Actor] = None,
) -> SpellCastResult:
    """Cast a spell and return the result.
    
    Args:
        caster: The actor casting the spell
        spell_name: Name or ID of the spell
        target: The target of the spell (optional)
    
    Returns:
        SpellCastResult with all details of the cast
    """
    # Look up the spell
    spell = get_spell(spell_name)
    if spell is None:
        return SpellCastResult(
            success=False,
            spell_name=spell_name,
            slot_level=0,
            error_message=f"未知的法术: {spell_name}",
        )
    
    # Check class restriction
    if caster.character_class is None or caster.character_class.value != "mage":
        return SpellCastResult(
            success=False,
            spell_name=spell.name_cn,
            slot_level=spell.level,
            error_message="只有法师职业可以施放法术。",
        )
    
    # Check if can cast
    can_cast, error = can_cast_spell(caster, spell)
    if not can_cast:
        return SpellCastResult(
            success=False,
            spell_name=spell.name_cn,
            slot_level=spell.level,
            error_message=error,
        )
    
    # Consume spell slot (for non-cantrips)
    if spell.level > 0:
        consumed = consume_spell_slot(caster, spell.level)
        if not consumed:
            return SpellCastResult(
                success=False,
                spell_name=spell.name_cn,
                slot_level=spell.level,
                error_message=f"你没有剩余的 {spell.level} 环法术位。",
            )
    
    # Prepare result
    result = SpellCastResult(
        success=True,
        spell_name=spell.name_cn,
        slot_level=spell.level,
        target=target.name if target else None,
        auto_hit=spell.auto_hit,
    )
    
    # Handle auto-hit spells (like Magic Missile)
    if spell.auto_hit and spell.damage_dice:
        # Roll damage for each projectile
        total_damage = 0
        all_rolls = []
        
        for _ in range(spell.num_projectiles):
            dmg, rolls = roll_damage(spell.damage_dice)
            total_damage += dmg
            all_rolls.extend(rolls)
        
        result.damage = total_damage
        result.damage_rolls = all_rolls
        result.damage_type = spell.damage_type
        
        if target:
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"{spell.num_projectiles} 支魔法飞弹自动命中 {target.name}，"
                f"造成 {total_damage} 点 {spell.damage_type.value if spell.damage_type else ''}伤害！"
            )
        else:
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"造成 {total_damage} 点伤害！"
            )
        
        return result
    
    # Handle attack roll spells (like Ray of Frost)
    if spell.requires_attack_roll and spell.damage_dice:
        spell_attack_mod = _calculate_spell_attack_mod(caster)
        attack_bonus = spell.get_attack_bonus(spell_attack_mod, caster.proficiency_bonus)
        
        attack_roll = roll_d20()
        attack_total = attack_roll + attack_bonus
        
        result.attack_roll = attack_roll
        result.attack_total = attack_total
        result.target_ac = target.ac if target else 10
        
        # Check hit
        if target and attack_total >= target.ac:
            result.hit = True
            dmg, rolls = roll_damage(spell.damage_dice)
            result.damage = dmg
            result.damage_rolls = rolls
            result.damage_type = spell.damage_type
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"攻击检定: d20={attack_roll} + {attack_bonus} = {attack_total} vs AC {target.ac} 命中！"
                f"造成 {dmg} 点 {spell.damage_type.value if spell.damage_type else ''}伤害！"
            )
        else:
            result.hit = False
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"攻击检定: d20={attack_roll} + {attack_bonus} = {attack_total} vs AC {result.target_ac} 未命中。"
            )
        
        return result
    
    # Handle saving throw spells (like Burning Hands)
    if spell.saving_throw_ability and spell.damage_dice:
        dc = _calculate_spell_dc(caster, spell)
        result.saving_throw_required = True
        result.saving_throw_ability = spell.saving_throw_ability
        result.saving_throw_dc = dc
        
        # For simplicity, assume target fails save (or we could roll)
        # In a real implementation, we'd roll the target's saving throw
        dmg, rolls = roll_damage(spell.damage_dice)
        result.damage = dmg
        result.damage_rolls = rolls
        result.damage_type = spell.damage_type
        
        if target:
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"{target.name} 尝试 {spell.saving_throw_ability.upper()} 豁免 (DC {dc})... 失败！"
                f"受到 {dmg} 点 {spell.damage_type.value if spell.damage_type else ''}伤害！"
            )
        else:
            result.narrative = (
                f"{caster.name} 施放 {spell.name_cn}，"
                f"造成 {dmg} 点伤害！"
            )
        
        return result
    
    # Generic spell (no damage)
    result.narrative = f"{caster.name} 施放 {spell.name_cn}。"
    return result


def parse_cast_command(intent: str) -> tuple[Optional[str], Optional[str]]:
    """Parse a spell cast command like "施放魔法飞弹攻击哥布林".
    
    Returns:
        (spell_name, target_name) or (None, None) if not a cast command
    """
    # Cast command patterns
    cast_patterns = [
        r"施放?\s*([\u4e00-\u9fa5]+)\s*(?:攻击|对|目标)?\s*([\u4e00-\u9fa5]+)?",
        r"cast\s+(\w+(?:\s+\w+)*)\s*(?:at|on|target)?\s*(\w+(?:\s+\w+)*?)?",
        r"使用?\s*([\u4e00-\u9fa5]+)",
        r"use\s+(\w+)",
    ]
    
    for pattern in cast_patterns:
        match = re.search(pattern, intent, re.IGNORECASE)
        if match:
            spell_name = match.group(1).strip() if match.group(1) else None
            target_name = match.group(2).strip() if match.group(2) and len(match.groups()) > 1 else None
            return spell_name, target_name
    
    return None, None


def is_cast_command(intent: str) -> bool:
    """Check if the intent is a spell cast command."""
    cast_keywords = ["施放", "cast", "使用", "use"]
    spell_names = ["魔法飞弹", "燃烧之手", "寒冰射线", "magic missile", "burning hands", "ray of frost"]
    
    intent_lower = intent.lower()
    
    # Check for cast keywords
    has_cast_keyword = any(kw in intent_lower for kw in cast_keywords)
    
    # Check for spell names
    has_spell_name = any(name.lower() in intent_lower for name in spell_names)
    
    return has_cast_keyword and has_spell_name


def is_rest_command(intent: str) -> tuple[bool, str]:
    """Check if the intent is a rest command.
    
    Returns:
        (is_rest, rest_type) where rest_type is "short" or "long"
    """
    intent_lower = intent.lower()
    
    # Long rest patterns
    long_rest_patterns = ["长休", "long rest", "休息", "rest"]
    for pattern in long_rest_patterns:
        if pattern in intent_lower:
            return True, "long"
    
    # Short rest patterns
    short_rest_patterns = ["短休", "short rest"]
    for pattern in short_rest_patterns:
        if pattern in intent_lower:
            return True, "short"
    
    return False, ""

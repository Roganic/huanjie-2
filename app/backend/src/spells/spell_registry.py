"""Spell registry - defines all available spells."""

from .spell_models import Spell, DamageType, SpellSchool

# ---------------------------------------------------------------------------
# Level 1 Spells
# ---------------------------------------------------------------------------

MAGIC_MISSILE = Spell(
    id="magic_missile",
    name="Magic Missile",
    name_cn="魔法飞弹",
    level=1,
    school=SpellSchool.EVOCATION,
    damage_dice="1d4+1",
    damage_type=DamageType.FORCE,
    num_projectiles=3,
    auto_hit=True,
    range_ft=120,
    casting_time="1 action",
    description="你创造三支由魔法能量构成的飞镖，自动命中目标。每支造成 1d4+1 力场伤害。",
    available_to=["mage"],
)

BURNING_HANDS = Spell(
    id="burning_hands",
    name="Burning Hands",
    name_cn="燃烧之手",
    level=1,
    school=SpellSchool.EVOCATION,
    damage_dice="3d6",
    damage_type=DamageType.FIRE,
    saving_throw_ability="dex",
    saving_throw_dc_base=8,
    range_ft=15,
    casting_time="1 action",
    description="你双手向前伸展，释放出一道 15 尺锥形的火焰。目标必须通过敏捷豁免，失败则受到 3d6 火焰伤害。",
    available_to=["mage"],
)

RAY_OF_FROST = Spell(
    id="ray_of_frost",
    name="Ray of Frost",
    name_cn="寒冰射线",
    level=0,  # Cantrip
    school=SpellSchool.EVOCATION,
    damage_dice="1d8",
    damage_type=DamageType.COLD,
    requires_attack_roll=True,
    range_ft=60,
    casting_time="1 action",
    description="你射出一道冰冷的蓝白色光线，对目标进行远程法术攻击。命中造成 1d8 冷冻伤害。",
    available_to=["mage"],
)

# ---------------------------------------------------------------------------
# Spell Registry
# ---------------------------------------------------------------------------

SPELLS: dict[str, Spell] = {
    "magic_missile": MAGIC_MISSILE,
    "burning_hands": BURNING_HANDS,
    "ray_of_frost": RAY_OF_FROST,
    # Chinese name aliases
    "魔法飞弹": MAGIC_MISSILE,
    "燃烧之手": BURNING_HANDS,
    "寒冰射线": RAY_OF_FROST,
}


def get_spell(name_or_id: str) -> Spell | None:
    """Get a spell by name or ID (case-insensitive)."""
    name_lower = name_or_id.lower().strip()
    
    # Direct lookup
    if name_lower in SPELLS:
        return SPELLS[name_lower]
    
    # Case-insensitive lookup
    for key, spell in SPELLS.items():
        if key.lower() == name_lower:
            return spell
        if spell.name.lower() == name_lower:
            return spell
        if spell.name_cn == name_or_id:
            return spell
    
    return None


def get_spells_for_class(character_class: str, level: int | None = None) -> list[Spell]:
    """Get all spells available to a character class.
    
    Args:
        character_class: The character class (e.g., "mage", "cleric")
        level: If specified, only return spells of this level
    
    Returns:
        List of spells available to the class
    """
    class_lower = character_class.lower()
    spells = [
        spell for spell in SPELLS.values()
        if class_lower in [c.lower() for c in spell.available_to]
    ]
    
    if level is not None:
        spells = [s for s in spells if s.level == level]
    
    # Remove duplicates (since we have aliases in SPELLS)
    seen_ids = set()
    unique_spells = []
    for spell in spells:
        if spell.id not in seen_ids:
            seen_ids.add(spell.id)
            unique_spells.append(spell)
    
    return unique_spells


def get_cantrips_for_class(character_class: str) -> list[Spell]:
    """Get all cantrips (level 0 spells) for a class."""
    return get_spells_for_class(character_class, level=0)

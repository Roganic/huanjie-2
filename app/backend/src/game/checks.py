"""Shared live-game D20 resolution; attack rolls remain in the combat rules."""
from ..models.action import CheckDetail

SAVE_PROFICIENCIES = {'warrior': ('str', 'con'), 'rogue': ('dex', 'int'), 'mage': ('int', 'wis')}


def resolve_check(actor, *, skill=None, ability=None, dc, saving_throw=False, advantage=False):
    from ..engine.dice import roll_d20
    from ..engine.resolver import _get_skill_ability, _is_skill_proficient
    from .conditions import advantage_for, consume_inspiration
    ability = _get_skill_ability(skill) if skill else ability
    modifier = actor.abilities.modifier(ability)
    if saving_throw:
        kind = actor.character_class.value if actor.character_class else ''
        proficient = ability in SAVE_PROFICIENCIES.get(kind, ())
        advantage_state = None
    else:
        proficient = bool(skill and _is_skill_proficient(actor, skill))
        advantage_state = advantage_for(actor, advantage=advantage)
    proficiency = actor.proficiency_bonus if proficient else 0
    rolls = [roll_d20(), roll_d20()] if advantage_state is not None else [roll_d20()]
    roll = min(rolls) if advantage_state is False else max(rolls)
    if not saving_throw:
        consume_inspiration(actor)
    return CheckDetail(ability=ability, modifier=modifier, proficiency_bonus=proficiency, roll=roll,
        total=roll+modifier+proficiency, dc=dc, skill_name=skill, advantage=advantage_state)

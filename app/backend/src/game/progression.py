"""One XP/level update for both quest rewards and combat rewards."""
from ..rules.experience import calculate_level_up
from ..rules.calculations import calculate_max_hp
from ..rest_system import initialize_actor_rest_resources


def grant_experience(session, amount):
    actor = session.actor
    xp, change = calculate_level_up(actor.level, actor.experience_points, amount,
                                    actor.abilities.modifier('con'), actor.character_class)
    actor.experience_points = xp
    result = dict(xp_gained=amount, total_xp=xp)
    if change and change.leveled_up:
        actor.level = change.new_level
        actor.proficiency_bonus = change.new_proficiency_bonus
        actor.hp_max = calculate_max_hp(actor.character_class, actor.abilities.modifier('con'), actor.level)
        actor.hp = actor.hp_max
        session.actor = actor = initialize_actor_rest_resources(actor)
        for skill in actor.skills:
            skill.modifier = actor.abilities.modifier(skill.ability) + (actor.proficiency_bonus if skill.proficient else 0)
        result['level_up'] = dict(old_level=change.old_level, new_level=change.new_level,
            hp_increase=change.hp_increase, new_proficiency_bonus=change.new_proficiency_bonus)
    return result

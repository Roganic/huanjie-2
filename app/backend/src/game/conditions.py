"""Small explicit condition rules shared by exploration, combat and recovery."""
RULES = {
    'poisoned': ('中毒', '攻击和技能检定具有劣势；3 个有效行动后、解毒剂或长休解除。'),
    'inspired': ('鼓舞', '下一次攻击或技能检定具有优势，使用后解除。'),
    'hidden': ('佯攻准备', '下次武器攻击具有优势，攻击后或离开战斗解除。'),
    'defending': ('防御', '敌人攻击具有劣势，持续到下次轮到你。'),
    'defeated': ('倒下', '本次冒险失败，请读档或重新冒险。'),
}


def add_condition(actor, name):
    if name not in actor.conditions:
        actor.conditions.append(name)
    if name == 'poisoned':
        actor.condition_turns[name] = 3


def remove_condition(actor, name):
    actor.conditions = [c for c in actor.conditions if c != name]
    actor.condition_turns.pop(name, None)


def advantage_for(actor, *, advantage=False, disadvantage=False):
    positive = advantage or 'inspired' in actor.conditions or 'advantage' in actor.conditions
    negative = disadvantage or 'poisoned' in actor.conditions or 'disadvantage' in actor.conditions
    return None if positive == negative else bool(positive)


def consume_inspiration(actor):
    remove_condition(actor, 'inspired')


def advance_time(session, amount=1):
    session.scene.time += amount
    from .events import advance_world
    if session.game_phase.value != "combat":
        advance_world(session, amount)
    actor = session.actor
    if actor:
        for name, remaining in list(actor.condition_turns.items()):
            if remaining <= amount:
                remove_condition(actor, name)
            else:
                actor.condition_turns[name] = remaining - amount


def condition_views(actor):
    return [dict(id=c, name=RULES.get(c,(c,''))[0], description=RULES.get(c,('', '旧内容状态，当前基础规则不额外结算。'))[1],
                 remaining=actor.condition_turns.get(c)) for c in actor.conditions]

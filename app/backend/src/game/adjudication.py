"""Rule-owned challenges: choose the contract before dice, then commit only its consequences."""
import hashlib
import json
from fastapi import HTTPException
from ..content.store import for_session
from ..models.adjudication import ChallengeDefinition, ChallengeChoice
from ..models.events import EventSpec, EventEffect
from ..models.action import CheckDetail, SavingThrowDetail
from .events import schedule, drain

SOCIAL_SKILLS = {'persuasion': '说服', 'deception': '欺瞒', 'intimidation': '威吓', 'performance': '表演'}


def challenges(session):
    """Authored affordances plus bounded social improvisation; no invented objects or loot."""
    from .world import scene_view
    pack = for_session(session)
    result = {c.id: c for c in pack.scenes[session.scene.id].challenges}
    for npc in scene_view(session).npcs:
        if npc.type == 'hostile' or not pack.characters[npc.id].alive:
            continue
        for skill, label in SOCIAL_SKILLS.items():
            id = f'social:{npc.id}:{skill}'
            result.setdefault(id, ChallengeDefinition(id=id, name=f'{label} · {npc.name}',
                description=f'用{label}影响{npc.name}的态度；不强迫其交物品、泄露秘密或改变任务。',
                target_id=npc.id, skill=skill, dc=15, risk='minor', retry_delay=2,
                stakes='消耗 1 格时间；成功关系 +1，失败关系 -1。获得新线索、剧情条件变化或经过 2 格时间后可再次尝试。',
                on_success=[EventSpec(title='关系改善', narration=f'{npc.name}对你的态度有所改善。', category='social', scope='personal',
                    effects=[EventEffect(kind='relationship', target_id=npc.id, amount=1)])],
                on_failure=[EventSpec(title='关系受损', narration=f'{npc.name}对你的态度变得冷淡。', category='social', scope='personal',
                    effects=[EventEffect(kind='relationship', target_id=npc.id, amount=-1)])]))
    return result


def fingerprint(session, challenge=None):
    # Time, prose, wording and our own relationship rewards cannot reset a challenge.
    if challenge and challenge.retry_flags is not None:
        return hashlib.sha256(json.dumps(sorted(set(challenge.retry_flags) & set(session.content_flags))).encode()).hexdigest()
    return hashlib.sha256(json.dumps({'flags': sorted(session.content_flags),
        'clues': sorted(session.discovered_clues.items())}, ensure_ascii=False).encode()).hexdigest()


def attempt_key(session, challenge):
    if challenge.goal_id:
        return f'{session.scene.id}:{challenge.target_id}:goal:{challenge.goal_id}'
    # Different social skills/wording must not permit endlessly farming one NPC.
    return f'{session.scene.id}:social:{challenge.target_id}' if challenge.id.startswith('social:') else f'{session.scene.id}:{challenge.id}'


def challenge_status(session, challenge):
    from .lifecycle import play_status
    if not play_status(session)['can_explore']:
        return play_status(session)['reason'] or '请先结束战斗。'
    if not set(challenge.required_flags) <= set(session.content_flags):
        return '还不具备这项挑战的前置条件。'
    if challenge.completed_flags and set(challenge.completed_flags) <= set(session.content_flags):
        return '这项目标已经完成。'
    previous = session.challenge_attempts.get(attempt_key(session, challenge))
    if previous and (previous.get('completed') or challenge.complete_on_success and previous.get('success')):
        return '这项目标已经完成。'
    if previous and challenge.retry == 'once':
        return '这次机会已经用过，不能靠换一种做法再次尝试。可以寻找其他线索或推进别的目标。'
    cooled_down = previous and previous.get('retry_event_id') in session.fired_events
    if previous and not cooled_down and challenge.retry == 'after_change' and previous['context'] == fingerprint(session, challenge):
        return '这项尝试已经结算；需要新线索、剧情条件变化或等待已安排的交涉间隔结束，换一种说法不会重新掷骰。'
    return ''


def challenge_view(session):
    result = []
    for c in challenges(session).values():
        if not set(c.required_flags) <= set(session.content_flags):
            continue
        result.append({k: getattr(c, k) for k in ('id', 'name', 'description', 'target_id', 'check_kind', 'skill', 'ability', 'dc', 'risk', 'stakes', 'time_cost')} |
                      {'goal_id': c.goal_id or ('attitude' if c.id.startswith('social:') else c.id),
                       'approaches': [a.model_dump(exclude={'required_flags'}) for a in c.approaches if set(a.required_flags) <= set(session.content_flags)],
                       'consequences': [o.model_dump(include={'id', 'name', 'stakes'}) for o in c.consequences if set(o.required_flags) <= set(session.content_flags)],
                       'blocked_reason': challenge_status(session, c)})
    return result


def no_action(message, *, status='blocked', summary='行动未执行', brief='当前还不能这样做。'):
    return dict(action_summary=summary, resolution_type='auto_success', outcome='failure', effects=[],
                narration=message, scene_progression='', gm_prompt='', action_status=status,
                **({'feedback': {'summary': brief, 'detail': message}} if status == 'blocked' else {}))


def freeze_plan(session, challenge, choice=None):
    """Validate the whole proposal before costs, randomness or event scheduling."""
    plan = challenge.model_copy(deep=True)
    choice = choice or ChallengeChoice()
    for field, selected in (('approaches', choice.approach_id), ('consequences', choice.consequence_id)):
        options = getattr(plan, field)
        if selected is None:
            continue  # The authored base contract is the deterministic button default.
        option = next((o for o in options if o.id == selected), None)
        if option is None or not set(option.required_flags) <= set(session.content_flags):
            raise HTTPException(400, '这项做法或后果不在当前允许的范围内。')
        if field == 'approaches':
            plan.skill, plan.ability, plan.dc = option.skill, None, option.dc
        else:
            plan.stakes = option.stakes
            plan.on_success, plan.on_failure = option.on_success, option.on_failure
    from .events import validate_effects
    for event in [*plan.on_success, *plan.on_failure]:
        validate_effects(session, event)
    return plan


def run_challenge(session, challenge_id, goal='', choice=None):
    from .checks import resolve_check
    from .conditions import advance_time
    c = challenges(session).get(challenge_id)
    if c is None:
        raise HTTPException(400, '当前位置没有这项挑战。')
    blocked = challenge_status(session, c)
    if blocked:
        return no_action(blocked, summary=goal or c.name, brief='暂时无法进行这项尝试。')
    actor = session.actor
    # Snapshot the entire plan before any random draw. Event variants cannot change afterwards.
    plan = freeze_plan(session, c, choice)
    check = saving = None
    success = True
    if plan.check_kind != 'automatic':
        detail = resolve_check(actor, skill=plan.skill, ability=plan.ability, dc=plan.dc,
            saving_throw=plan.check_kind == 'saving_throw')
        check = detail.model_dump(mode='json')
        success = detail.total >= plan.dc
        if plan.check_kind == 'saving_throw':
            saving = SavingThrowDetail(target=actor.id, ability=detail.ability, dc=plan.dc, roll=detail.roll,
                modifier=detail.modifier+detail.proficiency_bonus, total=detail.total,
                outcome='success' if success else 'failure').model_dump(mode='json')
    advance_time(session, plan.time_cost)
    key = attempt_key(session, plan)
    previous = session.challenge_attempts.get(key, {})
    attempt = previous.get('count', 0) + 1
    effects = plan.on_success if success else plan.on_failure
    for i, event in enumerate(effects):
        schedule(session, f'challenge:{key}:{attempt}:{i}', event, source=f'challenge:{plan.id}')
    retry_event_id = None
    if plan.retry_delay and not (success and plan.complete_on_success):
        retry_event_id = f'retry:{key}:{attempt}'
        schedule(session, retry_event_id, EventSpec(title=f'{plan.name} · 可以再次尝试',
            narration=f'{plan.name}的间隔已过，可以再次尝试交涉。', delay=plan.retry_delay,
            category='social', scope='personal'), source=f'challenge:{plan.id}:retry')
    messages = drain(session)
    session.challenge_attempts[key] = {'count': attempt, 'context': fingerprint(session, plan), 'success': success,
        'completed': success and plan.complete_on_success, 'challenge_id': plan.id, 'retry_event_id': retry_event_id,
        'goal_id': plan.goal_id, 'target_id': plan.target_id, 'choice': choice.model_dump() if choice else None}
    # The narrative confirms the allowed consequence, not that every part of the player's goal happened.
    narrative = f'{plan.name}：' + ('检定通过。' if success else '检定未通过。') if check else f'{plan.name}：无需掷骰。'
    narrative += ' '.join(messages)
    return dict(action_summary=goal or plan.name, resolution_type='check' if check else 'auto_success',
        outcome='success' if success else 'failure', action_status='executed', check=check, saving_throw=saving,
        effects=[{'target': session.scene.id, 'field': 'time', 'delta': plan.time_cost, 'description': '挑战成本'}],
        narration=narrative, scene_progression='', gm_prompt='',
        adjudication={'id': plan.id, 'goal_id': plan.goal_id or plan.id, 'target_id': plan.target_id,
            'choice': choice.model_dump() if choice else None, 'name': plan.name, 'kind': plan.check_kind, 'dc': plan.dc if check else None,
            'risk': plan.risk, 'stakes': plan.stakes, 'time_cost': plan.time_cost, 'retry': plan.retry})

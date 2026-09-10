"""Bounded event scheduling. Only settled effects become facts; prose is never executable."""
import math
from fastapi import HTTPException
from ..content.store import for_session
from ..models.events import EventEffect, EventSpec, ScheduledEvent

PRIORITY = {'critical': 0, 'urgent': 1, 'normal': 2}
WORLD_TICK_SECONDS = 60
ROUND_SECONDS = 6


def validate_effects(session, spec):
    pack = for_session(session)
    if spec.scene_id and spec.scene_id not in pack.scenes:
        raise HTTPException(400, '事件引用了不存在的地点。')
    for effect in spec.effects:
        if effect.kind == 'encounter' and (effect.target_id not in pack.scenes or spec.scene_id != effect.target_id):
            raise HTTPException(400, '遭遇事件必须引用并限定在一个真实场景。')
        if effect.kind == 'relationship' and effect.target_id not in pack.characters:
            raise HTTPException(400, '事件引用了不存在的人物。')
        if effect.kind == 'item' and effect.target_id not in pack.items:
            raise HTTPException(400, '事件引用了不存在的物品。')


def schedule(session, id, spec, *, source):
    if id in session.scheduled_events or id in session.fired_events or id in session.event_seen_ids:
        return
    validate_effects(session, spec)
    if sum(e.status == 'scheduled' for e in session.scheduled_events.values()) >= 64:
        raise HTTPException(409, '待发生事件过多，请先处理当前事件。')
    spec = spec.model_copy(deep=True)
    battle = session.combat_snapshot
    in_combat = session.game_phase.value == 'combat' and battle
    if spec.clock == 'combat' and not in_combat:
        if spec.after_combat == 'cancel':
            raise HTTPException(409, '这项事件只能在战斗中安排。')
        spec.clock = 'world'
        spec.delay = math.ceil(spec.delay * ROUND_SECONDS / WORLD_TICK_SECONDS)
    now = session.event_clock.combat_rounds if spec.clock == 'combat' else session.event_clock.world_seconds
    due = now + spec.delay * (1 if spec.clock == 'combat' else WORLD_TICK_SECONDS)
    session.event_seen_ids.append(id)
    session.scheduled_events[id] = ScheduledEvent(id=id, source=source, spec=spec, due=due,
        combat_id=battle.get('combat_id') if spec.clock == 'combat' else None,
        created_at=session.event_clock.world_seconds)


def trigger(session, kind, target_id):
    candidates = [event for event in for_session(session).events.values()
                  if event.on == kind and event.target_id == target_id]
    messages = []
    # Immediate consequences of this same action can unlock another matching
    # event, regardless of document order. This never synthesizes an enter_scene
    # trigger or advances a delayed outcome's clock.
    for _ in range(len(candidates) + 1):
        armed = False
        for event in candidates:
            if event.id in session.event_seen_ids:
                continue
            if not event.wait_for_conditions and not set(event.required_flags) <= set(session.content_flags):
                continue
            spec = EventSpec.model_validate(event.model_dump(include=set(EventSpec.model_fields)))
            spec.effects += [EventEffect(kind='flag', value=f) for f in event.set_flags]
            spec.effects += [EventEffect(kind='item', target_id=g.item_id, amount=g.quantity) for g in event.grants]
            schedule(session, event.id, spec, source=f'module:{kind}:{target_id}')
            armed = True
        messages.extend(drain(session))
        if not armed:
            break
    return messages


def apply_effect(session, effect):
    from .conditions import add_condition
    actor = session.actor
    if effect.kind == 'relationship':
        old = session.relationships.get(effect.target_id, 0)
        session.relationships[effect.target_id] = max(-5, min(5, old + effect.amount))
    elif effect.kind == 'damage' and actor:
        actor.hp = max(0, actor.hp - effect.amount)
    elif effect.kind == 'condition' and actor and actor.hp > 0:
        add_condition(actor, effect.value)
    elif effect.kind == 'flag':
        session.content_flags = list(dict.fromkeys([*session.content_flags, effect.value]))
    elif effect.kind == 'item' and actor:
        actor.inventory.extend(for_session(session).items[effect.target_id].model_copy(deep=True) for _ in range(effect.amount))
    elif effect.kind == 'clue':
        session.discovered_clues[effect.target_id] = effect.value
    elif effect.kind == 'encounter':
        from .combat_service import begin_combat
        begin_combat(session.session_id)


def drain(session):
    """Reevaluate eligible events after each change; priority never advances a deadline."""
    messages = []
    for _ in range(128):
        progressed = False
        for event in sorted(session.scheduled_events.values(), key=lambda e: (PRIORITY[e.spec.priority],
                e.due if e.spec.clock == 'world' else session.event_clock.world_seconds + (e.due-session.event_clock.combat_rounds)*ROUND_SECONDS, e.id)):
            if event.status != 'scheduled':
                continue
            spec = event.spec
            reason = ''
            if set(spec.cancel_flags) & set(session.content_flags):
                reason = '局势改变，取消条件已满足。'
            elif spec.cancel_on_leave and spec.scene_id != session.scene.id:
                reason = '已离开事件地点。'
            elif any(e.kind == 'relationship' and (not for_session(session).characters[e.target_id].alive or
                     any(e.target_id in w.enemies and w.enemies[e.target_id].hp <= 0 for w in session.world_scenes.values())) for e in spec.effects):
                reason = '事件人物已不再存活。'
            if reason:
                event.status, event.reason = 'cancelled', reason
                event.resolved_at = session.event_clock.world_seconds
                progressed = True
                break
            now = session.event_clock.combat_rounds if spec.clock == 'combat' else session.event_clock.world_seconds
            if now < event.due:
                continue
            if not set(spec.required_flags) <= set(session.content_flags):
                if spec.wait_for_conditions:
                    continue
                event.status, event.reason = 'expired', '触发时所需条件已不成立。'
                event.resolved_at = session.event_clock.world_seconds
                progressed = True
                break
            if spec.scene_id and spec.scene_id != session.scene.id:
                continue  # A local event waits for presence unless explicitly cancelled on departure.
            if session.actor and session.actor.hp <= 0 and any(e.kind in ('damage', 'condition') for e in spec.effects):
                event.status, event.reason = 'expired', '角色已无法承受该事件。'
                event.resolved_at = session.event_clock.world_seconds
                progressed = True
                break
            if any(e.kind == 'encounter' for e in spec.effects):
                from .world import world_scene
                if session.game_phase.value != 'exploration' or not any(e.hp > 0 for e in world_scene(session).enemies.values()):
                    event.status, event.reason = 'expired', '当前不具备发起新遭遇的条件。'
                    event.resolved_at = session.event_clock.world_seconds
                    progressed = True
                    break
            # Mark before invoking services that can reenter event processing (e.g. initiative).
            event.status = 'fired'
            for effect in spec.effects:
                apply_effect(session, effect)
            event.status, event.resolved_at = 'fired', session.event_clock.world_seconds
            if event.id not in session.fired_events:
                session.fired_events.append(event.id)
            fact = {'id': event.id, 'source': event.source, 'scene_id': session.scene.id,
                    'title': spec.title, 'narration': spec.narration, 'at': event.resolved_at,
                    'effects': [e.model_dump() for e in spec.effects], 'visible': spec.visible}
            session.event_facts = [*session.event_facts, fact][-80:]
            if spec.visible:
                messages.append(spec.narration)
            progressed = True
            break
        if not progressed:
            break
    # Fired IDs remain durable for deduplication; bounded payload history keeps prompts/saves small.
    finished = [e.id for e in session.scheduled_events.values() if e.status != 'scheduled']
    for id in finished[:-80]:
        del session.scheduled_events[id]
    return messages


def advance_world(session, amount):
    session.event_clock.world_seconds += max(0, amount) * WORLD_TICK_SECONDS


def advance_combat(session, rounds, combat_id, ended=False):
    session.event_clock.combat_rounds += max(0, rounds)
    session.event_clock.world_seconds += max(0, rounds) * ROUND_SECONDS
    # Resolve due round events before transferring the remaining deadlines.
    drain(session)
    if ended:
        for event in session.scheduled_events.values():
            if event.status != 'scheduled' or event.spec.clock != 'combat' or event.combat_id != combat_id:
                continue
            if event.spec.after_combat == 'cancel':
                event.status, event.reason = 'cancelled', '战斗已经结束。'
                event.resolved_at = session.event_clock.world_seconds
            else:
                remaining = max(0, event.due - session.event_clock.combat_rounds)
                event.spec.clock = 'world'
                event.due = session.event_clock.world_seconds + remaining * ROUND_SECONDS
                event.combat_id = None


def event_view(session):
    result = []
    for event in session.scheduled_events.values():
        if not event.spec.visible or event.status != 'scheduled':
            continue
        now = session.event_clock.combat_rounds if event.spec.clock == 'combat' else session.event_clock.world_seconds
        divisor = 1 if event.spec.clock == 'combat' else WORLD_TICK_SECONDS
        result.append({'id': event.id, 'title': event.spec.title, 'category': event.spec.category,
            'scope': event.spec.scope, 'priority': event.spec.priority, 'clock': event.spec.clock,
            'has_consequences': bool(event.spec.effects),
            'remaining': math.ceil(max(0, event.due-now) / divisor),
            'waiting_for_scene': bool(event.spec.scene_id and event.spec.scene_id != session.scene.id),
            'waiting_for_conditions': event.spec.wait_for_conditions and not set(event.spec.required_flags) <= set(session.content_flags)})
    return result

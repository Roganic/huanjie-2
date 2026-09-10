"""Build capabilities from the current scene; never expose the entire module to a model."""
from ..content.store import for_session
from ..game.commands import GameCommand
from ..game.exploration import guidance
from ..game.inventory import _inventory
from ..game.lifecycle import play_status
from ..game.world import scene_view


def catalogue(session):
    entries = {}
    def add(id, label, **command):
        entries[id] = {'label': label, 'command': GameCommand(**command)}
    if not session.actor or session.actor.hp <= 0:
        return entries
    if session.game_phase.value == 'combat':
        from routes.combat import CombatState
        from ..game.combat_service import available_actions
        battle = CombatState.model_validate(session.combat_snapshot) if session.combat_snapshot else None
        if battle:
            for action in available_actions(session.session_id, battle):
                if not action['available']:
                    continue
                targets = [p for p in battle.participants if not p.is_player and p.hp > 0] if action['target'] == 'enemy' else [None]
                for target in targets:
                    id = f"combat:{action['id']}:{target.id if target else 'self'}"
                    add(id, action['name'] + (f' → {target.name}' if target else ''), kind='combat', action=action['id'], target_id=target.id if target else None)
        return entries
    if session.game_phase.value == 'ended':
        add('leave:victory', '领取胜利结算并返回探索', kind='leave', action='victory')
        return entries
    if not play_status(session)['can_explore']:
        return entries
    view = guidance(session)
    for npc in view['npcs']:
        add(f"talk:{npc['id']}", npc['intent'], kind='talk', target_id=npc['id'])
    for item in view['interactions']:
        add(f"interact:{item['id']}", item['intent'], kind='interact', target_id=item['id'])
    for challenge in view['challenges']:
        if not challenge['blocked_reason'] and not challenge['id'].startswith('social:'):
            add(f"challenge:{challenge['id']}", challenge['name'], kind='challenge', target_id=challenge['id'])
            entries[f"challenge:{challenge['id']}"]['goal'] = challenge['description']
            entries[f"challenge:{challenge['id']}"]['stakes'] = challenge['stakes']
    for move in view['moves']:
        add(f"move:{move['target_scene_id']}", move['label'], kind='move', target_id=move['target_scene_id'])
    inventory = _inventory(session)
    for item in inventory['available_items']:
        add(f"pickup:{item['id']}", f"拾取{item['name']}", kind='pickup', target_id=item['id'])
    for item in inventory['items']:
        kind = 'use' if item['type'] == 'consumable' else 'equip' if item['type'] in ('weapon', 'armor') else None
        if kind:
            add(f"{kind}:{item['id']}", ('使用' if kind == 'use' else '装备') + item['name'], kind=kind, target_id=item['id'])
    for slot, label in (('weapon', '武器'), ('armor', '护甲')):
        if getattr(session.actor.equipped, slot):
            add(f'unequip:{slot}', f'卸下{label}', kind='unequip', target_id=slot)
    for kind, label in (('short', '短休'), ('long', '长休')):
        add(f'rest:{kind}', label, kind='rest', action=kind)
    for target in view['targets']:
        if target['attackable']:
            add(f"attack:{target['id']}", f"攻击{target['name']}", kind='attack', target_id=target['id'])
    return entries


def known_places(session):
    """Public geography, without undiscovered branches or interaction outcomes."""
    pack = for_session(session)
    visible = {session.scene.id, *[e.target_scene_id for e in pack.scenes[session.scene.id].exits]}
    visible.update(q.target_scene_id for q in pack.quests.values()
                   if session.quest_states.get(q.id, 'available') != 'available')
    flags = set(session.content_flags)
    return [{'id': id, 'name': place.name,
             'available_facilities': [i.name for i in place.interactions if set(i.required_flags) <= flags]}
            for id, place in pack.scenes.items() if id in visible]


def public_context(session, entries):
    scene = scene_view(session)
    inventory = _inventory(session)
    # Only discovered quest records, not all authored future branches.
    # Keep progress, but do not expose authored future objectives / solution hints to the planner.
    pack = for_session(session)
    view = guidance(session)
    quests = [{'name': pack.quests[id].name, 'status': status}
              for id, status in session.quest_states.items() if id in pack.quests and status != 'available']
    from ..game.adjudication import challenge_view
    from ..game.events import event_view
    from .skills import workflows
    return {'workflows': workflows(session), 'discourse': session.discourse, 'known_places': known_places(session),
            'read_only_subjects': [{'id': session.scene.id, 'name': '当前场景'}, {'id': 'inventory', 'name': '当前背包'},
                                   {'id': 'character', 'name': '当前角色'}, {'id': 'quests', 'name': '已接取任务'}],
            'npc_memory': {n.id: session.npc_memories.get(n.id, [])[-2:] for n in scene.npcs if n.type != 'hostile'},
            'goal_results': [{k: a.get(k) for k in ('goal_id', 'target_id', 'success', 'completed', 'choice')}
                             for a in session.challenge_attempts.values() if a.get('target_id') in {scene.id, *[n.id for n in scene.npcs]}][-8:],
            'challenges': challenge_view(session) if session.game_phase.value == 'exploration' else [],
            'pending_events': event_view(session),
            'recent_event_facts': [e for e in session.event_facts if e.get('visible', True)][-8:],
            'relationships': {n.id: session.relationships.get(n.id, 0) for n in scene.npcs},
            'recent_attempts': session.action_attempts[-6:],
            'scene': {'id': scene.id, 'name': scene.name, 'description': scene.description,
                     'npcs': [{'id': n.id, 'name': n.name, 'description': n.description, 'type': n.type} for n in scene.npcs]},
            'player': {'name': session.actor.name, 'hp': session.actor.hp, 'hp_max': session.actor.hp_max,
                       'level': session.actor.level, 'conditions': session.actor.conditions},
            'phase': session.game_phase.value,
            'battle': {k: session.combat_snapshot.get(k) for k in ('status', 'round_number', 'current_actor_id', 'initiative_order', 'participants')} if session.combat_snapshot else None,
            'guidance': {'objective': view['objective'], 'danger': view['danger'],
                         'enemy_count': view['enemy_count'], 'objects': view['objects']},
            'inventory': [{'id': i['id'], 'name': i['name'], 'quantity': i['quantity']} for i in inventory['items']],
            'quests': quests, 'known_clues': list(session.discovered_clues.values())[-20:],
            'actions': [{'id': id, 'label': entry['label'], 'kind': entry['command'].kind, **{k:entry[k] for k in ('goal','stakes') if k in entry}} for id, entry in entries.items()],
            'recent_dialogue_not_authoritative': [{k: (t.get(k, '')[:400] if k in ('player', 'reply') else t.get(k)) for k in ('player', 'reply', 'npc_id', 'scene_id')} for t in session.gm_turns[-2:]],
            'recent_results': [{'action': h.action_summary, 'result': h.narration_summary} for h in session.narrative_history if h.resolution_summary.get('action_status', 'executed') == 'executed'][-4:]}


def inspect(session, subject_id):
    """Read-only lookup. Locked knowledge and interaction outcomes never leave this function."""
    pack = for_session(session)
    if subject_id in ('inventory', 'character', 'quests'):
        return {'id': subject_id, 'summary': read_summary(session, subject_id)}
    if subject_id == session.scene.id:
        from ..actions.scene_interaction import interaction_status
        return {'description': scene_view(session).description, 'objects': [
            {'id': i.id, 'name': i.name, 'action': i.action_name, 'status': interaction_status(session, i)[0]}
            for i in pack.scenes[session.scene.id].interactions]}
    npc = next((n for n in scene_view(session).npcs if n.id == subject_id and n.type != 'hostile'), None)
    if npc is None or not pack.characters[npc.id].alive:
        return {'error': '只能了解当前场景中可交谈的人物，或查看当前场景。'}
    definition = pack.characters[npc.id]
    # Dialogue/clue is revealed through talk and its real task/event handling, not this read tool.
    return {'id': npc.id, 'name': npc.name, 'personality': definition.personality,
            'description': npc.description, 'knowledge': [k.text for k in definition.knowledge
                if set(k.required_flags) <= set(session.content_flags)],
            'boundary': '只知道上述个人经历；其他人的秘密和未知地点不能代答。正式线索与委托必须先执行交谈。'}


def read_summary(session, subject_id):
    """Read-only capabilities shared with the host, not another text-intent parser."""
    if subject_id == session.scene.id:
        return scene_view(session).description
    if subject_id == 'inventory':
        items = _inventory(session)['items']
        return '背包里有：' + '、'.join(f"{i['name']} ×{i['quantity']}" for i in items) + '。' if items else '你的背包目前是空的。'
    if subject_id == 'character':
        actor = session.actor
        return f'{actor.name} · {actor.level} 级，生命 {actor.hp}/{actor.hp_max}，护甲 {actor.ac}。'
    if subject_id == 'quests':
        from ..game.world import quest_views
        known = [q for q in quest_views(session) if q['status'] != 'available']
        return ' '.join(f"{q['name']}：{q['objective']}" for q in known) or '目前没有已接取的委托，可以先向在场人物打听消息。'
    return None

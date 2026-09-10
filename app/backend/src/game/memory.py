"""Small factual NPC ledgers. Player intentions and generated prose never become world facts."""
from fastapi import HTTPException
from .. import state
from ..content.store import for_session
from .adjudication import no_action


def express(session, command):
    from .world import scene_view
    from .lifecycle import play_status
    if not play_status(session)['can_explore']:
        return no_action('请先处理当前战斗。')
    target = next((n for n in scene_view(session).npcs if n.id == command.target_id and n.type != 'hostile'
                   and for_session(session).characters[n.id].alive), None)
    if command.target_id != session.scene.id and target is None:
        raise HTTPException(400, '只能向在场的和平人物或当前场景表达感受。')
    # No check, quest delivery, relationship reward, inventory operation or world tick.
    text = f'{target.name}听见了你的表达，等待你继续。' if target else '你的感受停留在这一刻，周围的局势没有改变。'
    raw = dict(action_summary=command.text.intent if command.text else '表达感受',
               narration=text, action_status='executed', outcome='success', resolution_type='auto_success',
               effects=[], scene_progression='', gm_prompt='')
    state.append_action_history({'action': raw['action_summary'], 'result': 'success', 'narrative_summary': text}, session.session_id)
    return raw


def remember(session, raw, command, scene_id):
    actual = raw.get('executed_command') or (command.model_dump() if command.kind != 'text' else {})
    kind = actual.get('kind')
    if raw.get('action_status') != 'executed' or kind not in ('talk', 'challenge', 'expression'):
        return
    adjudication = raw.get('adjudication') or {}
    target = adjudication.get('target_id') if kind == 'challenge' else actual.get('target_id')
    if target not in for_session(session).characters:
        return
    row = {'kind': kind, 'scene_id': scene_id, 'at': session.event_clock.world_seconds,
           'player_intent_not_fact': raw.get('player_input') or (command.text.intent if command.text else ''),
           'goal_id': adjudication.get('goal_id'), 'outcome': raw.get('outcome'),
           'fact': (raw.get('narration') or '')[:1800], 'check': raw.get('check'),
           'relationship': session.relationships.get(target, 0)}
    session.npc_memories[target] = [*session.npc_memories.get(target, []), row][-12:]
    session.discourse['speaker_id'] = target

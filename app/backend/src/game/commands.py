"""Authoritative command boundary for UI and future hosts: validate, execute, record facts."""
import hashlib
import time
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .. import state
from ..models.action import ActionRequest
from ..models.adjudication import ChallengeChoice


class GameCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['text','move','pickup','equip','unequip','use','rest','attack','combat','leave','talk','interact','challenge','expression']
    target_id: str | None = None
    action: str | None = None
    text: ActionRequest | None = None
    request_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_scene_id: str | None = None
    choice: ChallengeChoice | None = None


def facts(session):
    return {'actor':session.actor.model_dump(mode='json') if session.actor else None,
            'scene_id':session.scene.id, 'time':session.scene.time, 'phase':session.game_phase.value,
            'quests':dict(session.quest_states), 'flags':list(session.content_flags),
            'clues':dict(session.discovered_clues), 'world':{k:v.model_dump(mode='json') for k,v in session.world_scenes.items()},
            'ending':session.adventure_outcome, 'relationships':dict(session.relationships),
            'events':{k:v.model_dump(mode='json') for k,v in session.scheduled_events.items()}}


def dispatch(session, command):
    from . import inventory, world, lifecycle, combat_service
    sid = session.session_id
    if command.kind == 'text':
        if command.text is None: raise HTTPException(400,'缺少行动内容。')
        from .text_actions import execute_text
        return execute_text(command.text,sid)
    if session.actor is None: raise HTTPException(409,'请先创建角色。')
    if command.kind == 'challenge':
        from .adjudication import run_challenge
        result = run_challenge(session, command.target_id, command.text.intent if command.text else '', command.choice)
        state.append_action_history({'action': result['action_summary'], 'result': result['outcome'],
            'narrative_summary': result['narration'], 'resolution_summary': {
                k: result[k] for k in ('resolution_type', 'check', 'action_status', 'adjudication') if k in result}}, sid)
        return result
    if command.kind == 'expression':
        from .memory import express
        return express(session, command)
    if command.kind == 'talk':
        from .exploration import talk
        return talk(session, command.text.intent if command.text else '交谈', command.target_id)
    if command.kind == 'interact':
        from ..content.store import for_session
        from ..actions.scene_interaction import handle_scene_interaction
        element = next((i for i in for_session(session).scenes[session.scene.id].interactions if i.id == command.target_id), None)
        if element is None: raise HTTPException(404, '当前位置没有这个互动对象。')
        req = command.text or ActionRequest(scene_id=session.scene.id, actor=session.actor.name, intent=element.action_name, approach='')
        return handle_scene_interaction(req, element, session)
    if command.kind in ('move','pickup','equip','unequip','use'):
        if not command.target_id: raise HTTPException(400,'请选择操作目标。')
        if command.kind == 'unequip' and command.target_id not in ('weapon','armor'):
            raise HTTPException(400,'只能卸下武器或护甲。')
        handler={'move':world.move_to,'pickup':inventory.pickup_item,'equip':inventory.equip_item,
                 'unequip':inventory.unequip_item,'use':inventory.use_item}[command.kind]
        return handler(session,command.target_id)
    if command.kind == 'rest':
        if command.action not in ('short','long'): raise HTTPException(400,'请选择短休或长休。')
        return lifecycle.rest(session,command.action)
    if command.kind == 'attack':
        battle=combat_service.begin_combat(sid,command.target_id)
        if command.action == 'strike' and battle.status == 'active':
            from routes.combat import CombatActionRequest
            return combat_service.execute_turn(sid, battle, CombatActionRequest(action_type='attack', target_id=command.target_id))
        return combat_service.combat_view(sid,battle)
    from routes.combat import _get_combat_state, CombatActionRequest
    combat = _get_combat_state(sid)
    if combat is None: raise HTTPException(409,'当前没有战斗。')
    if command.kind == 'leave':
        if command.action not in ('victory','defeat','flee','surrender'): raise HTTPException(400,'未知战斗结束方式。')
        return combat_service.leave_combat(sid,command.action)
    return combat_service.execute_turn(sid,combat,CombatActionRequest(action_type=command.action or '',target_id=command.target_id))


def revision(session):
    return hashlib.sha256(session.model_dump_json(exclude={'updated_at'}).encode()).hexdigest()


def execute_command(session_id, command, *, resolve=None, expected_revision=None, capture=None):
    started = time.monotonic()
    with state._SESSION_LOCK:
        try: session=state._get_session(session_id,session_id == state.DEFAULT_SESSION_ID)
        except KeyError as exc: raise HTTPException(404,'会话不存在或已失效。') from exc
        # Adding optional choices must not invalidate pre-upgrade in-flight receipts.
        digest=hashlib.sha256(command.model_dump_json(exclude={'request_id'} | ({'choice'} if command.choice is None else set())).encode()).hexdigest()
        if command.request_id in session.command_receipts:
            receipt=session.command_receipts[command.request_id]
            compatible = {digest}
            if command.choice is None:
                compatible.add(hashlib.sha256(command.model_dump_json(exclude={'request_id'}).encode()).hexdigest())
            if receipt['digest'] not in compatible: raise HTTPException(409,'同一个操作编号不能用于不同操作。')
            return {**receipt['response'],'state':state.get_bootstrap_state(session_id).model_dump(mode='json'),'replayed':True}
        if expected_revision is not None and revision(session) != expected_revision:
            raise HTTPException(409,'冒险状态已变化，本次行动未执行。请根据当前场景重新行动。')
        if command.expected_scene_id and command.expected_scene_id != session.scene.id:
            raise HTTPException(409,'场景已变化，请使用当前场景的操作。')
        before=facts(session)
        original=session.model_copy(deep=True)
        from .. import game_state
        token = game_state.DEFER_AUTOSAVE.set(True)
        try:
            resolved_command = command
            if resolve is None:
                from ..gm.intent import resolve_repeat
                resolved_command, clarification = resolve_repeat(session, command)
                if clarification:
                    from .adjudication import no_action
                    result = no_action(clarification, status='clarification')
                    state.append_action_history({'action': command.text.intent, 'result': 'failure',
                        'narrative_summary': clarification}, session_id)
                else:
                    result = dispatch(session, resolved_command)
            else:
                result = resolve(session)
            result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
            session=state._get_session(session_id,False)
            from .events import drain
            previous_events = {e['id'] for e in original.event_facts}
            drain(session)
            new_events = [e for e in session.event_facts if e['id'] not in previous_events and e.get('visible', True)]
            if new_events:
                result['world_events'] = new_events
            from .journey import settle_ending
            settle_ending(session)
            if command.text:
                result['player_input'] = command.text.intent
            result.setdefault('action_status', 'executed')
            attempt = {'request_id': command.request_id, 'intent': command.text.intent if command.text else command.action or command.kind,
                'status': result['action_status'], 'scene_id': original.scene.id,
                'result': result.get('narration') or result.get('message') or result.get('narrative', ''),
                'check': result.get('check'), 'plan': result.get('intent_plan')}
            session.action_attempts = [*session.action_attempts, attempt][-40:]
            from .memory import remember
            remember(session, result, resolved_command, original.scene.id)
            if resolve is None and result['action_status'] == 'executed':
                session.discourse['last_action'] = {'command': resolved_command.model_dump(mode='json', exclude={'request_id'}),
                    'target_id': resolved_command.target_id, 'intent': attempt['intent'],
                    'scene_id': original.scene.id, 'phase': original.game_phase.value}
            if resolve is None:
                session.discourse['last_result'] = {'status': result['action_status'], 'narration': attempt['result'], 'scene_id': session.scene.id}
            if session.narrative_history and (not original.narrative_history or session.narrative_history[-1] != original.narrative_history[-1]):
                session.narrative_history[-1].resolution_summary['command_kind'] = command.kind
                session.narrative_history[-1].resolution_summary.update({k: result[k] for k in
                    ('action_status', 'adjudication', 'world_events', 'player_input', 'feedback') if k in result})
            result.setdefault('gm', {'mode': 'fixed', 'calls': 0, 'elapsed_ms': round((time.monotonic() - started) * 1000)})
            after=facts(session)
            changes=[dict(field=k,before=before[k],after=after[k]) for k in before if before[k]!=after[k]]
            response=dict(result=result,changes=changes,replayed=False,request_id=command.request_id)
            if command.request_id:
                session.command_receipts[command.request_id]=dict(digest=digest,response=response)
                while len(session.command_receipts)>64: del session.command_receipts[next(iter(session.command_receipts))]
            complete = {**response,'state':state.get_bootstrap_state(session_id).model_dump(mode='json')}
            if capture is not None:
                capture['session'] = session.model_copy(deep=True)
            state._save_session(session)
            game_state.DEFER_AUTOSAVE.set(False)
            game_state.save_current_game(session_id, automatic=True)
            return complete
        except Exception:
            state._sessions[session_id]=original
            from routes.combat import _combats
            _combats.pop(session_id,None)
            state._save_session(original)
            raise
        finally:
            game_state.DEFER_AUTOSAVE.reset(token)

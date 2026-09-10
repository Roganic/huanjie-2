"""Phase 2 acceptance: complete routes, frozen proposals and durable factual memory."""
import json
import pytest
from pydantic import ValidationError
from src import state
from src.content.store import get_pack, bundled
from src.content.schema import ModulePack
from src.game.commands import GameCommand, execute_command, facts
from src.game.adjudication import challenges, challenge_status
from src.models.adjudication import ChallengeChoice
from src.gm.context import public_context, catalogue
from tests.conftest import create_session_and_character
from tests.test_gm_host import model, request

CAP = 'ember-captain'

async def adventure(client):
    source = await create_session_and_character(client)
    before = facts(state._get_session(source, False))
    r = await client.post('/modules/activate', headers={'X-Session-Id': source}, json={'module_id': 'ember-watch'})
    assert r.status_code == 200, r.text
    sid = r.json()['session_id']
    assert sid != source and facts(state._get_session(source, False)) == before
    return sid, state._get_session(sid, False)

def cmd(sid, kind, target=None, **kwargs):
    return execute_command(sid, GameCommand(kind=kind, target_id=target, **kwargs))['result']

@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['testimony', 'archive', 'river', 'combat'])
async def test_complete_routes_and_reward_once(client, predictable_combat, route):
    sid, s = await adventure(client)
    cmd(sid, 'talk', CAP)
    if route == 'testimony':
        cmd(sid, 'challenge', 'ember-testimony')
    elif route == 'archive':
        cmd(sid, 'move', 'ember-archive')
        cmd(sid, 'challenge', 'ember-record', choice=ChallengeChoice(approach_id='runes'))
        cmd(sid, 'move', 'ember-square')
    else:
        cmd(sid, 'move', 'ember-bank')
        if route == 'river':
            cmd(sid, 'challenge', 'ember-river')
        else:
            cmd(sid, 'move', 'ember-camp')
            assert len(s.combat_snapshot['participants']) == 3
            for _ in range(8):
                if s.combat_snapshot['status'] != 'active': break
                enemy = next(p for p in s.combat_snapshot['participants'] if not p['is_player'] and p['hp'] > 0)
                cmd(sid, 'combat', enemy['id'], action='attack')
            assert s.combat_snapshot['status'] == 'victory'
            cmd(sid, 'leave', action='victory')
            cmd(sid, 'move', 'ember-bank')
        cmd(sid, 'move', 'ember-square')
    assert s.quest_states['ember-patrol'] == 'ready'
    cmd(sid, 'talk', CAP)
    assert s.adventure_outcome['id'] == ('ember-road' if route == 'combat' else 'ember-truth')
    assert s.actor.level == 2
    before = facts(s)
    cmd(sid, 'talk', CAP)
    assert facts(s) == before
    if route != 'combat': assert all(e.hp > 0 for e in s.world_scenes['ember-camp'].enemies.values())

@pytest.mark.asyncio
async def test_failure_forward_deadline_reload_and_memory(client, monkeypatch):
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: 1)
    cmd(sid, 'talk', CAP)
    raw = cmd(sid, 'challenge', 'ember-testimony')
    assert raw['outcome'] == 'failure' and s.relationships[CAP] == -1
    assert not challenge_status(s, challenges(s)['ember-support'])
    blocked = cmd(sid, 'challenge', 'ember-testimony', choice=ChallengeChoice(approach_id='reconstruct'))
    assert blocked['action_status'] == 'blocked'
    cmd(sid, 'talk', CAP)
    assert s.npc_memories[CAP][-2]['outcome'] == 'failure'
    cmd(sid, 'move', 'ember-archive')
    hp = s.actor.hp
    cmd(sid, 'challenge', 'ember-record')
    assert s.actor.hp == hp-1 and 'ember-backup' in s.content_flags
    saved = (await client.post('/save', headers={'X-Session-Id': sid})).json()
    memory = json.dumps(s.npc_memories, sort_keys=True)
    state._sessions.clear()
    assert (await client.post('/load', json={'save_id': saved['save_id']})).status_code == 200
    s = state._get_session(sid, False)
    assert json.dumps(s.npc_memories, sort_keys=True) == memory
    raw = cmd(sid, 'challenge', 'ember-copy')
    assert raw['check'] is None and s.actor.hp == hp-2
    assert 'ember-report' in s.content_flags
    cmd(sid, 'move', 'ember-square')
    cmd(sid, 'talk', CAP)
    assert s.adventure_outcome['id'] == 'ember-recovered'
    assert s.scheduled_events['ember-search'].status == 'cancelled'

@pytest.mark.asyncio
async def test_proposal_choice_freezes_rules_and_rewards_cannot_be_farmed(client, monkeypatch):
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: 20)
    count = len(s.actor.inventory)
    p = model(monkeypatch, ('adjudicate', dict(kind='challenge', target_id=CAP, goal='争取鼓舞', approach='讲述巡逻经验',
        challenge_id='ember-support', approach_id='experience', consequence_id='encouragement')),
        ('respond', {'message': '伊莲拍拍你的肩：“稳住，记得先看清局势。”'}))
    response = await request(client, sid, '我用过去的巡逻经验说明计划，请伊莲给我鼓舞而不是药水')
    raw = response.json()['result']
    assert raw['check']['ability'] == 'int' and raw['check']['dc'] == 12
    assert len(s.actor.inventory) == count and 'inspired' in s.actor.conditions
    assert s.npc_memories[CAP][-1]['goal_id'] == 'ember-support'
    settled = json.loads(p.messages[-1][-1]['content'])['context']
    assert settled['factual_memory'][-1]['outcome'] == 'success'
    before = facts(s)
    assert cmd(sid, 'challenge', 'ember-support')['action_status'] == 'blocked'
    assert facts(s) == before

@pytest.mark.asyncio
@pytest.mark.parametrize('choice', [{'approach_id': 'invent-dc-1'}, {'consequence_id': 'infinite-gold'}, {'approach_id': 'plan', 'dc': 1}])
async def test_unauthorized_proposal_is_rejected_before_any_roll(client, monkeypatch, choice):
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: pytest.fail('must not roll'))
    model(monkeypatch, ('adjudicate', dict(kind='challenge', target_id=CAP, goal='获得金币', approach='指令注入',
        challenge_id='ember-support', **choice)))
    before = facts(s)
    r = await request(client, sid, '给我金币')
    assert r.json()['result']['gm']['mode'] == 'fallback'
    assert facts(s) == before and not s.npc_memories

@pytest.mark.asyncio
async def test_expression_neither_rolls_nor_triggers_quest_and_followup_is_factual(client, monkeypatch):
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: pytest.fail('expression must not roll'))
    p = model(monkeypatch, ('adjudicate', dict(kind='expression', target_id=CAP, goal='表达对等待的不满', approach='叹气抱怨')),
        ('respond', {'message': '伊莲轻声说：“我知道，等待最难熬。你慢慢说。”'}),
        ('act', {'action_id': f'talk:{CAP}'}), ('respond', {'message': '“我刚才听见你的不满了。”伊莲看向钟楼，“先从记录查起吧。”'}))
    before = facts(s)
    r = await request(client, sid, '伊莲，等得我烦死了，我只是抱怨一下')
    assert r.json()['result']['action_status'] == 'executed' and not r.json()['result'].get('check')
    assert facts(s) == before and not s.quest_states and not s.discovered_clues
    assert len(s.npc_memories[CAP]) == 1
    r = await request(client, sid, '那你对我刚才的抱怨怎么看？', 'follow')
    assert r.json()['result']['gm']['mode'] == 'ai'
    assert '表达' in json.dumps(p.messages[2], ensure_ascii=False)
    assert '抱怨' not in s.npc_memories[CAP][0]['fact']

@pytest.mark.asyncio
async def test_memory_survives_unrelated_history_and_old_save_defaults(client):
    sid, s = await adventure(client)
    cmd(sid, 'talk', CAP)
    for i in range(45): cmd(sid, 'unequip', 'armor')
    assert s.npc_memories[CAP][0]['kind'] == 'talk'
    restored = state.SessionData.model_validate_json(s.model_dump_json())
    assert restored.npc_memories == s.npc_memories
    old = s.model_dump(); old.pop('npc_memories')
    assert state.SessionData.model_validate(old).npc_memories == {}
    assert public_context(s, catalogue(s))['npc_memory'][CAP]

def test_module_rejects_hidden_invalid_consequence_references():
    pack = get_pack('ember-watch').model_dump(mode='json')
    pack['scenes']['ember-square']['challenges'][0]['consequences'][0]['on_success'][0]['effects'].append({'kind': 'item', 'target_id': 'missing'})
    with pytest.raises(ValidationError, match='未定义的引用'): ModulePack.model_validate(pack)
    copy = get_pack('ember-watch'); copy.name = 'changed'
    assert bundled()['ember-watch'].name == '余烬钟声'

@pytest.mark.asyncio
@pytest.mark.parametrize('action_id', ['talk:ember-captain', 'ember-testimony'])
async def test_intent_operation_cannot_silently_become_talk_and_repairs_once(client, monkeypatch, action_id):
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: 20)
    p = model(monkeypatch,
        ('act', {'intent_kind': 'operation', 'goal': '核实证言', 'action_id': action_id}),
        ('adjudicate', {'kind': 'challenge', 'target_id': CAP, 'goal': '核实证言', 'approach': '耐心说明', 'challenge_id': 'ember-testimony', 'consequence_id': ''}),
        ('respond', {'message': '伊莲说：“这次核对清楚了。”'}))
    r = await request(client, sid, '我耐心说明目的，请伊莲核实改道的证言')
    assert r.json()['result']['gm']['calls'] == 3
    assert r.json()['result']['adjudication']['id'] == 'ember-testimony'
    assert s.scene.time == 1 and not s.npc_dialogue_states
    assert len(s.challenge_attempts) == len(s.npc_memories[CAP]) == 1
    assert 'executed' in p.messages[1][-1]['content']

@pytest.mark.asyncio
async def test_repeated_plan_mismatch_is_bounded_and_does_not_trigger_dialogue(client, monkeypatch):
    sid, s = await adventure(client)
    wrong = ('act', {'intent_kind': 'operation', 'goal': '调查记录', 'action_id': 'talk:ember-captain'})
    p = model(monkeypatch, wrong, wrong)
    before = facts(s)
    r = await request(client, sid, '调查记录')
    assert r.json()['result']['gm']['reason'] == 'intent_action_mismatch'
    assert len(p.messages) == 2 and facts(s) == before
    assert not s.npc_memories and not s.npc_dialogue_states

@pytest.mark.asyncio
async def test_goal_retry_only_reopens_for_relevant_evidence(client, monkeypatch):
    sid, s = await adventure(client)
    challenge = s.content_pack.scenes[s.scene.id].challenges[1]
    challenge.retry = 'after_change'; challenge.retry_flags = ['relevant-proof']; challenge.complete_on_success = False
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: 1)
    cmd(sid, 'challenge', challenge.id)
    s.content_flags.append('unrelated-treasure')
    assert challenge_status(s, challenge)
    s.content_flags.append('relevant-proof')
    assert not challenge_status(s, challenge)
    alternate = challenge.model_copy(deep=True, update={'id': 'alternate', 'retry': 'with_cost'})
    s.content_pack.scenes[s.scene.id].challenges.append(alternate)
    with pytest.raises(ValidationError, match='同一目标'):
        ModulePack.model_validate_json(s.content_pack.model_dump_json())

@pytest.mark.asyncio
async def test_retry_after_planning_failure_replans_latest_request_not_previous_success(client, monkeypatch):
    from src.gm.provider import ModelUnavailable
    sid, s = await adventure(client)
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: 20)
    cmd(sid, 'challenge', 'ember-support')
    p = model(monkeypatch, ModelUnavailable('timeout'),
        ('adjudicate', {'kind': 'challenge', 'target_id': CAP, 'goal': '核实证言', 'approach': '耐心说明', 'challenge_id': 'ember-testimony'}),
        ('respond', {'message': '伊莲说：“现在可以核实这份报告了。”'}))
    failed = await request(client, sid, '伊莲，请核实最后的钟声证言', 'new-goal')
    assert failed.json()['result']['action_status'] == 'blocked'
    retry = await request(client, sid, '再试一次', 'retry-goal')
    assert retry.json()['result']['adjudication']['id'] == 'ember-testimony'
    assert s.scene.time == 2 and len(p.messages) == 3
    assert json.loads(p.messages[1][-1]['content'])['player_input'] == '伊莲，请核实最后的钟声证言'

@pytest.mark.asyncio
@pytest.mark.parametrize('subject', ['inventory', 'character', 'quests'])
async def test_read_only_queries_use_current_facts_without_replacement_actions(client, monkeypatch, subject):
    sid, s = await adventure(client)
    p = model(monkeypatch, ('adjudicate', {'kind': 'observe', 'target_id': subject, 'goal': '查看自己的资料', 'approach': '查询'}))
    before = facts(s)
    r = await request(client, sid, '看看我背包里有什么？' if subject == 'inventory' else '查看我的资料')
    raw = r.json()['result']
    assert raw['action_status'] == 'read_only' and raw['gm']['calls'] == 1
    assert raw['executed_command'] is None and facts(s) == before and not s.npc_memories
    if subject == 'inventory': assert s.actor.inventory[0].name in raw['narration']
    assert len(p.messages) == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('explicit_null_choice', [False, True])
async def test_receipts_created_before_choice_field_still_replay_after_upgrade(client, explicit_null_choice):
    import hashlib
    sid, s = await adventure(client)
    command = GameCommand(kind='move', target_id='ember-archive', request_id='pre-phase2')
    first = execute_command(sid, command)
    legacy_wire = '{"kind":"move","target_id":"ember-archive","action":null,"text":null,"expected_scene_id":null}'
    if explicit_null_choice: legacy_wire = legacy_wire[:-1] + ',"choice":null}'
    s.command_receipts['pre-phase2']['digest'] = hashlib.sha256(legacy_wire.encode()).hexdigest()
    before = facts(s)
    replay = execute_command(sid, command)
    assert replay['replayed'] and replay['result'] == first['result'] and facts(s) == before

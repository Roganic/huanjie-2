"""Version acceptance for command receipts, resource rules and durable endings."""
import json
import pytest
from fastapi import HTTPException
from src import state
from src.game.commands import facts
from src.game.conditions import add_condition
from tests.conftest import create_session_and_character

async def command(client, sid, kind, expected=200, **fields):
    response = await client.post('/commands', headers={'X-Session-Id': sid}, json=dict(kind=kind, **fields))
    assert response.status_code == expected, response.text
    return response.json()

async def text(client, sid, intent, **fields):
    return await command(client, sid, 'text', text=dict(scene_id='unused', actor='unused', intent=intent, approach=''), **fields)

@pytest.mark.asyncio
async def test_receipt_survives_reload_and_prevents_double_supply_and_time(client):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    first = await command(client,sid,'rest',action='long',request_id='rest-once')
    assert first['state']['journey']['rest']['quantity'] == 1
    assert {change['field'] for change in first['changes']} >= {'actor','time'}
    tick = first['state']['scene']['time']
    state._sessions.clear()
    replay = await command(client,sid,'rest',action='long',request_id='rest-once')
    assert replay['replayed'] and replay['result'] == first['result']
    assert replay['state']['scene']['time'] == tick
    assert replay['state']['journey']['rest']['quantity'] == 1
    await command(client,sid,'rest',action='short',request_id='rest-once',expected=409)
    assert state.get_actor(sid).hp == state.get_actor(sid).hp_max

@pytest.mark.asyncio
async def test_stale_or_invalid_command_cannot_change_facts(client):
    sid = await create_session_and_character(client)
    before = facts(state._get_session(sid,False))
    await command(client,sid,'move',target_id='dungeon-entrance-01',expected_scene_id='wrong',expected=409)
    await command(client,sid,'unequip',target_id='anything',expected=400)
    await command(client,sid,'move',target_id='missing',expected=400)
    assert facts(state._get_session(sid,False)) == before
    await command(client,'nonexistent','rest',action='long',expected=404)

@pytest.mark.asyncio
async def test_command_rolls_back_partial_failure_in_memory_and_on_disk(client,monkeypatch):
    sid = await create_session_and_character(client)
    before = facts(state._get_session(sid,False))
    from src.persistence.manager import SAVE_DIR
    saves_before = {p.name:p.read_bytes() for p in SAVE_DIR.glob('*.json')}
    def fail(session, command):
        session.actor.hp = 1
        session.scene.time += 99
        state._save_session(session)
        state.append_action_history(dict(action='半途操作',result='success',narrative_summary='必须回滚'),sid)
        raise HTTPException(409,'测试中断')
    monkeypatch.setattr('src.game.commands.dispatch',fail)
    await command(client,sid,'rest',action='long',expected=409,request_id='not-committed')
    state._sessions.clear()
    restored = state._get_session(sid,False)
    assert facts(restored) == before and 'not-committed' not in restored.command_receipts
    assert {p.name:p.read_bytes() for p in SAVE_DIR.glob('*.json')} == saves_before

@pytest.mark.asyncio
async def test_supplies_exhaustion_and_safe_rest_and_old_content(client):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    for _ in range(2): await command(client,sid,'rest',action='long')
    session = state._get_session(sid,False); before = facts(session)
    result = await command(client,sid,'rest',action='long',expected=409)
    assert '补给不足' in result['detail'] and facts(state._get_session(sid,False)) == before
    await command(client,sid,'move',target_id='village-square-01')
    free = await command(client,sid,'rest',action='long')
    assert free['state']['journey']['rest']['quantity'] == 0
    assert free['state']['journey']['rest']['can_long_rest']
    await command(client,sid,'pickup',target_id='camp-supply')
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    paid = await command(client,sid,'rest',action='long')
    assert paid['state']['journey']['rest']['quantity'] == 0
    state._get_session(sid,False).content_pack.supplies = None
    legacy = await command(client,sid,'rest',action='long')
    assert legacy['state']['journey']['rest']['cost'] == 0

@pytest.mark.asyncio
async def test_poison_from_scene_has_disadvantage_and_only_valid_actions_tick(client,monkeypatch):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await text(client,sid,'和托尔金说话')
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:1)
    failed = await text(client,sid,'检查废弃补给箱')
    assert failed['result']['outcome'] == 'failure'
    session = state._get_session(sid,False)
    assert session.actor.condition_turns == {'poisoned':3}
    await text(client,sid,'观察周围'); await text(client,sid,'召唤巨龙')
    assert session.actor.condition_turns == {'poisoned':3}
    rolls = iter([20,1]); monkeypatch.setattr('src.engine.dice.roll_d20',lambda:next(rolls))
    check = (await text(client,sid,'调查石门'))['result']['check']
    assert check['advantage'] is False and check['roll'] == 1
    assert session.actor.condition_turns == {'poisoned':2}
    await command(client,sid,'move',target_id='village-square-01')
    assert session.actor.condition_turns == {'poisoned':1}
    await command(client,sid,'move',target_id='tavern-01')
    assert 'poisoned' not in session.actor.conditions and not session.actor.condition_turns

@pytest.mark.asyncio
async def test_antidote_works_at_full_hp_and_is_not_wasted_without_poison(client):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='village-square-01')
    await command(client,sid,'pickup',target_id='antidote')
    await command(client,sid,'use',target_id='antidote',expected=400)
    session = state._get_session(sid,False)
    assert any(i.id=='antidote' for i in session.actor.inventory)
    add_condition(session.actor,'poisoned')
    used = await command(client,sid,'use',target_id='antidote')
    assert used['result']['item_use']['hp_change'] == 0
    actor = state.get_actor(sid)
    assert actor.hp == actor.hp_max and 'poisoned' not in actor.conditions
    assert not any(i.id=='antidote' for i in actor.inventory) and not actor.condition_turns
    add_condition(actor,'poisoned')
    await command(client,sid,'rest',action='long')
    assert 'poisoned' not in state.get_actor(sid).conditions

@pytest.mark.asyncio
async def test_inspiration_and_poison_cancel_then_inspiration_is_consumed(client,monkeypatch):
    sid = await create_session_and_character(client)
    await text(client,sid,'阅读行路笔记')
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await text(client,sid,'和托尔金说话')
    add_condition(state.get_actor(sid),'poisoned')
    rolls = iter([15]); monkeypatch.setattr('src.engine.dice.roll_d20',lambda:next(rolls))
    result = await text(client,sid,'调查石门')
    assert result['result']['check']['advantage'] is None
    assert 'inspired' not in state.get_actor(sid).conditions
    assert state.get_actor(sid).condition_turns == {'poisoned':2}

@pytest.mark.asyncio
async def test_authored_information_grants_advantage(client,monkeypatch):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await text(client,sid,'和托尔金说话')
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:20)
    await text(client,sid,'辨认古老碑文')
    guide = (await client.get('/exploration',headers={'X-Session-Id':sid})).json()
    assert '优势' in next(o for o in guide['objects'] if o['id']=='stone-door')['rule_hint']
    rolls = iter([1,20]); monkeypatch.setattr('src.engine.dice.roll_d20',lambda:next(rolls))
    result = await text(client,sid,'调查石门')
    assert result['result']['check']['advantage'] is True and result['result']['check']['roll'] == 20

@pytest.mark.asyncio
async def test_legacy_hostility_ending_is_durable_and_combat_stream_has_no_duplicate_narration(client):
    sid = await create_session_and_character(client)
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await text(client,sid,'和托尔金说话')
    from src.game.world import world_scene, make_enemy
    session = state._get_session(sid,False)
    npc = next(n for n in session.scene.npcs if n.id=='wounded-adventurer-01')
    world_scene(session).enemies[npc.id] = make_enemy(npc,session.content_pack)
    world_scene(session).aggression = True
    result = await command(client,sid,'attack',target_id='wounded-adventurer-01')
    ending = result['state']['journey']['ending']
    assert ending['id'] == 'broken-trust'
    state._sessions.clear()
    assert state.get_bootstrap_state(sid).journey['ending'] == ending
    response = await client.post('/commands',headers={'X-Session-Id':sid,'Accept':'text/event-stream'},json=dict(kind='text',text=dict(scene_id='x',actor='x',intent='防御',approach='')))
    assert response.status_code == 200,response.text
    chunks = [json.loads(b.split('data: ',1)[1]) for b in response.text.split('\n\n') if b.startswith('event: chunk')]
    assert len([c for c in chunks if c['field'] in ('narration','narrative')]) == 1
    assert state.get_bootstrap_state(sid).journey['ending'] == ending

@pytest.mark.asyncio
async def test_poison_cancels_feint_and_blocks_sneak_damage(client,predictable_combat,monkeypatch):
    from src.game import combat_service
    sid = await create_session_and_character(client,character_class='rogue')
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await command(client,sid,'move',target_id='combat-encounter-01')
    add_condition(state.get_actor(sid),'poisoned')
    seen = []
    original = combat_service.resolve_attack_with_equipment
    def attack(actor, ac, **kwargs):
        if actor.character_class: seen.append(kwargs.get('advantage'))
        return original(actor, ac, **kwargs)
    monkeypatch.setattr(combat_service,'resolve_attack_with_equipment',attack)
    await command(client,sid,'combat',action='feint')
    result = await command(client,sid,'combat',action='attack',target_id='goblin-01')
    assert seen == [None]
    assert not any(e.get('type')=='sneak_attack' for e in result['result']['events'])
    assert 'hidden' not in state.get_actor(sid).conditions
    assert state.get_actor(sid).condition_turns == {'poisoned':1}

@pytest.mark.asyncio
@pytest.mark.parametrize('condition,selected',[('poisoned',1),('inspired',20)])
async def test_spell_attack_uses_shared_conditions(client,predictable_combat,monkeypatch,condition,selected):
    sid = await create_session_and_character(client,character_class='mage')
    await command(client,sid,'move',target_id='dungeon-entrance-01')
    await command(client,sid,'move',target_id='combat-encounter-01')
    add_condition(state.get_actor(sid),condition)
    rolls = iter([1,20]); monkeypatch.setattr('src.spells.spell_resolver.roll_d20',lambda:next(rolls))
    result = await command(client,sid,'combat',action='ray_of_frost',target_id='goblin-01')
    spell = next(e['resolution'] for e in result['result']['events'] if e['type']=='spell')
    assert spell['attack_roll'] == selected
    if condition=='inspired': assert condition not in state.get_actor(sid).conditions
    else: assert state.get_actor(sid).condition_turns == {'poisoned':2}

@pytest.mark.asyncio
async def test_automatic_save_is_one_complete_receipt_and_manual_saves_are_retained(client):
    sid = await create_session_and_character(client)
    headers = {'X-Session-Id':sid}
    manual = (await client.post('/save',headers=headers,json={'save_name':'保留这一刻'})).json()
    await text(client,sid,'和老马库斯说话',request_id='last-action')
    await command(client,sid,'move',target_id='dungeon-entrance-01',request_id='last-move')
    saves = (await client.get('/saves')).json()['saves']
    automatic = [save for save in saves if save['save_id'].startswith('auto_')]
    assert len(automatic) == 1 and len(saves) == 2
    response = await client.post('/load',json={'save_id':automatic[0]['save_id']})
    assert response.status_code == 200,response.text
    session = state._get_session(sid,False)
    assert session.scene.id == 'dungeon-entrance-01' and 'last-move' in session.command_receipts
    replay = await command(client,sid,'move',target_id='dungeon-entrance-01',request_id='last-move')
    assert replay['replayed']
    response = await client.post('/load',json={'save_id':manual['save_id']})
    assert response.status_code == 200 and response.json()['scene']['id']=='tavern-01'

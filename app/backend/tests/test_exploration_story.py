"""Short adventure: alternate route, exact targets and durable consequences."""
import pytest
from src import state
from src.content.schema import ModulePack
from tests.conftest import create_session_and_character

async def act(client,sid,intent,**fields):
    r=await client.post('/action',headers={'X-Session-Id':sid},json=dict(scene_id='spoof',actor='spoof',intent=intent,approach='',**fields))
    assert r.status_code==200,r.text
    return r.json()

async def move(client,sid,target):
    r=await client.post('/map/move',headers={'X-Session-Id':sid},json={'target_scene_id':target})
    assert r.status_code==200,r.text
    return r.json()

async def guide(client,sid):
    return (await client.get('/exploration',headers={'X-Session-Id':sid})).json()

@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['warrior','mage','rogue'])
async def test_noncombat_route_rewards_once_survives_load_and_leaves_enemies(client,monkeypatch,predictable_combat,kind):
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:20)
    sid=await create_session_and_character(client,character_class=kind)
    h={'X-Session-Id':sid}
    await act(client,sid,'和老马库斯说话')
    await move(client,sid,'dungeon-entrance-01')
    await act(client,sid,'和托尔金说话')
    assert (await guide(client,sid))['quest']['status']=='active'
    await act(client,sid,'我想调查石门')
    report=await act(client,sid,'取出巡逻记录',interaction_id='patrol-report')
    assert report['check'] is None and report['outcome']=='success'
    assert state._get_session(sid,False).content_flags.count('patrol_report')==1
    snapshot=(await client.post('/save',headers=h,json={})).json()
    state._sessions.clear()
    await client.post('/load',json={'save_id':snapshot['save_id']})
    assert (await act(client,sid,'拾取巡逻记录'))['outcome']=='failure'
    await move(client,sid,'village-square-01')
    await move(client,sid,'tavern-01')
    assert '通知村民' in (await act(client,sid,'和老马库斯说话'))['narration']
    assert '通知村民' not in (await act(client,sid,'和老马库斯说话'))['narration']
    ready=await guide(client,sid)
    assert ready['quest']['status']=='ready' and '敌人仍在' in ready['quest']['objective']
    await move(client,sid,'dungeon-entrance-01')
    count=len(state.get_actor(sid).inventory)
    await act(client,sid,'和托尔金说话')
    assert len(state.get_actor(sid).inventory)==count+2
    assert (await guide(client,sid))['quest']['status']=='completed'
    await act(client,sid,'和托尔金说话')
    assert len(state.get_actor(sid).inventory)==count+2
    actor=state.get_actor(sid)
    assert actor.hp==actor.hp_max and actor.experience_points==300 and actor.level==2
    assert state._get_session(sid,False).adventure_outcome['id']=='warning-delivered'
    battle=await move(client,sid,'combat-encounter-01')
    assert len([p for p in battle['combat']['participants'] if not p['is_player'] and p['hp']>0])==3

@pytest.mark.asyncio
async def test_gates_failure_and_button_text_equivalence(client,monkeypatch):
    sid=await create_session_and_character(client)
    await move(client,sid,'dungeon-entrance-01')
    session=state._get_session(sid,False); tick=session.scene.time
    locked=await act(client,sid,'取出巡逻记录',interaction_id='patrol-report')
    assert locked['outcome']=='failure' and locked['check'] is None and session.scene.time==tick
    objects={o['id']:o for o in (await guide(client,sid))['objects']}
    assert objects['stone-door']['status']=='locked' and '托尔金' in objects['stone-door']['reason']
    await act(client,sid,'和托尔金说话')
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:1)
    failed=await act(client,sid,'调查石门')
    assert failed['outcome']=='failure' and session.scene.time==tick+1
    assert 'stone_marks' not in session.content_flags
    assert (await act(client,sid,'取出巡逻记录'))['outcome']=='failure'
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:20)
    success=await act(client,sid,'untrusted label',interaction_id='stone-door',dc=1,ability='str')
    assert success['check']['ability']=='int' and success['check']['dc']==10
    assert success['action_summary']=='调查石门' and session.scene.time==tick+2
    assert (await act(client,sid,'检查石门'))['outcome']=='failure' and session.scene.time==tick+2
    assert {o['id']:o for o in (await guide(client,sid))['objects']}['stone-door']['status']=='completed'

@pytest.mark.asyncio
@pytest.mark.parametrize('intent',['召唤一条龙','调查不存在的宝箱','不调查石门','调查石门然后杀死托尔金','intimidate the bandit leader'])
async def test_unknown_or_composite_input_cannot_roll_or_mutate_rules(client,monkeypatch,intent):
    sid=await create_session_and_character(client)
    await move(client,sid,'dungeon-entrance-01'); await act(client,sid,'和托尔金说话')
    session=state._get_session(sid,False)
    before=(session.actor.model_dump(),session.scene.time,list(session.content_flags))
    def forbidden(): raise AssertionError('Unknown input must not roll')
    monkeypatch.setattr('src.engine.dice.roll_d20',forbidden)
    result=await act(client,sid,intent,ability='str',dc=1)
    assert result['outcome']=='failure' and result['check'] is None and result['effects']==[]
    assert (session.actor.model_dump(),session.scene.time,session.content_flags)==before
    assert '可用行动' in result['narration']

@pytest.mark.asyncio
async def test_session_isolation_and_old_content_stays_pinned(client):
    first=await create_session_and_character(client); second=await create_session_and_character(client)
    await move(client,first,'dungeon-entrance-01'); await act(client,first,'和托尔金说话')
    old=state._get_session(second,False)
    assert 'passage_briefed' not in old.content_flags
    old.content_pack.version='1.0.1'; old.content_pack.scenes['dungeon-entrance-01'].interactions=[]
    state._save_session(old); await move(client,second,'dungeon-entrance-01')
    r=await client.post('/action',headers={'X-Session-Id':second},json=dict(scene_id='x',actor='x',intent='调查石门',approach='',interaction_id='stone-door'))
    assert r.status_code==400
    assert old.content_pack.version=='1.0.1' and (await guide(client,second))['objects']==[]

def test_interaction_event_reference_and_alternate_objective_validation():
    from src.content.store import builtin
    from pydantic import ValidationError
    pack=builtin().model_dump();pack['events']['report-recovered']['target_id']='elsewhere:patrol-report'
    with pytest.raises(ValidationError,match='target_id'):ModulePack.model_validate(pack)
    pack=builtin().model_dump();pack['quests']['clear-passage']['alternative_ready_text']=''
    with pytest.raises(ValidationError,match='替代任务路线'):ModulePack.model_validate(pack)

@pytest.mark.asyncio
async def test_streamed_interaction_has_same_result_and_no_duplicate_event(client,monkeypatch):
    import json
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:20)
    sid=await create_session_and_character(client)
    await move(client,sid,'dungeon-entrance-01');await act(client,sid,'和托尔金说话');await act(client,sid,'调查石门')
    session=state._get_session(sid,False);before=len(state.get_action_history(sid));tick=session.scene.time
    r=await client.post('/action',headers={'X-Session-Id':sid,'Accept':'text/event-stream'},json=dict(scene_id='x',actor='x',intent='取出巡逻记录',approach='',interaction_id='patrol-report'))
    assert r.status_code==200
    block=next(b for b in r.text.split('\n\n') if 'event: complete' in b)
    result=json.loads(block.split('data: ',1)[1])
    assert result['outcome']=='success' and result['check'] is None
    assert session.scene.time==tick+1 and len(state.get_action_history(sid))==before+1
    assert session.fired_events.count('report-recovered')==1
    saved=(await client.post('/save',headers={'X-Session-Id':sid},json={})).json()
    state._sessions.clear();await client.post('/load',json={'save_id':saved['save_id']})
    assert (await act(client,sid,'取出巡逻记录'))['outcome']=='failure'
    assert state._get_session(sid,False).fired_events.count('report-recovered')==1

@pytest.mark.asyncio
async def test_negative_and_multi_action_text_does_not_attack_or_deliver(client):
    sid=await create_session_and_character(client)
    for intent in ['不要和老马库斯说话','攻击老马库斯然后喝药水']:
        result=await act(client,sid,intent)
        assert result['outcome']=='failure'
    session=state._get_session(sid,False)
    assert not session.discovered_clues and not session.combat_snapshot
    assert session.scene.time==0

@pytest.mark.asyncio
async def test_failed_check_keeps_its_dice_and_outcome_after_reload(client,monkeypatch):
    sid=await create_session_and_character(client);h={'X-Session-Id':sid}
    await move(client,sid,'dungeon-entrance-01');await act(client,sid,'和托尔金说话')
    monkeypatch.setattr('src.engine.dice.roll_d20',lambda:1)
    failed=await act(client,sid,'调查石门')
    saved=(await client.post('/save',headers=h,json={})).json()
    state._sessions.clear();await client.post('/load',json={'save_id':saved['save_id']})
    history=(await client.get('/state',headers=h)).json()['narrative_history'][-1]
    assert history['resolution_summary']['outcome']=='failure'
    assert history['resolution_summary']['resolution_type']=='check'
    assert history['resolution_summary']['check']==failed['check']
    assert history['scene_progression']==failed['scene_progression']

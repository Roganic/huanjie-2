"""Friendly protection across button, text, spell and streamed command entry points."""
import pytest
from src import state
from src.game.commands import facts
from tests.conftest import create_session_and_character

@pytest.mark.asyncio
@pytest.mark.parametrize('entry',['direct','command','text','spell','stream'])
@pytest.mark.parametrize('name',['老马库斯','戴兜帽的商人'])
async def test_peaceful_targets_rejected_without_time_resources_or_story_changes(client,entry,name):
    sid=await create_session_and_character(client,character_class='mage')
    headers={'X-Session-Id':sid}
    # Use the real authored ID for this named neutral/friendly character.
    session=state._get_session(sid,False)
    npc_id=next(n.id for n in session.scene.npcs if n.name==name)
    before=facts(session)
    action=dict(scene_id='tavern-01',actor='unused',intent=f'攻击{name}',approach='',target=npc_id)
    if entry=='direct': path,body='/combat/start',dict(target_id=npc_id)
    elif entry=='command': path,body='/commands',dict(kind='attack',target_id=npc_id)
    elif entry=='text': path,body='/action',action
    else:
        if entry=='spell': action['intent']=f'对{name}施放魔法飞弹'
        if entry=='stream': headers['Accept']='text/event-stream'
        path,body='/commands',dict(kind='text',text=action)
    response=await client.post(path,headers=headers,json=body)
    assert response.status_code==409,response.text
    assert '暂不支持攻击' in response.json()['detail']
    assert facts(state._get_session(sid,False))==before
    guide=(await client.get('/exploration',headers=headers)).json()
    assert all(not target['attackable'] for target in guide['targets'])
    assert session.scene.time==0 and session.adventure_outcome is None

@pytest.mark.asyncio
async def test_rejecting_giver_attack_does_not_fail_quest_or_prevent_dialogue(client):
    sid=await create_session_and_character(client);headers={'X-Session-Id':sid}
    await client.post('/commands',headers=headers,json=dict(kind='move',target_id='dungeon-entrance-01'))
    action=dict(scene_id='x',actor='x',intent='和托尔金说话',approach='')
    await client.post('/action',headers=headers,json=action)
    response=await client.post('/commands',headers=headers,json=dict(kind='attack',target_id='wounded-adventurer-01'))
    assert response.status_code==409
    result=await client.post('/action',headers=headers,json=action)
    assert result.status_code==200 and result.json()['outcome']=='success'
    session=state._get_session(sid,False)
    assert session.quest_states['clear-passage']=='active' and session.adventure_outcome is None

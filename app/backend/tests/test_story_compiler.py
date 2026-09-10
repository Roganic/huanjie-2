import pytest
from pydantic import ValidationError
from src.content.compiler import compile_story, flag
from src.content.schema import ModulePack
from src.models.state import CharacterCreateRequest
from src.game.commands import execute_command, GameCommand
from src import state


def outline():
    return {'name':'桥头的纸灯','description':'找回信件。','starting_scene_id':'home',
        'locations':[{'id':'home','name':'家门','description':'阿梅在门边等你。','exits':['bridge']},
                     {'id':'bridge','name':'石桥','description':'信夹在桥栏里。','exits':['home']}],
        'people':[{'id':'mei','name':'阿梅','scene_id':'home','type':'friendly','dialogue':'请帮我找回信件。'}],
        'beats':[{'id':'find','name':'发现信件','scene_id':'bridge','trigger':'arrive','success':{'narration':'你发现了夹在桥栏里的信。'}}],
        'quests':[{'id':'letter','name':'找回信件','giver_id':'mei','objective':'去石桥找到信件，再交给阿梅。',
            'requires':[{'beat_id':'find'}],'ready_text':'信已经找到。','xp_reward':10}],
        'endings':[{'id':'lamplight','title':'灯下','description':'信回到了阿梅手里。','completed_quests':['letter']}]}


def play(document):
    sid=state.create_session().session_id
    session=state._get_session(sid,False);session.content_pack=ModulePack.model_validate(document)
    state.create_character(CharacterCreateRequest(name='旅人',character_class='warrior'),sid)
    def act(kind,target):return execute_command(sid,GameCommand(kind=kind,target_id=target))['result']
    return session,act


def test_compiled_story_requires_actual_journey_and_single_settlement():
    graph=outline();doc=compile_story(graph)
    assert doc['id'].isascii()
    s,act=play(doc)
    act('talk','mei');act('talk','mei')
    assert s.actor.experience_points==0 and s.adventure_outcome is None and flag('find') not in s.content_flags
    act('move','bridge');assert flag('find') in s.content_flags
    assert s.adventure_outcome is None
    act('move','home');act('talk','mei')
    assert s.actor.experience_points==10 and s.adventure_outcome['id']=='lamplight'
    act('talk','mei');assert s.actor.experience_points==10


def test_failure_path_and_delayed_consequence_are_real_events(monkeypatch):
    graph=outline()
    graph['beats']=[{'id':'find','name':'撬开匣子','scene_id':'bridge','trigger':'check','skill':'investigation','dc':15,
        'stakes':'失败会弄湿纸张，需要复原。','success':{'narration':'信完好无损。'},'failure':{'narration':'纸张被打湿。'}},
        {'id':'repair','name':'复原纸张','scene_id':'bridge','trigger':'interact','requires':[{'beat_id':'find','outcome':'failure'}],
         'success':{'narration':'纸上的字渐渐显现。','delay':3}}]
    q=graph['quests'][0];q.update(alternative=[{'beat_id':'repair'}],alternative_objective='复原湿信，再交给阿梅。',alternative_ready_text='湿信已经复原。')
    s,act=play(compile_story(graph));monkeypatch.setattr('src.engine.dice.roll_d20',lambda:1)
    act('talk','mei');act('move','bridge');act('challenge','find');act('interact','repair')
    assert flag('find','failure') in s.content_flags and flag('repair') not in s.content_flags
    act('move','home');act('move','bridge');act('move','home');act('talk','mei')
    assert s.adventure_outcome['id']=='lamplight' and s.actor.experience_points==10


@pytest.mark.parametrize('fault',['cycle','missing','duplicate','impossible_failure','unreachable','conflicting_branches','reversed_cancellation'])
def test_invalid_causal_graph_is_rejected_before_installation(fault):
    graph=outline()
    if fault=='cycle':graph['beats'][0]['requires']=[{'beat_id':'find'}]
    if fault=='missing':graph['quests'][0]['requires']=[{'beat_id':'not-created'}]
    if fault=='duplicate':graph['locations'].append(graph['locations'][0])
    if fault=='impossible_failure':graph['quests'][0]['requires']=[{'beat_id':'find','outcome':'failure'}]
    if fault=='unreachable':graph['locations'][0]['exits']=[]
    if fault=='reversed_cancellation':graph['beats'][0]['success']['cancel_after']=[{'beat_id':'find'}]
    if fault=='conflicting_branches':
        graph['beats'][0].update(trigger='check',skill='investigation',stakes='失败会弄湿信件。',failure={'narration':'信被打湿了。'})
        graph['beats'].append({'id':'repair','name':'复原','scene_id':'bridge','trigger':'interact',
            'requires':[{'beat_id':'find','outcome':'failure'}],'success':{'narration':'纸张恢复了。'}})
        graph['quests'][0]['requires']=[{'beat_id':'find'},{'beat_id':'repair'}]
    with pytest.raises(ValidationError):compile_story(graph)


@pytest.mark.parametrize('roll', [1, 20])
def test_alternative_evidence_joins_same_goal_and_preserves_time_cost(monkeypatch, roll):
    graph = outline()
    graph['beats'] = [
        {'id': 'find', 'name': '找信', 'scene_id': 'bridge', 'trigger': 'check', 'skill': 'investigation',
         'stakes': '失败需要复原', 'success': {'narration': '找到完整信件。'}, 'failure': {'narration': '信湿了。'}},
        {'id': 'repair', 'name': '复原信件', 'scene_id': 'bridge', 'trigger': 'interact', 'time_cost': 3,
         'requires': [{'beat_id': 'find', 'outcome': 'failure'}], 'success': {'narration': '复原了信件。'}},
        {'id': 'pack', 'name': '收好信件', 'scene_id': 'bridge', 'trigger': 'interact',
         'requires_any': [{'beat_id': 'find'}, {'beat_id': 'repair'}], 'success': {'narration': '信件收好了。'}}]
    graph['quests'][0]['requires'] = [{'beat_id': 'pack'}]
    session, act = play(compile_story(graph))
    monkeypatch.setattr('src.engine.dice.roll_d20', lambda: roll)
    act('talk', 'mei'); act('move', 'bridge')
    assert act('interact', 'pack')['action_status'] == 'blocked'
    act('challenge', 'find')
    if roll == 1:
        assert act('interact', 'pack')['action_status'] == 'blocked'
        before = session.event_clock.world_seconds
        act('interact', 'repair')
        assert session.event_clock.world_seconds - before == 180
    act('interact', 'pack'); act('move', 'home'); act('talk', 'mei')
    assert session.adventure_outcome['id'] == 'lamplight'
    assert session.actor.experience_points == 10


def test_story_timer_resolves_after_leaving_its_origin():
    graph = outline()
    graph['beats'].append({'id': 'fog', 'name': '起雾', 'scene_id': 'home', 'trigger': 'talk', 'target_id': 'mei',
                           'success': {'narration': '雾覆盖了小镇。', 'delay': 1, 'scope': 'story'}})
    session, act = play(compile_story(graph))
    act('talk', 'mei'); act('move', 'bridge')
    assert session.scene.id == 'bridge' and flag('fog') in session.content_flags


def test_late_and_timely_endings_are_exclusive_regardless_of_list_order():
    graph = outline()
    graph['beats'].append({'id': 'fog', 'name': '浓雾', 'scene_id': 'home', 'trigger': 'talk', 'target_id': 'mei',
        'success': {'narration': '雾已封桥。', 'delay': 1, 'scope': 'story'}})
    graph['endings'][0]['excludes'] = [{'beat_id': 'fog'}]
    graph['endings'].append({'id': 'late', 'title': '迟来的信', 'description': '信送到了，但已经错过约定。',
        'completed_quests': ['letter'], 'requires': [{'beat_id': 'fog'}]})
    session, act = play(compile_story(graph))
    act('talk', 'mei'); act('move', 'bridge'); act('move', 'home'); act('talk', 'mei')
    assert session.adventure_outcome['id'] == 'late'
    assert session.actor.experience_points == 10


def test_ending_cannot_exclude_a_transitively_required_fact():
    graph = outline()
    graph['beats'].append({'id': 'deliver', 'name': '收好信', 'scene_id': 'bridge', 'trigger': 'interact',
        'requires': [{'beat_id': 'find'}], 'success': {'narration': '把信收好了。'}})
    graph['endings'][0].update(requires=[{'beat_id': 'deliver'}], excludes=[{'beat_id': 'find'}])
    with pytest.raises(ValidationError, match='无法达成'):
        compile_story(graph)
    graph['endings'][0]['requires'] = []
    graph['endings'][0]['requires_any'] = [{'beat_id': 'deliver'}]
    with pytest.raises(ValidationError, match='备选前置分支'):
        compile_story(graph)


def test_same_conversation_arms_dependent_timer_once_without_synthetic_arrival():
    graph = outline()
    # Deliberately reverse dependency order to catch accidental reliance on JSON order.
    graph['beats'] += [
        {'id': 'rain', 'name': '下雨', 'scene_id': 'home', 'trigger': 'talk', 'target_id': 'mei',
         'requires': [{'beat_id': 'greet'}], 'success': {'narration': '雨来了。', 'delay': 3, 'scope': 'story'}},
        {'id': 'greet', 'name': '接过委托', 'scene_id': 'home', 'trigger': 'talk', 'target_id': 'mei',
         'success': {'narration': '阿梅说明了委托。'}},
        {'id': 'return', 'name': '回来', 'scene_id': 'home', 'trigger': 'arrive',
         'requires': [{'beat_id': 'greet'}], 'success': {'narration': '你回来了。'}}]
    session, act = play(compile_story(graph))
    act('talk', 'mei')
    timer = session.scheduled_events['rain']
    assert timer.status == 'scheduled' and timer.due - timer.created_at == 180
    assert flag('greet') in session.content_flags and flag('return') not in session.content_flags
    deadline = timer.due
    act('talk', 'mei')
    assert session.scheduled_events['rain'].due == deadline
    act('move', 'bridge'); act('move', 'home')
    assert flag('return') in session.content_flags


def test_delayed_interaction_does_not_announce_its_result_early():
    graph = outline()
    graph['beats'][0].update(trigger='interact', success={'narration': '墨水终于显出文字。', 'delay': 3})
    session, act = play(compile_story(graph))
    act('move', 'bridge')
    result = act('interact', 'find')
    assert '墨水终于显出文字' not in result['narration']
    assert flag('find') not in session.content_flags


def test_immediate_interaction_narration_is_not_duplicated():
    graph = outline(); graph['beats'][0]['trigger'] = 'interact'
    session, act = play(compile_story(graph))
    act('move', 'bridge')
    result = act('interact', 'find')
    assert result['narration'].count('你发现了夹在桥栏里的信。') == 1


def test_npc_knowledge_unlocks_from_actual_story_facts_and_validates_references():
    graph = outline()
    graph['people'][0]['knowledge'] = [{'id': 'sender', 'text': '信来自远方的姐姐。', 'requires': [{'beat_id': 'find'}]}]
    pack = compile_story(graph)
    session, act = play(pack)
    knowledge = session.content_pack.characters['mei'].knowledge[0]
    assert not set(knowledge.required_flags) <= set(session.content_flags)
    act('move', 'bridge')
    assert set(knowledge.required_flags) <= set(session.content_flags)
    graph['people'][0]['knowledge'][0]['requires'][0]['beat_id'] = 'missing'
    with pytest.raises(ValidationError, match='不存在'):
        compile_story(graph)

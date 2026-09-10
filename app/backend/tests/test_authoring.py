"""Author workflows: non-combat goals, parse/repair boundary and isolated drafts."""
import json
import pytest
from src import state
from src.content import authoring, store
from src.content.schema import ModulePack
from src.gm.provider import ModelUnavailable
from src.game.world import quest_views, quest_dialogue
from tests.test_story_compiler import outline


def story():
    return {'id': 'paper-lantern', 'version': '1.0', 'name': '纸灯', 'description': '寻找失落的信。', 'starting_scene_id': 'home',
        'scenes': {'home': {'id': 'home', 'name': '家门', 'description': '灯还亮着。', 'character_ids': ['mei'], 'exits': [{'direction': '桥', 'target_scene_id': 'bridge'}]},
                   'bridge': {'id': 'bridge', 'name': '石桥', 'description': '桥栏下夹着信。', 'exits': [{'direction': '回家', 'target_scene_id': 'home'}]}},
        'characters': {'mei': {'id': 'mei', 'name': '阿梅', 'type': 'friendly', 'dialogue': '替我找回那封信。'}}, 'items': {},
        'quests': {'letter': {'id': 'letter', 'name': '迟到的信', 'kind': 'flags', 'giver_id': 'mei', 'target_scene_id': 'bridge',
            'objective': '到石桥找信，带回家门。', 'required_flags': ['letter-found'], 'ready_text': '信已找回。', 'xp_reward': 10}},
        'events': {'find': {'id': 'find', 'on': 'enter_scene', 'target_id': 'bridge', 'narration': '你找到了那封信。', 'set_flags': ['letter-found']}},
        'endings': [{'id': 'home-again', 'title': '灯下', 'description': '信已送达。', 'completed_quests': ['letter']}]}


def test_peaceful_quest_requires_actual_flags_and_only_rewards_once():
    pack = ModulePack.model_validate(story())
    sid = state.create_session().session_id
    session = state._get_session(sid, False)
    session.content_pack = pack
    from src.models.state import CharacterCreateRequest
    state.create_character(CharacterCreateRequest(name='测试旅人', character_class='warrior'), sid)
    quest_dialogue(session, 'mei')
    assert session.quest_states['letter'] == 'active'
    assert '击败' not in quest_views(session)[0]['objective']
    session.content_flags.append('letter-found')
    assert quest_views(session)[0]['status'] == 'ready'
    quest_dialogue(session, 'mei')
    xp = session.actor.experience_points
    assert session.quest_states['letter'] == 'completed' and xp == 10
    quest_dialogue(session, 'mei')
    assert session.actor.experience_points == xp


@pytest.mark.asyncio
async def test_text_parser_repairs_draft_without_installing_or_mutating(monkeypatch, tmp_path):
    monkeypatch.setattr(store, 'MODULE_DIR', tmp_path / 'modules')
    bad = outline(); bad['starting_scene_id'] = 'missing'
    responses = [bad, outline()]
    prompts = []
    class Provider:
        model = 'test'
        async def complete(self, messages, tools, timeout, **kwargs):
            prompts.append(list(messages))
            if len(prompts) == 1:
                return 'submit_module', {'document': json.dumps(responses.pop(0)), 'assumptions': ['默认低等级。'], 'questions': []}, {}, {'input_tokens': 12, 'output_tokens': 15}
            return 'revise_module', {'patches': [{'op': 'replace', 'path': '/starting_scene_id', 'value': 'home'}],
                'coverage': [{'source_excerpt': '寻找信件', 'references': ['beats:find', 'quests:letter'], 'note': '找到信件才能交付任务。'}],
                'assumptions': [], 'questions': []}, {}, {'input_tokens': 12, 'output_tokens': 15}
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    result = await authoring.ModelStoryParser().parse('寻找信件的故事。')
    assert result['valid'] and result['module']['name'] == '桥头的纸灯'
    assert result['usage'] == {'calls': 2, 'input_tokens': 24, 'output_tokens': 30}
    assert '起始地点不存在' in prompts[1][-1]['content']
    assert not (tmp_path / 'modules').exists()


@pytest.mark.asyncio
async def test_model_failure_is_explicit_and_does_not_fabricate_story(monkeypatch):
    class Provider:
        model = 'test'
        async def complete(self, *a, **kw): raise ModelUnavailable('rate_limit')
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    result = await authoring.ModelStoryParser().parse('小镇的故事。')
    assert not result['valid'] and result['draft'] is None
    assert result['issues'][0]['type'] == 'model_unavailable'


@pytest.mark.asyncio
async def test_invalid_model_format_still_reports_returned_usage(monkeypatch):
    class Provider:
        model = 'test'
        async def complete(self, *a, **kw):
            raise ModelUnavailable('provider_error', usage={'input_tokens': 100, 'output_tokens': 20})
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    result = await authoring.ModelStoryParser().parse('没有返回完整结构的故事。')
    assert not result['valid'] and result['usage'] == {'input_tokens': 100, 'output_tokens': 20, 'calls': 1}


@pytest.mark.asyncio
async def test_saved_outline_repair_feeds_new_validation_back_without_regeneration(client, monkeypatch):
    graph = outline(); graph['starting_scene_id'] = 'missing'
    calls = []
    class Provider:
        model = 'test'
        async def complete(self, messages, tools, timeout, **kwargs):
            assert tools[0]['function']['name'] == 'revise_module'
            calls.append(messages[-1]['content'])
            patches = [{'op': 'replace', 'path': '/starting_scene_id', 'value': 'home'},
                {'op': 'replace', 'path': '/quests/0/requires', 'value': [{'beat_id': 'unknown'}]}] if len(calls) == 1 else [
                {'op': 'replace', 'path': '/quests/0/requires', 'value': [{'beat_id': 'find'}]}]
            return 'revise_module', {'patches': patches, 'coverage': [{'source_excerpt': '找到信件',
                'references': ['beats:find'], 'note': '进入桥头找到信件。'}], 'assumptions': [], 'questions': []}, {}, {'input_tokens': 10, 'output_tokens': 5}
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    response = await client.post('/modules/repair', json={'source': '阿梅请你到桥头找信，找到信件之后回到家门报告任务。',
        'outline': json.dumps(graph, ensure_ascii=False)})
    result = response.json()
    assert response.status_code == 200 and result['valid']
    assert 'unknown' in calls[1] and result['usage']['calls'] == 2
    assert graph['starting_scene_id'] == 'missing'


def test_preflight_reports_reward_and_encounter_mistakes_despite_an_unrelated_schema_error():
    graph = outline(); graph['starting_scene_id'] = 'missing'
    graph['quests'][0]['rewards'] = [{'item_id': 'medal'}]
    graph['beats'][0]['success']['effects'] = [{'kind': 'item', 'target_id': 'medal'}, {'kind': 'encounter', 'target_id': 'timer'}]
    result = authoring.document_review(graph)
    assert not result['valid']
    assert {'reward_overlap', 'invalid_encounter'} <= {w['type'] for w in result['warnings']}


def test_stable_patch_targets_survive_earlier_deletions_and_keep_batches_atomic():
    from src.content.revision import apply_patches, DraftPatch
    original = {'beats': [{'id': 'first', 'name': '一'}, {'id': 'second', 'name': '二'}, {'id': 'third', 'name': '三'}]}
    changes = [DraftPatch(op='remove', path='/beats/@first'), DraftPatch(op='remove', path='/beats/@second'),
               DraftPatch(op='replace', path='/beats/@third/name', value='第三件事')]
    assert apply_patches(original, changes) == {'beats': [{'id': 'third', 'name': '第三件事'}]}
    assert len(original['beats']) == 3
    with pytest.raises(ValueError, match='标识不存在'):
        apply_patches(original, [*changes, DraftPatch(op='remove', path='/beats/@missing')])
    assert len(original['beats']) == 3


@pytest.mark.asyncio
async def test_failed_generated_structure_survives_save_and_manual_repair(client, monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, 'DRAFT_DIR', tmp_path / 'drafts')
    bad = outline(); bad['starting_scene_id'] = 'missing'
    class Provider:
        model = 'test'
        async def complete(self, *a, **kw):
            return 'submit_module', {'document': bad, 'assumptions': ['低等级调查。'], 'questions': ['信是谁写的？']}, {}, {}
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    result = await authoring.ModelStoryParser().parse('未完成的送信故事。')
    assert not result['valid'] and result['draft'] is None
    assert result['outline'] == bad and result['questions'] == ['信是谁写的？']
    pending = {'format': 'story_graph', 'source': json.dumps(bad, ensure_ascii=False)}
    saved = (await client.post('/modules/drafts', json={'document': story(), 'pending': pending,
        'assumptions': result['assumptions'], 'questions': result['questions']})).json()
    reopened = (await client.get('/modules/drafts')).json()['drafts'][0]
    assert reopened['pending'] == pending and not reopened['review']['valid']
    assert reopened['document'] == story() and reopened['review']['questions'] == result['questions']
    repaired = await client.post('/modules/parse', json={'format': 'story_graph', 'source': json.dumps(outline())})
    assert repaired.json()['valid']
    r = await client.post('/modules/drafts', json={'id': saved['id'], 'document': repaired.json()['module']})
    assert r.json()['pending'] is None and r.json()['review']['valid']
    # Incomplete JSON edits are also retained verbatim, never applied as a module.
    pending = {'format': 'json', 'source': '{"name":'}
    r = await client.post('/modules/drafts', json={'id': saved['id'], 'document': story(), 'pending': pending})
    assert r.json()['pending'] == pending and not r.json()['review']['valid']


@pytest.mark.asyncio
async def test_invalid_draft_can_be_saved_reopened_and_repaired(client, monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, 'DRAFT_DIR', tmp_path / 'drafts')
    invalid = story(); invalid['scenes']['home']['exits'][0]['target_scene_id'] = 'missing'
    r = await client.post('/modules/drafts', json={'source': '原故事', 'document': invalid,
        'assumptions': ['默认调查难度为 10。'], 'questions': ['送信人是否知道真相？']})
    assert r.status_code == 200 and not r.json()['review']['valid']
    draft_id = r.json()['id']
    reopened = (await client.get('/modules/drafts')).json()['drafts'][0]
    assert reopened['document'] == invalid
    assert reopened['review']['assumptions'] == ['默认调查难度为 10。']
    assert reopened['review']['questions'] == ['送信人是否知道真相？']
    r = await client.post('/modules/drafts', json={'id': draft_id, 'source': '原故事', 'document': story()})
    assert r.json()['review']['valid']
    assert len((await client.get('/modules/drafts')).json()['drafts']) == 1
    assert (await client.post('/modules/drafts', json={'id': '../escape', 'document': story()})).status_code == 422


def test_review_reports_disconnected_map_and_unproducible_goal():
    document = story(); document['scenes']['home']['exits'] = []; document['events'] = {}
    result = authoring.review(document)
    assert result['valid']
    assert {w['type'] for w in result['warnings']} == {'unreachable', 'unproduced_flag'}


@pytest.mark.asyncio
async def test_valid_syntax_still_receives_source_review_and_mapping_survives_draft(client, monkeypatch, tmp_path):
    monkeypatch.setattr(authoring, 'DRAFT_DIR', tmp_path)
    graph = outline(); graph['quests'][0]['xp_reward'] = 0
    class Provider:
        model = 'test'
        async def complete(self, messages, tools, timeout, **kwargs):
            if tools[0]['function']['name'] == 'submit_module':
                return 'submit_module', {'document': graph, 'assumptions': [], 'questions': []}, {}, {}
            return 'revise_module', {'patches': [{'op': 'replace', 'path': '/quests/0/xp_reward', 'value': 10}],
                'coverage': [{'source_excerpt': '交还信件获得十点经验', 'references': ['quests:letter'], 'note': '找到信件后交还阿梅，结算十点经验。'}],
                'assumptions': [], 'questions': []}, {}, {}
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    result = await authoring.ModelStoryParser().parse('到桥头找信，交还信件获得十点经验。')
    assert result['valid'] and result['usage']['calls'] == 2
    assert result['module']['quests']['letter']['xp_reward'] == 10
    assert graph['quests'][0]['xp_reward'] == 0
    response = await client.post('/modules/drafts', json={'document': result['module'], 'source': result['source'], 'coverage': result['coverage']})
    assert response.status_code == 200
    loaded = (await client.get('/modules/drafts')).json()['drafts'][0]
    assert loaded['review']['coverage'] == result['coverage']


def test_reviewer_patch_failure_is_atomic_and_cannot_escape_document():
    from src.content.revision import DraftPatch, apply_patches
    original = outline()
    patches = [DraftPatch(op='replace', path='/name', value='changed'), DraftPatch(op='add', path='/../../secret', value='bad')]
    with pytest.raises(ValueError): apply_patches(original, patches)
    assert original['name'] == '桥头的纸灯'


def test_set_revision_can_fill_omitted_fields_but_cannot_invent_array_targets():
    from src.content.revision import DraftPatch, apply_patches
    original = {'endings': [{'id': 'end'}]}
    set_field = DraftPatch(op='set', path='/endings/@end/excludes', value=[])
    assert apply_patches(original, [set_field])['endings'][0]['excludes'] == []
    assert 'excludes' not in original['endings'][0]
    with pytest.raises(ValueError):
        apply_patches(original, [set_field, DraftPatch(op='set', path='/endings/@absent', value={})])
    assert original == {'endings': [{'id': 'end'}]}


@pytest.mark.asyncio
async def test_invalid_patch_is_returned_for_bounded_repair_and_resolved_questions_clear(monkeypatch):
    calls = []
    class Provider:
        model = 'test'
        async def complete(self, messages, *args, **kwargs):
            calls.append(json.loads(messages[-1]['content']))
            patches = [{'op': 'replace', 'path': '/endings/@home-again/excludes', 'value': []}] if len(calls) == 1 else [
                {'op': 'set', 'path': '/endings/@home-again/excludes', 'value': []}]
            return 'revise_module', {'patches': patches, 'coverage': [{'source_excerpt': '找到信件',
                'references': ['beats:find'], 'note': '找到信件后报告。'}], 'assumptions': [], 'questions': []}, {}, {}
    monkeypatch.setattr(authoring, 'ToolProvider', Provider)
    graph = outline()
    # Use the actual fixture's ending identifier; omitted excludes must stay omitted until set.
    graph['endings'][0]['id'] = 'home-again'
    graph['endings'][0].pop('excludes', None)
    result = await authoring.ModelStoryParser().parse('找到信件之后报告。', previous={'outline': graph, 'questions': ['旧问题']})
    assert result['valid'] and result['questions'] == [] and len(calls) == 2
    assert any(e['type'] == 'invalid_revision' for e in calls[1]['validation_issues'])
    assert 'excludes' not in graph['endings'][0]

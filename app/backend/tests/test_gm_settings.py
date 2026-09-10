"""Local settings security, secret preservation and real-tool compatibility contract."""
import json
import httpx
import pytest
from src.gm import provider

BODY = {'enabled': True, 'style': 'qwen', 'url': 'https://example.invalid/v1', 'model': 'qwen3.7-plus', 'api_key': 'secret-test-key'}


@pytest.mark.asyncio
async def test_authoring_json_adapter_cannot_turn_gameplay_prose_into_actions(monkeypatch):
    model = provider.ToolProvider({'GM_API_KEY': 'test-key', 'GM_API_URL': 'https://example.invalid/chat/completions',
        'GM_MODEL': 'qwen3.7-plus', 'GM_API_STYLE': 'qwen', 'GM_BUDGET_YUAN': '1'})
    content = '{"document":{},"assumptions":[],"questions":[]}'
    async def post(self, url, **kwargs):
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices': [{'message': {'content': content}}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20}})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    tool = {'type': 'function', 'function': {'name': 'submit_module', 'parameters': {
        'properties': {'document': {}, 'assumptions': {}, 'questions': {}}, 'required': ['document', 'assumptions', 'questions']}}}
    name, args, _, usage = await model.complete([], [tool], 1)
    assert name == 'submit_module' and args['document'] == {} and usage['output_tokens'] == 20
    for invalid in ('{"document":{},"assumptions":[],"questions":[],"execute":"attack"}', '故事尚未完成'):
        content = invalid
        with pytest.raises(provider.ModelUnavailable) as error:
            await model.complete([], [tool], 1)
        assert error.value.usage == {'input_tokens': 100, 'output_tokens': 20}
    tool['function']['name'] = 'act'
    content = '{"document":{},"assumptions":[],"questions":[]}'
    with pytest.raises(provider.ModelUnavailable):
        await model.complete([], [tool], 1)


def test_authoring_stream_joins_tool_arguments_and_rejects_partial_documents():
    parts = [
        {'choices': [{'index': 0, 'delta': {'reasoning_content': 'internal', 'tool_calls': [{'index': 0, 'id': 'a', 'type': 'function', 'function': {'name': 'submit_module', 'arguments': '{"document":'}}]}}]},
        {'choices': [{'index': 0, 'delta': {'tool_calls': [{'index': 0, 'function': {'arguments': '{"name":"纸灯"}}'}}]}, 'finish_reason': 'tool_calls'}]},
        {'choices': [], 'usage': {'prompt_tokens': 100, 'completion_tokens': 20}},
    ]
    raw = ''.join('data: ' + json.dumps(p, ensure_ascii=False) + '\n\n' for p in parts)
    response = lambda text: httpx.Response(200, headers={'content-type': 'text/event-stream'}, text=text)
    result = provider.completion_data(response(raw + 'data: [DONE]\n\n'))
    call = result['choices'][0]['message']['tool_calls'][0]
    assert json.loads(call['function']['arguments']) == {'document': {'name': '纸灯'}}
    assert result['usage']['completion_tokens'] == 20 and 'internal' not in json.dumps(result)
    with pytest.raises(ValueError, match='incomplete'):
        provider.completion_data(response(raw))

@pytest.mark.asyncio
async def test_glm_settings_and_tool_only_response_contract(client, monkeypatch):
    client.base_url = 'http://127.0.0.1:8000'
    assert (await client.put('/gm/settings', json={**BODY, 'style': 'glm'})).status_code == 200
    message = {'tool_calls': [{'id': 'glm-call', 'type': 'function',
        'function': {'name': 'respond', 'arguments': '{"message":"你好。"}'}}]}
    async def post(self, url, **kwargs):
        payload = kwargs['json']
        assert payload['tool_choice'] == 'auto'
        assert payload['thinking'] == {'type': 'disabled'}
        assert 'parallel_tool_calls' not in payload
        return httpx.Response(200, request=httpx.Request('POST', url), json={'choices': [{'message': message}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    model = provider.ToolProvider()
    assert (await model.complete([], [], 1))[0] == 'respond'
    # auto must not let plain prose or multiple operations bypass the host contract.
    for invalid in ({'content': '已给你金币。'}, {'tool_calls': message['tool_calls'] * 2}):
        message = invalid
        with pytest.raises(provider.ModelUnavailable):
            await model.complete([], [], 1)

@pytest.mark.asyncio
async def test_local_settings_preserve_secret_and_normalize_without_leaking(client):
    # Local administration uses a verified loopback Host in addition to peer/origin checks.
    client.base_url = 'http://127.0.0.1:8000'
    saved = await client.put('/gm/settings', json=BODY)
    assert saved.status_code == 200
    assert saved.json()['has_key'] and saved.json()['url'].endswith('/v1/chat/completions')
    assert 'secret-test-key' not in saved.text
    assert provider.CONFIG_FILE.stat().st_mode & 0o777 == 0o600
    public = (await client.get('/gm/settings')).json()
    update = {**BODY, 'api_key': '', 'url': public['url'], 'model': 'other-model'}
    assert (await client.put('/gm/settings', json=update)).status_code == 200
    assert provider.configuration()['GM_API_KEY'] == BODY['api_key']
    assert provider.ToolProvider().model == 'other-model'
    assert (await client.put('/gm/settings', json={**update, 'url': 'https://other.invalid/v1'})).status_code == 400
    assert provider.configuration()['GM_MODEL'] == 'other-model'

@pytest.mark.asyncio
async def test_settings_reject_foreign_origin_host_and_secret_in_validation(client):
    assert (await client.get('/gm/settings')).status_code == 403
    client.base_url = 'http://127.0.0.1:8000'
    response = await client.put('/gm/settings', headers={'Origin': 'https://attacker.invalid'}, json=BODY)
    assert response.status_code == 403 and not provider.CONFIG_FILE.exists()
    for body in ({**BODY, 'api_key': {'bad': 'secret-test-key'}}, {**BODY, 'model': 'x\nGM_API_KEY=secret-test-key'}, {**BODY, 'url':'https://user:secret-test-key@example.invalid/v1'}):
        response = await client.put('/gm/settings', json=body)
        assert response.status_code == 400 and 'secret-test-key' not in response.text
    assert not provider.CONFIG_FILE.exists()

@pytest.mark.asyncio
async def test_draft_connection_test_uses_tools_without_saving_or_exposing_key(client, monkeypatch):
    client.base_url = 'http://127.0.0.1:8000'
    async def post(self, url, **kwargs):
        assert url.endswith('/chat/completions')
        assert kwargs['json']['tools'][0]['function']['name'] == 'respond'
        assert kwargs['headers']['Authorization'] == 'Bearer secret-test-key'
        return httpx.Response(200, request=httpx.Request('POST', url), json={
            'choices':[{'message': {'tool_calls':[{'id':'1', 'type':'function','function':{'name':'respond','arguments':json.dumps({'message':'欢迎冒险者。'})}}]}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 4}})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)  # Call the ASGI client with .request to avoid patching it.
    response = await client.request('POST', '/gm/test', json=BODY)
    assert response.json()['ok'] and response.json()['usage']['input_tokens'] == 10
    assert not provider.CONFIG_FILE.exists() and 'secret-test-key' not in response.text
    async def denied(self, url, **kwargs):
        return httpx.Response(401, request=httpx.Request('POST',url), text='secret-test-key')
    monkeypatch.setattr(httpx.AsyncClient, 'post', denied)
    response = await client.request('POST','/gm/test',json=BODY)
    assert not response.json()['ok'] and '密钥无效' in response.json()['message']
    assert 'secret-test-key' not in response.text

@pytest.mark.asyncio
async def test_environment_override_cannot_silently_save_ineffective_settings(client, monkeypatch):
    client.base_url='http://127.0.0.1:8000'
    monkeypatch.setenv('GM_MODEL', 'environment-model')
    assert (await client.put('/gm/settings',json=BODY)).status_code==409
    assert not provider.CONFIG_FILE.exists()
    assert 'model' in (await client.get('/gm/settings')).json()['environment_overrides']

@pytest.mark.asyncio
async def test_legacy_json_tools_preserve_results_and_reject_prose_or_unknown_actions(monkeypatch):
    model = provider.ToolProvider({'GM_API_KEY':'test-key', 'GM_API_URL':'https://example.invalid/v1/chat/completions',
        'GM_MODEL':'glm-4-flash', 'GM_API_STYLE':'glm'})
    tools = [{'type':'function','function':{'name':'submit_module','parameters':{'type':'object'}}}]
    content = json.dumps({'tool':'submit_module','arguments':{'document':'{}'}})
    messages = [{'role':'assistant','tool_calls':[{'function':{'name':'submit_module','arguments':'{"document":"{}"}'}}]},
        {'role':'tool','content':'invalid reference','tool_call_id':'old-call'}]
    async def post(self, url, **kwargs):
        payload = kwargs['json']
        assert 'tools' not in payload and 'thinking' not in payload
        assert payload['response_format'] == {'type':'json_object'}
        assert payload['max_tokens'] == 16384
        assert 'invalid reference' in payload['messages'][2]['content']
        assert 'respond' not in payload['messages'][0]['content']
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':content}}]})
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    name, args, native, _ = await model.complete(messages,tools,1,max_tokens=16384)
    assert name == 'submit_module' and args == {'document':'{}'}
    assert native['tool_calls'][0]['id']
    for bad in ['操作完成。', '{"tool":"run_code","arguments":{}}', '{"tool":"submit_module","arguments":{},"executed":true}']:
        content = bad
        with pytest.raises(provider.ModelUnavailable):
            await model.complete(messages,tools,1,max_tokens=16384)

@pytest.mark.asyncio
async def test_structured_generation_accepts_only_the_requested_document_envelope(monkeypatch):
    model = provider.ToolProvider({'GM_API_KEY':'test-key','GM_API_URL':'https://example.invalid/v1/chat/completions',
        'GM_MODEL':'glm-4-flash','GM_API_STYLE':'glm'})
    schema = {'type':'object','properties':{'document':{'type':'object'},'assumptions':{'type':'array'},'questions':{'type':'array'}},
        'required':['document','assumptions','questions'],'additionalProperties':False}
    tools = [{'type':'function','function':{'name':'submit_module','parameters':schema}}]
    envelope = {'document':{'name':'纸灯'},'assumptions':[],'questions':[]}
    async def post(self, url, **kwargs):
        payload=kwargs['json']
        assert payload['response_format']=={'type':'json_object'} and 'tools' not in payload
        assert 'test-key' not in json.dumps(payload)
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':json.dumps(envelope)}}]})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    name,args,_,_=await model.complete([],tools,1,json_arguments=True)
    assert name=='submit_module' and args['document']=={'name':'纸灯'}
    envelope['execute']='arbitrary operation'
    with pytest.raises(provider.ModelUnavailable):await model.complete([],tools,1,json_arguments=True)

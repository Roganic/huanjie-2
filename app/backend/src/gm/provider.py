"""Small Chat Completions tool adapter; no provider keys enter game state or logs."""
import json
import os
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

CONFIG_FILE = Path(__file__).resolve().parents[2] / '.env.gm'


ERRORS = {'authentication': '密钥无效或已过期，请更换密钥。', 'permission': '没有调用权限，请核对业务空间和模型权限。',
          'budget_exhausted': '本轮模型预算已用完，已暂停 AI。',
          'pricing_unknown': '该模型尚未设置计费标准，已暂停调用。',
          'budget_request_size': '本次内容超出模型预算保护范围，请缩短内容。',
          'budget_configuration': '模型预算配置无效，已暂停调用。',
          'not_activated': '模型服务返回未开通或无使用资格，请核对服务账户的开通状态。',
          'model_or_url': '找不到模型或接口，请核对模型名称和完整地址。', 'rate_limit': '服务限流或额度不足，请检查控制台后稍后再试。',
          'balance': '账户余额不足，请检查服务账户。', 'timeout': '模型响应超时，请稍后重试。',
          'provider_error': '连接或工具格式验证失败，请核对接口地址、模型及网络。'}

def configuration():
    values = {}
    if CONFIG_FILE.is_file():
        for line in CONFIG_FILE.read_text().splitlines():
            key, separator, value = line.strip().partition('=')
            if separator and key.startswith('GM_'):
                values[key] = value.strip().strip('\"\'')
    values.update({k: v for k, v in os.environ.items() if k.startswith('GM_')})
    return values


class ModelUnavailable(Exception):
    def __init__(self, code, *, usage=None):
        super().__init__(code)
        self.usage = usage or {}


def completion_data(response):
    """Normalize an authoring stream without exposing partial drafts or reasoning."""
    if 'text/event-stream' not in response.headers.get('content-type', ''):
        return response.json()
    if len(response.content) > 2_000_000:
        raise ValueError('model response too large')
    calls, prose, usage = {}, [], None
    finished = False
    for line in response.text.splitlines():
        if not line.startswith('data:'):
            continue
        raw = line[5:].strip()
        if raw == '[DONE]':
            finished = True
            continue
        part = json.loads(raw)
        if part.get('usage'):
            usage = part['usage']
        for choice in part.get('choices', []):
            if choice.get('index', 0) != 0:
                raise ValueError('one completion required')
            if choice.get('finish_reason') == 'length':
                raise ValueError('incomplete model document')
            delta = choice.get('delta', {})
            if delta.get('content'):
                prose.append(delta['content'])
            for fragment in delta.get('tool_calls', []):
                index = fragment.get('index', 0)
                call = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                if fragment.get('id'): call['id'] = fragment['id']
                if fragment.get('type'): call['type'] = fragment['type']
                for field in ('name', 'arguments'):
                    call['function'][field] += fragment.get('function', {}).get(field) or ''
    if not finished:
        raise ValueError('incomplete model stream')
    return {'choices': [{'message': {'content': ''.join(prose), 'tool_calls': [calls[key] for key in sorted(calls)]}}], 'usage': usage}


class ToolProvider:
    def __init__(self, config=None):
        config = configuration() if config is None else config
        self.config = config
        self.key = config.get('GM_API_KEY', '')
        self.url = config.get('GM_API_URL', '')
        self.model = config.get('GM_MODEL', '')
        self.style = config.get('GM_API_STYLE', 'standard')
        self.enabled = config.get('GM_ENABLED', 'true').lower() not in ('false', '0', 'off')
        parsed = urlparse(self.url)
        self.ready = bool(self.enabled and self.key and self.model and parsed.hostname and
                          (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')))

    async def complete(self, messages, tools, timeout, *, max_tokens=800, json_arguments=False):
        if not self.ready:
            raise ModelUnavailable('not_configured')
        consumed = {}
        try:
            payload = {'model': self.model, 'messages': messages, 'tools': tools,
                       'tool_choice': 'required', 'parallel_tool_calls': False, 'max_tokens': max_tokens}
            if len(tools) == 1 and tools[0]['function']['name'] in ('submit_module', 'revise_module'):
                payload['temperature'] = 0.1
            # Disable expensive thinking for the documented compatible providers.
            if self.style == 'qwen':
                payload['enable_thinking'] = False
                if self.model in ('qwen3.7-plus', 'qwen3.8-max') and len(tools) == 1 and tools[0]['function']['name'] in ('submit_module', 'revise_module'):
                    payload.update(enable_thinking=True, thinking_budget=4096, tool_choice='auto')
                    payload.update(stream=True, tool_stream=True, stream_options={'include_usage': True})
            elif self.style in ('deepseek', 'kimi', 'glm'):
                payload['thinking'] = {'type': 'disabled'}
            if self.style == 'glm':
                # Planning/translation should be stable; prose may vary within
                # the settled facts. Do not inherit the provider's creative default.
                payload['temperature'] = 0.5 if len(tools) == 1 and tools[0]['function']['name'] == 'respond' else 0.1
                # BigModel only documents auto; still require one valid tool below.
                payload['tool_choice'] = 'auto'
                payload.pop('parallel_tool_calls')
                if self.model in ('glm-4-flash', 'glm-4-flash-250414'):
                    payload.pop('thinking', None)  # Legacy Flash has no thinking mode.
            json_tools = not json_arguments and self.style == 'glm' and self.model in (
                'glm-4-flash', 'glm-4-flash-250414', 'glm-4.5-flash', 'glm-4.7-flash', 'glm-4.6v-flash')
            if json_tools:
                # Flash endpoints may ignore native tool_choice=auto. Translate a strict JSON
                # envelope into the same validated tool protocol; prose is still rejected.
                payload.pop('tools')
                payload.pop('tool_choice')
                payload['response_format'] = {'type': 'json_object'}
                encoded = []
                for message in messages:
                    role, content = message['role'], message.get('content') or ''
                    if role == 'tool': role, content = 'user', '工具实际返回的数据：' + content
                    if message.get('tool_calls'):
                        call = message['tool_calls'][0]['function']
                        content = json.dumps({'tool': call['name'], 'arguments': json.loads(call['arguments'])}, ensure_ascii=False)
                    encoded.append({'role': role, 'content': content})
                contract = '你必须且只能返回一个 JSON 对象，格式 {"tool":"工具名","arguments":{参数}}。不能直接回答文字。只选择下列一个工具，不增加字段：' + json.dumps(tools, ensure_ascii=False)
                payload['messages'] = [{'role': 'system', 'content': contract}, *encoded]
            if json_arguments:
                if len(tools) != 1:
                    raise ValueError('structured generation requires one schema')
                payload.pop('tools', None)
                payload.pop('tool_choice', None)
                payload.pop('parallel_tool_calls', None)
                payload['response_format'] = {'type': 'json_object'}
                payload['temperature'] = 0.1
                contract = '只输出一个 JSON 对象，字段直接遵循以下 Schema，不包裹工具名称，不用 Markdown：' + json.dumps(tools[0]['function']['parameters'], ensure_ascii=False)
                payload['messages'] = [{'role': 'system', 'content': contract}, *messages]
            # Compatible endpoints differ in how they handle repeated system
            # roles. Send one policy block, preserving all instructions in order.
            systems = [m.get('content') or '' for m in payload['messages'] if m['role'] == 'system']
            if systems:
                payload['messages'] = [{'role': 'system', 'content': '\n\n'.join(systems)},
                    *[m for m in payload['messages'] if m['role'] != 'system']]
            # Browser engine requests are metered by the authenticated server.
            # This is a runtime check, not a client-controlled configuration flag.
            reservation = None
            if sys.platform != 'emscripten':
                from . import budget
                try:
                    budget.validate_endpoint(self.model, self.url)
                    reservation = budget.reserve(payload, self.config)
                except budget.BudgetError as exc:
                    raise ModelUnavailable(str(exc)) from None
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                response = await client.post(self.url, headers={'Authorization': f'Bearer {self.key}'}, json=payload)
                response.raise_for_status()
                data = completion_data(response)
            if reservation:
                budget.settle(reservation, data.get('usage'))
            usage = data.get('usage') or {}
            consumed = {'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens')}
            message = data['choices'][0]['message']
            if json_arguments:
                args = json.loads(message.get('content') or '')
                schema = tools[0]['function']['parameters']
                if not isinstance(args, dict) or not set(schema.get('required', [])) <= set(args) or set(args) - set(schema.get('properties', {})):
                    raise ValueError('invalid structured document')
                message = {'tool_calls': [{'id': 'call-' + uuid.uuid4().hex, 'type': 'function',
                    'function': {'name': tools[0]['function']['name'], 'arguments': json.dumps(args, ensure_ascii=False)}}]}
            if json_tools:
                envelope = json.loads(message.get('content') or '')
                if not isinstance(envelope, dict) or set(envelope) != {'tool', 'arguments'} or not isinstance(envelope['arguments'], dict) or envelope['tool'] not in {t['function']['name'] for t in tools}:
                    raise ValueError('invalid tool envelope')
                message = {'tool_calls': [{'id': 'call-' + uuid.uuid4().hex, 'type': 'function',
                    'function': {'name': envelope['tool'], 'arguments': json.dumps(envelope['arguments'], ensure_ascii=False)}}]}
            # Reasoning-mode providers cannot force a tool choice. Authoring
            # has exactly one non-executable document schema, so a direct JSON
            # document may enter the same validation path. Gameplay never uses
            # this adapter: prose cannot become an action.
            if not message.get('tool_calls') and len(tools) == 1 and tools[0]['function']['name'] in ('submit_module', 'revise_module'):
                content = (message.get('content') or '').strip()
                if content.startswith('```json\n') and content.endswith('```'):
                    content = content[8:-3].strip()
                args = json.loads(content)
                schema = tools[0]['function']['parameters']
                if not isinstance(args, dict) or not set(schema.get('required', [])) <= set(args) or set(args) - set(schema.get('properties', {})):
                    raise ValueError('invalid authoring document envelope')
                message = {'tool_calls': [{'id': 'call-' + uuid.uuid4().hex, 'type': 'function',
                    'function': {'name': tools[0]['function']['name'], 'arguments': json.dumps(args, ensure_ascii=False)}}]}
            calls = message.get('tool_calls', [])
            if len(calls) != 1 or calls[0].get('type') != 'function':
                raise ValueError('one tool required')
            call = calls[0]
            if not isinstance(call.get('id'), str) or not call['id']:
                raise ValueError('missing tool call id')
            args = json.loads(call['function']['arguments'])
            if not isinstance(args, dict):
                raise ValueError('invalid arguments')
            return call['function']['name'], args, {'role': 'assistant', 'content': None, 'tool_calls': calls}, consumed
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            reason = {401: 'authentication', 403: 'permission', 404: 'model_or_url',
                      429: 'rate_limit', 402: 'balance'}.get(code, 'provider_error')
            try:
                body = exc.response.json()
                error = body.get('error', body) if isinstance(body, dict) else {}
                if isinstance(error, dict) and error.get('code') == 'AccessDenied.Unpurchased':
                    reason = 'not_activated'
                if isinstance(error, dict) and error.get('code') in ERRORS:
                    reason = error['code']
            except ValueError:
                pass
            raise ModelUnavailable(reason) from None
        except httpx.TimeoutException:
            raise ModelUnavailable('timeout') from None
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            # Never include provider response bodies, URLs, headers or keys in client errors.
            raise ModelUnavailable('provider_error', usage=consumed) from exc


def status():
    provider = ToolProvider()
    return {'configured': provider.ready, 'mode': 'ai' if provider.ready else 'fixed',
            'label': 'AI 主持已配置' if provider.ready else '固定主持 · AI 未配置',
            'limits': {'model_calls': 4, 'read_tools': 2, 'actions': 1, 'timeout_seconds': 35}}

"""Local model administration. Secrets never appear in a response or validation error."""
import ipaddress
import os
import tempfile
import threading
import time
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from . import provider
from .host import ReplyArgs, tool_definitions

router = APIRouter(prefix='/gm', tags=['gm-settings'])
LOCK = threading.RLock()
FIELDS = {'enabled': 'GM_ENABLED', 'style': 'GM_API_STYLE', 'url': 'GM_API_URL', 'model': 'GM_MODEL', 'authoring_model': 'GM_AUTHORING_MODEL', 'api_key': 'GM_API_KEY'}
ERRORS = provider.ERRORS


def local_request(request):
    # Configuration belongs to the local operator, not every player who can reach the game API.
    host = request.url.hostname
    peer = request.client.host if request.client else ''
    try:
        loopback = ipaddress.ip_address(peer).is_loopback
    except ValueError:
        loopback = False
    origin = urlparse(request.headers.get('origin', ''))
    if not loopback or host not in ('localhost', '127.0.0.1', '::1') or (origin.geturl() and
            (origin.scheme not in ('http', 'https') or origin.hostname not in ('localhost', '127.0.0.1', '::1'))):
        raise HTTPException(403, '模型设置只允许在本机页面访问。')


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: bool = True
    style: str = Field(max_length=20)
    url: str = Field(max_length=1000)
    model: str = Field(max_length=150)
    authoring_model: str = Field(default='', max_length=150)
    api_key: str = Field(default='', max_length=1000)


def public_settings():
    config = provider.configuration()
    return {'enabled': config.get('GM_ENABLED', 'true').lower() not in ('false', 'off', '0'),
            'managed': os.getenv('SESSION_DURABLE') == 'true',
            'style': config.get('GM_API_STYLE', 'standard'), 'url': config.get('GM_API_URL', ''),
            'model': config.get('GM_MODEL', ''), 'has_key': bool(config.get('GM_API_KEY')),
            'authoring_model': config.get('GM_AUTHORING_MODEL', ''),
            'environment_overrides': [name for name, key in FIELDS.items() if key in os.environ]}


async def validated(request):
    local_request(request)
    try:
        data = Settings.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(400, '设置格式无效，请检查输入。') from None
    if any('\n' in v or '\r' in v or '\x00' in v for v in (data.style, data.url, data.model, data.authoring_model, data.api_key)):
        raise HTTPException(400, '设置不能包含换行或控制字符。')
    if data.style not in ('standard', 'qwen', 'deepseek', 'kimi', 'glm'):
        raise HTTPException(400, '请选择支持的接口类型。')
    data.url = data.url.strip().rstrip('/')
    data.model = data.model.strip()
    data.authoring_model = data.authoring_model.strip()
    data.api_key = data.api_key.strip()
    try:
        parsed = urlparse(data.url)
    except ValueError:
        raise HTTPException(400, '接口地址格式无效。') from None
    if data.url and (not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or
                    not (parsed.scheme == 'https' or parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'))):
        raise HTTPException(400, '请使用 HTTPS 地址；本机模型可使用 HTTP。地址不能含密钥或查询参数。')
    if data.url.endswith('/v1'):
        data.url += '/chat/completions'
    if data.url and not data.url.endswith('/chat/completions'):
        raise HTTPException(400, '请填写 OpenAI 兼容地址，结尾为 /v1 或 /chat/completions。')
    current = provider.configuration()
    if not data.api_key and data.url != current.get('GM_API_URL', '') and current.get('GM_API_KEY'):
        raise HTTPException(400, '更换接口地址时请同时填写对应密钥，避免将原密钥发送给新服务。')
    config = {key: str(getattr(data, name)).lower() if name == 'enabled' else getattr(data, name) for name, key in FIELDS.items()}
    config['GM_API_KEY'] = data.api_key or current.get('GM_API_KEY', '')
    if 'GM_BUDGET_YUAN' in current:
        config['GM_BUDGET_YUAN'] = current['GM_BUDGET_YUAN']
    if data.enabled and not all(config[k] for k in ('GM_API_KEY', 'GM_API_URL', 'GM_MODEL')):
        raise HTTPException(400, '启用 AI 前请填写地址、模型和密钥。')
    return config


@router.get('/settings')
def read_settings(request: Request):
    local_request(request)
    return public_settings()


@router.get('/budget')
def read_budget(request: Request):
    local_request(request)
    if os.getenv('SESSION_DURABLE') == 'true':
        return {'managed': True}
    from .budget import summary
    return summary()


@router.put('/settings')
async def save_settings(request: Request):
    config = await validated(request)
    with LOCK:
        # Saving a model must not erase the operator's spending limit.
        current = provider.configuration()
        if 'GM_BUDGET_YUAN' in current:
            config['GM_BUDGET_YUAN'] = current['GM_BUDGET_YUAN']
        if any(key in os.environ for key in FIELDS.values()):
            raise HTTPException(409, '当前有环境变量覆盖设置，请先移除覆盖后再使用页面保存。')
        path = provider.CONFIG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix='.gm-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as out:
                out.write('# Local model settings. Never commit secrets.\n')
                out.write(''.join(f'{key}={value}\n' for key, value in config.items()))
            os.chmod(temp, 0o600)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp): os.unlink(temp)
    return {**public_settings(), 'status': provider.status()}


@router.post('/test')
async def test_connection(request: Request):
    config = await validated(request)
    config['GM_ENABLED'] = 'true'
    model = provider.ToolProvider(config)
    if not model.ready:
        raise HTTPException(400, '请先填写地址、模型和密钥。')
    started = time.monotonic()
    try:
        name, args, _, usage = await model.complete([
            {'role': 'system', 'content': '请调用 respond，用一句中文问候冒险者，不承诺任何游戏奖励。'},
            {'role': 'user', 'content': '你好。'}], tool_definitions(['respond']), 18)
        if name != 'respond': raise ValueError()
        reply = ReplyArgs.model_validate(args)
        return {'ok': True, 'message': reply.message, 'model': model.model, 'usage': usage,
                'elapsed_ms': round((time.monotonic()-started)*1000)}
    except (provider.ModelUnavailable, ValueError) as exc:
        return {'ok': False, 'message': ERRORS.get(str(exc), ERRORS['provider_error'])}

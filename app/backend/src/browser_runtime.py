"""Web Worker adapter. The same rule engine runs with cloud-owned snapshots.

Only loaded under Pyodide: no sockets, no Python threads, no service secrets.
"""
import json
import os
from pathlib import Path
import httpx
import starlette.concurrency
import starlette.routing
import fastapi.routing


async def inline(func, *args, **kwargs):
    # All calls are serialized in a dedicated worker; no UI thread is blocked.
    return func(*args, **kwargs)


starlette.concurrency.run_in_threadpool = inline
starlette.routing.run_in_threadpool = inline
fastapi.routing.run_in_threadpool = inline


class CloudModelTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        from pyodide.http import pyfetch
        from js import AbortSignal
        if str(request.url) != 'http://localhost/cloud/chat/completions':
            raise httpx.ConnectError('Only the managed model gateway is available.', request=request)
        timeout = request.extensions.get('timeout', {}).get('read') or 18
        try:
            result = await pyfetch('/api/model', method='POST', headers={'Content-Type': 'application/json'},
                body=request.content.decode(), signal=AbortSignal.timeout(int(timeout * 1000)))
            return httpx.Response(result.status, content=await result.bytes(), request=request)
        except Exception as exc:
            raise httpx.ConnectError('Model gateway unavailable.', request=request) from exc


_client = httpx.AsyncClient


class BrowserClient(_client):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('transport', CloudModelTransport())
        kwargs.setdefault('trust_env', False)
        super().__init__(*args, **kwargs)


httpx.AsyncClient = BrowserClient


def configure(model):
    os.environ.update(SESSION_STATE_DIR='/data/sessions', SESSION_DURABLE='true', SAVE_DIR='/data/saves', MODULE_DIR='/data/modules', DRAFT_DIR='/data/drafts',
        GM_ENABLED='true' if model.get('configured') else 'false', GM_API_STYLE=model.get('style', 'standard'),
        GM_MODEL=model.get('model', ''), GM_AUTHORING_MODEL=model.get('authoring_model', ''), GM_API_KEY='server-managed', GM_API_URL='http://localhost/cloud/chat/completions')


async def handle(raw):
    from .main import app
    from . import state
    request = json.loads(raw)
    headers = httpx.Headers(request.get('headers') or {})
    selection = Path('/data/profile/current.json')
    if 'x-session-id' not in headers and selection.exists():
        current = json.loads(selection.read_text()).get('session_id')
        if current and state.session_exists(current):
            headers['x-session-id'] = current
    async with _client(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 80)), base_url='http://127.0.0.1') as client:
        response = await client.request(request['method'], request['path'], headers=headers, content=request.get('body'))
    if response.is_success:
        data = response.json()
        current = data.get('session_id') if isinstance(data, dict) else None
        current = current or response.headers.get('x-session-id') or headers.get('x-session-id')
        if current and state.session_exists(current):
            selection.parent.mkdir(exist_ok=True)
            selection.write_text(json.dumps({'session_id': current}))
    return json.dumps({'status': response.status_code, 'body': response.text, 'headers': dict(response.headers)})


def snapshot():
    files = {}
    for path in sorted(Path('/data').rglob('*.json')):
        files[str(path.relative_to('/data'))] = path.read_text()
    return json.dumps(files, ensure_ascii=False, separators=(',', ':'))

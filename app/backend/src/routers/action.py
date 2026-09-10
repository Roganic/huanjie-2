"""HTTP/SSE adapters for the transport-independent game command boundary."""
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ..models.action import ActionRequest
from ..state import DEFAULT_SESSION_ID
from ..game.commands import GameCommand
from ..gm.host import handle_command
from ..gm.provider import status as gm_status

router=APIRouter(tags=['game'])


def _sse_event(event,data):
    return f'event: {event}\ndata: {json.dumps(data,ensure_ascii=False)}\n\n'


@router.post('/commands')
async def commands(command: GameCommand, request: Request):
    executed = await handle_command(request.headers.get('X-Session-Id') or DEFAULT_SESSION_ID,command)
    if 'text/event-stream' in request.headers.get('accept',''):
        raw={**executed['result'],'changes':executed['changes'],'replayed':executed['replayed']}
        async def stream():
            yield _sse_event('start',raw)
            for field in ('gm_narration','narration','narrative','scene_progression','gm_prompt'):
                if field in raw and not (field == 'narrative' and 'narration' in raw):
                    yield _sse_event('chunk',{'field':field,'delta':raw[field]})
            yield _sse_event('complete',raw)
        return StreamingResponse(stream(),media_type='text/event-stream')
    return executed


@router.get('/gm/status')
def host_status():
    return gm_status()


@router.get('/gm/history')
def host_history(request: Request):
    from .. import state
    from fastapi import HTTPException
    sid = request.headers.get('X-Session-Id')
    if not sid:
        raise HTTPException(400, '请先创建角色。')
    with state._SESSION_LOCK:
        try:
            session = state._get_session(sid, False)
        except KeyError as exc:
            raise HTTPException(404, '会话不存在或已失效。') from exc
        return {'turns': [{k: t.get(k) for k in ('id', 'player', 'reply', 'npc_id', 'scene_id', 'status', 'created_at')} for t in session.gm_turns]}


@router.get('/gm/metrics')
def host_metrics(request: Request):
    from .. import state
    from fastapi import HTTPException
    sid = request.headers.get('X-Session-Id')
    if not sid:
        raise HTTPException(400, '请先创建角色。')
    with state._SESSION_LOCK:
        try:
            turns = state._get_session(sid, False).gm_turns
        except KeyError:
            raise HTTPException(404, '会话不存在或已失效。') from None
        completed = [t for t in turns if 'elapsed_ms' in t]
        times = sorted(t['elapsed_ms'] for t in completed)
        import math
        percentile = lambda p: times[max(0, math.ceil(len(times)*p)-1)] if times else None
        return {'window': 40, 'turns': len(completed), 'calls': sum(t.get('calls', 0) for t in completed),
                'fallbacks': sum(t['status'] == 'fallback' for t in completed),
                'input_tokens': sum(u.get('input_tokens') or 0 for t in completed for u in t.get('usage', [])),
                'output_tokens': sum(u.get('output_tokens') or 0 for t in completed for u in t.get('usage', [])),
                'p50_ms': percentile(.5), 'p95_ms': percentile(.95),
                'models': list(dict.fromkeys(t.get('model', '') for t in completed))}


@router.post('/action')
async def submit_action(req: ActionRequest, request: Request):
    sid=request.headers.get('X-Session-Id') or request.query_params.get('session_id') or DEFAULT_SESSION_ID
    executed=await handle_command(sid,GameCommand(kind='text',text=req,request_id=req.request_id))
    raw={**executed['result'],'changes':executed['changes'],'replayed':executed['replayed']}
    if 'text/event-stream' not in request.headers.get('accept',''):
        return raw
    async def stream():
        yield _sse_event('start',{k:raw[k] for k in ('action_summary','resolution_type','outcome') if k in raw})
        for field in ('narration','scene_progression','gm_prompt'):
            yield _sse_event('chunk',{'field':field,'delta':raw.get(field,'')})
        yield _sse_event('complete',raw)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})

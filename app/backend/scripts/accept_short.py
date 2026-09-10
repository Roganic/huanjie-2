"""Disposable short-adventure acceptance. --ai requires real model responses."""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

runtime = Path(tempfile.mkdtemp(prefix='huanjie-short-'))
os.environ.update(SESSION_STATE_DIR=str(runtime/'sessions'), SAVE_DIR=str(runtime/'saves'), MODULE_DIR=str(runtime/'modules'))
if '--ai' not in sys.argv: os.environ['GM_ENABLED'] = 'false'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.game.commands import facts

rows = []
report = Path('/tmp/huanjie-short-ai.json' if '--ai' in sys.argv else '/tmp/huanjie-short-rules.json')
roll = [20]

async def main():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1') as client:
        source = (await client.get('/state/bootstrap')).json()['session_id']
        await client.post('/character/create', headers={'X-Session-Id': source}, json={'name':'渡灯测试者','character_class':'warrior','ability_generation':'standard_array'})
        async def start():
            r = await client.post('/modules/activate', headers={'X-Session-Id':source}, json={'module_id':'last-ferry-light'})
            assert r.status_code == 200
            return r.json()['session_id']
        async def act(sid, kind, target=None, text=None):
            s = state._get_session(sid,False)
            data = {'request_id':f'short-{len(rows)}','kind':kind,'expected_scene_id':s.scene.id}
            if target: data['target_id'] = target
            if text: data['text'] = {'scene_id':s.scene.id,'actor':s.actor.name,'intent':text,'approach':''}
            started = time.monotonic()
            response = await client.post('/commands',headers={'X-Session-Id':sid},json=data)
            assert response.status_code == 200, response.text
            r = response.json()['result']
            settled = facts(s)
            replay = await client.post('/commands',headers={'X-Session-Id':sid},json=data)
            assert replay.json()['replayed'] and facts(s) == settled
            row = {'kind':kind,'target':target,'text':text,'elapsed_ms':round((time.monotonic()-started)*1000),'result':r}
            rows.append(row);report.write_text(json.dumps({'complete':False,'rows':rows},ensure_ascii=False,indent=2))
            print(json.dumps({'step':len(rows),'kind':kind,'status':r.get('action_status'),'gm':r.get('gm')},ensure_ascii=False),flush=True)
            if '--ai' in sys.argv and kind in ('talk','text') and r.get('action_status') != 'blocked':
                assert r['gm']['mode'] in ('ai','read_only'), r
            return r
        sid = await start()
        await act(sid,'talk','cen','岑婆，告诉我怎样让渡船回来。')
        await act(sid,'move','workshop')
        r = await act(sid,'text',text='阿禾，先救人比追责更重要。我耐心解释这个道理，争取你的信任，请你交出校准图。') if '--ai' in sys.argv else await act(sid,'challenge','reassure-he')
        assert r.get('adjudication',{}).get('id')=='reassure-he', r
        assert 'calibration' in state._get_session(sid,False).content_flags
        await act(sid,'move','ferry'); await act(sid,'move','lighthouse')
        await act(sid,'challenge','align-light'); await act(sid,'move','ferry')
        await act(sid,'talk','cen','岑婆，我已经校准灯架并发出引航信号，来提交救援结果。')
        assert state._get_session(sid,False).adventure_outcome['id']=='light'
        sid = await start(); roll[0] = 1
        await act(sid,'talk','cen','我会去潮阶查看维修匣。')
        await act(sid,'move','tidal-steps'); r=await act(sid,'challenge','open-case')
        assert r['outcome']=='failure'
        s = state._get_session(sid,False)
        before = (facts(s),s.challenge_attempts,s.npc_memories)
        saved = (await client.post('/save',headers={'X-Session-Id':sid})).json()
        state._sessions.clear()
        assert (await client.post('/load',json={'save_id':saved['save_id']})).status_code==200
        s=state._get_session(sid,False)
        assert before == (facts(s),s.challenge_attempts,s.npc_memories)
        await act(sid,'challenge','restore-paper'); await act(sid,'move','ferry'); await act(sid,'move','lighthouse')
        await act(sid,'challenge','align-light'); await act(sid,'move','ferry')
        await act(sid,'talk','cen','图纸湿了，但我按刻度复原了校准信息，灯光已经发出。')
        assert s.adventure_outcome['id']=='light'
        sid=await start(); await act(sid,'talk','cen','我想用钟声帮助他们。');await act(sid,'move','lighthouse')
        await act(sid,'challenge','ring-bell');await act(sid,'move','ferry');await act(sid,'talk','cen','三短一长的钟声已经发出，渡船驶向了避风码头。')
        assert state._get_session(sid,False).adventure_outcome['id']=='bell'
        report.write_text(json.dumps({'complete':True,'ai_required':'--ai' in sys.argv,'routes':['亮灯','失败复原与读档','钟声'],'rows':rows},ensure_ascii=False,indent=2))

with patch('src.engine.dice.roll_d20',lambda:roll[0]):
    asyncio.run(main())

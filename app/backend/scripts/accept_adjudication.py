"""Opt-in live-model validation of the adjudication protocol in a disposable adventure."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true')
parser.add_argument('--output', default='/tmp/huanjie-adjudication-live.json')
args = parser.parse_args()
if not args.live:
    parser.error('Use --live to enable real model calls.')
runtime = Path(tempfile.mkdtemp(prefix='huanjie-adjudication-'))
os.environ.update(SESSION_STATE_DIR=str(runtime/'sessions'), SAVE_DIR=str(runtime/'saves'))
for key in ('KIMI_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(key, None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.game.commands import GameCommand, execute_command, facts
from src.gm.provider import ToolProvider


async def main():
    assert ToolProvider().ready
    rows = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
        sid = (await client.get('/state/bootstrap')).json()['session_id']
        headers = {'X-Session-Id': sid}
        assert (await client.post('/character/create', headers=headers, json={'name': '裁定验收', 'character_class': 'warrior', 'ability_generation': 'standard_array'})).status_code == 200
        def session(): return state._get_session(sid, False)
        async def turn(text, status):
            assert len(rows) < 12
            command = dict(kind='text', request_id=f'architecture-{len(rows)}', text=dict(scene_id=session().scene.id, actor='裁定验收', intent=text, approach=''))
            response = await client.post('/commands', headers=headers, json=command)
            assert response.status_code == 200, response.text
            raw = response.json()['result']
            rows.append(dict(player=text, status=raw.get('action_status'), facts=raw.get('narration'),
                reply=raw.get('gm_narration'), gm=raw.get('gm'), check=raw.get('check'), trace=session().gm_turns[-1].get('trace')))
            Path(args.output).write_text(json.dumps({'passed': False, 'rows': rows}, ensure_ascii=False, indent=2))
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            assert raw['action_status'] == status, rows[-1]
            before = facts(session())
            replay = await client.post('/commands', headers=headers, json=command)
            assert replay.json()['replayed'] and before == facts(session())
            return raw
        before = facts(session())
        await turn('举起手里的武器，朝老马库斯的头上砸下去', 'blocked')
        retry = await turn('再试一次', 'blocked')
        assert retry['gm']['calls'] == 0 and before == facts(session())
        assert not session().event_facts
        await turn('那我现在可以干什么？', 'read_only')
        with patch('src.engine.dice.roll_d20', return_value=20):
            r = await turn('我放下武器，诚恳解释自己的来意，试着说服老马库斯信任我', 'executed')
        assert r['check']['skill_name'] == 'persuasion' and r['check']['dc'] == 15
        assert session().relationships['tavern-keeper-01'] == 1
        await turn('再试一次', 'blocked')
        assert session().scene.time == 1
        execute_command(sid, GameCommand(kind='move', target_id='village-square-01'))
        execute_command(sid, GameCommand(kind='move', target_id='tavern-01'))
        with patch('src.engine.dice.roll_d20', return_value=1):
            r = await turn('我编造自己是远方贵族的随从，试着骗取老马库斯的信任', 'executed')
        assert r['check']['skill_name'] == 'deception' and r['outcome'] == 'failure'
        assert session().relationships['tavern-keeper-01'] == 0
        saved = (await client.post('/save', headers=headers)).json()
        snapshot = session().model_dump(mode='json')
        from src.game_state import load_game_by_id
        assert load_game_by_id(saved['save_id'])
        state._sessions.pop(sid)
        assert session().discourse == snapshot['discourse']
        assert session().event_clock.model_dump() == snapshot['event_clock']
        await turn('再试一次', 'blocked')
        await turn('问老马库斯，现在村里有什么消息？', 'executed')
        assert session().scene.time == 4
        metrics = (await client.get('/gm/metrics', headers=headers)).json()
        Path(args.output).write_text(json.dumps({'passed': True, 'dice': 'fixed validation rolls', 'metrics': metrics, 'rows': rows}, ensure_ascii=False, indent=2))
        print('PASS ' + json.dumps(metrics, ensure_ascii=False), flush=True)

asyncio.run(main())

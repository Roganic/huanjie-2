"""Measure routed interactions in a disposable adventure; --live enables real dialogue."""
import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

parser = argparse.ArgumentParser()
parser.add_argument('--live', action='store_true')
parser.add_argument('--output', default='/tmp/huanjie-interaction-acceptance.json')
args = parser.parse_args()
runtime = Path(tempfile.mkdtemp(prefix='huanjie-interaction-'))
os.environ.update(SESSION_STATE_DIR=str(runtime / 'sessions'), SAVE_DIR=str(runtime / 'saves'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.game.commands import facts
from src.game import combat_service
from src.gm import host

async def main():
    rows = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://127.0.0.1:8000') as client:
        sid = (await client.get('/state/bootstrap')).json()['session_id']
        headers = {'X-Session-Id': sid}
        await client.post('/character/create', headers=headers, json={'name': '交互性能验收', 'character_class': 'warrior', 'ability_generation': 'standard_array'})
        def session(): return state._get_session(sid, False)
        async def turn(label, **command):
            body = {**command, 'request_id': f'perf-{len(rows)}', 'expected_scene_id': session().scene.id}
            if isinstance(body.get('text'), str):
                body['text'] = {'scene_id': session().scene.id, 'actor': '交互性能验收', 'intent': body['text'], 'approach': ''}
            start = time.monotonic()
            response = await client.post('/commands', headers=headers, json=body)
            elapsed = round((time.monotonic() - start) * 1000)
            assert response.status_code == 200, response.text
            raw = response.json()['result']
            if command['kind'] not in ('text', 'talk'): assert raw['gm']['calls'] == 0
            before = facts(session())
            replay = await client.post('/commands', headers=headers, json=body)
            assert replay.json()['replayed'] and facts(session()) == before
            rows.append({'label': label, 'kind': command['kind'], 'elapsed_ms': elapsed, 'gm': raw['gm'], 'reply': raw.get('gm_narration') or raw.get('narration') or raw.get('message') or raw.get('narrative'), 'replayed_without_change': True})
            Path(args.output).write_text(json.dumps({'rows': rows, 'complete': False}, ensure_ascii=False, indent=2))
            return raw
        weapon = session().actor.equipped.weapon.id
        await turn('卸下武器', kind='unequip', target_id='weapon')
        await turn('装备武器', kind='equip', target_id=weapon)
        await turn('阅读笔记', kind='interact', target_id='veteran-advice')
        await turn('前往广场', kind='move', target_id='village-square-01')
        await turn('返回酒馆', kind='move', target_id='tavern-01')
        await turn('说服尝试', kind='challenge', target_id='social:tavern-keeper-01:persuasion')
        blocked = await turn('相同尝试受限', kind='challenge', target_id='social:tavern-keeper-01:persuasion')
        assert blocked['action_status'] == 'blocked' and blocked['feedback']['detail']
        if args.live:
            assert host.ToolProvider().ready, '模型未配置'
            talk = await turn('交谈按钮', kind='talk', target_id='tavern-keeper-01', text='与老马库斯交谈')
            assert talk['gm']['mode'] == 'ai' and talk['gm']['calls'] <= 2
            follow = await turn('自由输入追问', kind='text', text='老马库斯，你还知道关于托尔金的什么消息？')
            assert follow['gm']['mode'] == 'ai'
            move = await turn('自由输入移动', kind='text', text='前往遗忘地下城入口')
            assert session().scene.id == 'dungeon-entrance-01' and 'gm_narration' not in move
        else:
            await turn('前往入口', kind='move', target_id='dungeon-entrance-01')
        await turn('进入遭遇', kind='move', target_id='combat-encounter-01')
        await turn('防御', kind='combat', action='defend')
        for _ in range(10):
            battle = session().combat_snapshot
            if battle['status'] != 'active': break
            enemy = next(p for p in battle['participants'] if not p['is_player'] and p['hp'] > 0)
            await turn('攻击', kind='combat', action='attack', target_id=enemy['id'])
        assert session().combat_snapshot['status'] == 'victory'
        await turn('胜利结算', kind='leave', action='victory')
        before = facts(session())
        saved = (await client.post('/save', headers=headers, json={'save_name': '交互验收'})).json()
        state._sessions.clear()
        assert (await client.post('/load', json={'save_id': saved['save_id']})).status_code == 200
        assert facts(session()) == before
    direct = [r['elapsed_ms'] for r in rows if r['kind'] not in ('text', 'talk')]
    report = {'complete': True, 'rows': rows, 'direct_median_ms': statistics.median(direct), 'direct_max_ms': max(direct),
              'model_calls': sum(r['gm'].get('calls', 0) for r in rows), 'save_load_preserved': True,
              'measurement': 'Local ASGI request including persistence, excludes browser/network rendering; fixed validation dice.'}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k:v for k,v in report.items() if k != 'rows'}, ensure_ascii=False))

original = combat_service.resolve_attack_with_equipment
def attack(actor, target_ac, **kwargs):
    if actor.character_class: return original(actor, target_ac, **kwargs)
    return dict(hit=False, damage=0, attack_roll=1, total_attack=1, target_ac=target_ac, damage_rolls=[], weapon_used='验收敌人')
with patch('random.randint', lambda lo, hi: hi), patch('random.random', lambda: 0.0), patch.object(combat_service, 'roll_d20', lambda: 20), patch.object(combat_service, 'resolve_attack_with_equipment', attack):
    asyncio.run(main())

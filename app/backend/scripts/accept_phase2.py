"""Disposable real-host acceptance for Phase 2. No production saves are read or changed."""
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
runtime = Path(tempfile.mkdtemp(prefix='huanjie-phase2-'))
os.environ.update(SESSION_STATE_DIR=str(runtime/'sessions'), SAVE_DIR=str(runtime/'saves'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.game.commands import facts
from src.game import combat_service
from src.gm.host import ToolProvider

allow_fallback = '--allow-fallback' in sys.argv
output = Path('/tmp/huanjie-phase2-live.json')
recoveries=[]
rows=[]
tool_trace=[]
original_complete=ToolProvider.complete
async def traced_complete(self,*a,**kw):
    result=await original_complete(self,*a,**kw)
    tool_trace.append({'name':result[0],'arguments':result[1]})
    Path('/tmp/huanjie-phase2-tool-trace.json').write_text(json.dumps(tool_trace,ensure_ascii=False,indent=2))
    return result
ToolProvider.complete=traced_complete
roll=[20]
async def main():
    assert ToolProvider().ready, '模型未配置'
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1:8000') as client:
        source = (await client.get('/state/bootstrap')).json()['session_id']
        await client.post('/character/create',headers={'X-Session-Id':source},json={'name':'阶段二验收','character_class':'warrior','ability_generation':'standard_array'})
        async def start():
            r=await client.post('/modules/activate',headers={'X-Session-Id':source},json={'module_id':'ember-watch'})
            assert r.status_code==200, r.text
            return r.json()['session_id']
        async def turn(sid,label,kind='text',text=None,target=None,**kw):
            s=state._get_session(sid,False)
            body=dict(kind=kind,request_id=f'phase2-{len(rows)}',expected_scene_id=s.scene.id,**kw)
            if target: body['target_id']=target
            if text: body['text']=dict(scene_id=s.scene.id,actor=s.actor.name,intent=text,approach='')
            t=time.monotonic()
            r=await client.post('/commands',headers={'X-Session-Id':sid},json=body)
            assert r.status_code==200,r.text
            raw=r.json()['result']
            stable=facts(s)
            replay=await client.post('/commands',headers={'X-Session-Id':sid},json=body)
            assert replay.json()['replayed'] and facts(s)==stable
            row=dict(label=label,kind=kind,input=text,reply=raw.get('gm_narration') or raw.get('narration') or raw.get('narrative'),
                status=raw.get('action_status'),outcome=raw.get('outcome'),check=raw.get('check'),plan=raw.get('intent_plan'),
                gm=raw['gm'],elapsed_ms=round((time.monotonic()-t)*1000),scene=s.scene.id,
                trace=s.gm_turns[-1].get('trace') if kind=='text' else None)
            rows.append(row); output.write_text(json.dumps(dict(complete=False,rows=rows),ensure_ascii=False,indent=2))
            print(json.dumps({k:row[k] for k in ('label','status','gm')},ensure_ascii=False),flush=True)
            return raw
        async def ensure_goal(sid,raw,challenge,choice=None):
            if raw.get('adjudication',{}).get('id')==challenge: return raw
            assert allow_fallback and raw.get('action_status')=='blocked', raw
            recoveries.append({'challenge':challenge,'reason':raw['gm'].get('reason')})
            return await turn(sid,'明确按钮恢复 '+challenge,kind='challenge',target=challenge,**({'choice':choice} if choice else {}))
        sid=await start(); s=state._get_session(sid,False)
        before=facts(s)
        r=await turn(sid,'普通抱怨',text='伊莲，等得我烦死了。我只是抱怨一下，没想要求你做什么。')
        assert facts(s)==before and not r.get('check') and ((r.get('executed_command') or {}).get('kind')=='expression' or allow_fallback and r['action_status']=='blocked')
        r=await turn(sid,'追问刚才情绪',text='你怎么看我刚才的抱怨？')
        assert not r.get('check') and (r['gm']['mode'] in ('ai','read_only') or allow_fallback and r['action_status']=='blocked')
        r=await turn(sid,'选择鼓舞而非药水',text='伊莲，我用以前巡逻的经验说明准备方案，请你鼓舞我出发，不需要药水。')
        r=await ensure_goal(sid,r,'ember-support',{'approach_id':'experience','consequence_id':'encouragement'})
        assert r.get('adjudication',{}).get('id')=='ember-support' and 'inspired' in s.actor.conditions
        r=await turn(sid,'另一个目标核实证言',text='伊莲，我耐心解释核实消息的必要性，请你确认最后的钟声是否意味着巡逻队改道，好让我形成完整报告。')
        r=await ensure_goal(sid,r,'ember-testimony')
        assert r.get('adjudication',{}).get('id')=='ember-testimony' and 'ember-report' in s.content_flags
        r=await turn(sid,'目标完成后重试',text='再试一次')
        assert r['action_status']=='blocked'
        await turn(sid,'交付调查',kind='talk',target='ember-captain',text='伊莲，我来提交已经核实的调查结果。')
        assert s.adventure_outcome['id']=='ember-truth'
        sid=await start(); s=state._get_session(sid,False)
        await turn(sid,'开始失败路线',kind='talk',target='ember-captain',text='伊莲，请说明委托。')
        roll[0]=1
        r=await turn(sid,'证言交涉失败',text='伊莲，我试着耐心劝你核实最后的钟声，告诉我准确的改道证言。')
        r=await ensure_goal(sid,r,'ember-testimony')
        assert r.get('adjudication',{}).get('id')=='ember-testimony' and r['outcome']=='failure'
        r=await turn(sid,'失败后仍可聊天',text='伊莲，我刚才没能说服你核实证言。接下来还能从哪里查证？')
        assert not r.get('check') and (r['gm']['mode'] in ('ai','read_only') or allow_fallback and r['action_status']=='blocked')
        await turn(sid,'前往档案室',kind='move',target='ember-archive')
        r=await turn(sid,'自由调查失败',text='我仔细核对残页的页码和字迹，尝试拼出巡逻队的钟声记录。')
        r=await ensure_goal(sid,r,'ember-record')
        assert r.get('adjudication',{}).get('id')=='ember-record' and r['outcome']=='failure'
        saved=(await client.post('/save',headers={'X-Session-Id':sid})).json()
        before=(facts(s),s.npc_memories,s.challenge_attempts,s.discourse)
        state._sessions.clear()
        assert (await client.post('/load',json={'save_id':saved['save_id']})).status_code==200
        s=state._get_session(sid,False)
        assert before==(facts(s),s.npc_memories,s.challenge_attempts,s.discourse)
        r=await turn(sid,'读档后失败推进',text='那我去整理低柜的登记副本，按页码逐一核对。')
        r=await ensure_goal(sid,r,'ember-copy')
        assert r.get('adjudication',{}).get('id')=='ember-copy' and not r.get('check')
        await turn(sid,'返回广场',kind='move',target='ember-square')
        r=await turn(sid,'失败经历后的交付',kind='talk',target='ember-captain',text='伊莲，你刚才没能给我的证言，我后来从登记副本查到了。现在提交报告。')
        assert s.adventure_outcome['id']=='ember-recovered'
        sid=await start(); s=state._get_session(sid,False); roll[0]=20
        await turn(sid,'战斗路线接任务',kind='talk',target='ember-captain',text='我来处理归路上的匪徒。')
        await turn(sid,'到河岸',kind='move',target='ember-bank')
        await turn(sid,'进入两敌人遭遇',kind='move',target='ember-camp')
        assert len(s.combat_snapshot['participants'])==3
        for i in range(8):
            if s.combat_snapshot['status']!='active': break
            enemy=next(p for p in s.combat_snapshot['participants'] if not p['is_player'] and p['hp']>0)
            await turn(sid,'攻击匪徒',kind='combat',target=enemy['id'],action='attack')
        assert s.combat_snapshot['status']=='victory'
        await turn(sid,'战斗结算',kind='leave',action='victory')
        await turn(sid,'回河岸',kind='move',target='ember-bank')
        await turn(sid,'回广场',kind='move',target='ember-square')
        await turn(sid,'提交战斗结果',kind='talk',target='ember-captain',text='匪徒营地已经清理，我来报告。')
        assert s.adventure_outcome['id']=='ember-road'
    report=dict(complete=True,button_recoveries=recoveries,rows=rows,model_calls=sum(r['gm'].get('calls',0) for r in rows),
                routes=['交涉调查','失败推进与存读档','战斗'],save_load_preserved=True,measurement='隔离 ASGI + 真实配置模型；检定固定用于覆盖路线；每步验证幂等回放。')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False))

original=combat_service.resolve_attack_with_equipment
def attack(actor,target_ac,**kw):
    if actor.character_class: return original(actor,target_ac,**kw)
    return dict(hit=False,damage=0,attack_roll=1,total_attack=1,target_ac=target_ac,damage_rolls=[],weapon_used='验收敌人')
with patch('src.engine.dice.roll_d20',lambda:roll[0]),patch('random.randint',lambda lo,hi:hi),patch('random.random',lambda:0),patch.object(combat_service,'roll_d20',lambda:20),patch.object(combat_service,'resolve_attack_with_equipment',attack):
    asyncio.run(main())

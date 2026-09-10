"""Opt-in real model acceptance in disposable sessions, with fixed validation dice."""
import argparse, asyncio, json, os, sys, tempfile
from pathlib import Path
from unittest.mock import patch
p = argparse.ArgumentParser()
p.add_argument('--combat-only', action='store_true')
p.add_argument('--live', action='store_true'); p.add_argument('--output', default='/tmp/huanjie-gm-acceptance.json')
a = p.parse_args()
if not a.live: p.error('Pass --live to enable real calls; provider charges may apply.')
runtime = Path(tempfile.mkdtemp(prefix='huanjie-live-'))
os.environ.update(SESSION_STATE_DIR=str(runtime/'sessions'), SAVE_DIR=str(runtime/'saves'))
for k in ('KIMI_API_KEY','OPENAI_API_KEY'): os.environ.pop(k,None)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from httpx import AsyncClient, ASGITransport
from src.main import app
from src import state
from src.game.commands import facts
from src.game import combat_service
from src.gm.provider import ToolProvider
async def main():
 assert ToolProvider().ready, '模型未配置'
 rows=[]
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://127.0.0.1:8000') as c:
  sid=(await c.get('/state/bootstrap')).json()['session_id']; h={'X-Session-Id':sid}
  assert (await c.post('/character/create',headers=h,json={'name':'主持验收','character_class':'warrior','ability_generation':'standard_array'})).status_code==200
  def s(): return state._get_session(sid,False)
  async def turn(text,expected=None,readonly=False):
   assert len(rows)<32,'验收预算用完'
   before=facts(s()); command={'kind':'text','request_id':f'accept-{len(rows)}','text':{'scene_id':s().scene.id,'actor':'主持验收','intent':text,'approach':''}}
   r=await c.post('/commands',headers=h,json=command)
   assert r.status_code==200,f'{text}: HTTP {r.status_code}'
   raw=r.json()['result']; record=s().gm_turns[-1]
   row={'player':text,'reply':raw.get('gm_narration') or raw.get('narration'),'facts':raw.get('narration'),'gm':raw['gm'],'trace':record.get('trace'),'scene':s().scene.id,'phase':s().game_phase.value}
   rows.append(row); Path(a.output).write_text(json.dumps({'dice':'fixed validation rolls; real model','rows':rows},ensure_ascii=False,indent=2))
   print(json.dumps(row,ensure_ascii=False),flush=True)
   assert raw['gm']['mode'] in ('ai', 'read_only') or (expected and expected in record.get('trace', []) and raw['gm']['mode']=='fallback' and raw['gm']['reason']=='invalid_narrative'),raw['gm']
   if expected: assert expected in record['trace'],f"Expected {expected}, got {record['trace']}"
   if readonly: assert facts(s())==before,'询问不能执行行动'
   after=facts(s()); count=len(s().gm_turns)
   replay=await c.post('/commands',headers=h,json=command)
   assert replay.json()['replayed'] and facts(s())==after and len(s().gm_turns)==count
  if not a.combat_only:
   await turn('我现在在哪儿？有什么可以做的？',readonly=True)
   await turn('问老马库斯，最近村里有什么消息？','talk:tavern-keeper-01')
   await turn('那托尔金在哪儿？我该怎么去？',readonly=True)
   await turn('去地下城入口','move:dungeon-entrance-01')
   await turn('去地下城入口',readonly=True)
   await turn('问托尔金，地下城里发生了什么？','talk:wounded-adventurer-01')
   await turn('那除了打架，还有别的办法吗？','talk:wounded-adventurer-01')
   saved=(await c.post('/save',headers=h,json={'save_name':'AI 连续对话验收'})).json()
   snapshot=facts(s()); memory=s().gm_turns.copy(); state._sessions.clear()
   assert (await c.post('/load',json={'save_id':saved['save_id']})).status_code==200
   assert facts(s())==snapshot and s().gm_turns==memory
   await turn('你刚才说的另一种办法，先从哪里着手？','talk:wounded-adventurer-01')
   await turn('我沿着石门划痕寻找机关','interact:stone-door')
   await turn('取出巡逻记录','interact:patrol-report')
   await turn('前往村庄广场','move:village-square-01')
   await turn('去酒馆','move:tavern-01')
   await turn('告诉老马库斯巡逻记录里的危险，请他通知村民','talk:tavern-keeper-01')
   await turn('去地下城入口','move:dungeon-entrance-01')
   await turn('告诉托尔金，我已经通知村民了','talk:wounded-adventurer-01')
   assert s().adventure_outcome['id']=='warning-delivered' and s().actor.experience_points==300
   actor=s().actor.model_dump()
   await turn('问托尔金，接下来村民会安全吗？','talk:wounded-adventurer-01')
   assert s().actor.model_dump()==actor,'奖励不能重复'
  else:
   from src.game.commands import execute_command, GameCommand
   execute_command(sid, GameCommand(kind='move', target_id='dungeon-entrance-01'))
  await turn('进入地下城通道','move:combat-encounter-01')
  from routes.combat import _get_combat_state
  assert s().game_phase.value=='combat'
  assert len([p for p in _get_combat_state(sid).participants if not p.is_player and p.hp>0])==3
  await turn('举盾防御','combat:defend:self')
  while s().game_phase.value=='combat':
   target=next(p for p in _get_combat_state(sid).participants if not p.is_player and p.hp>0)
   await turn('攻击'+target.name,f'combat:attack:{target.id}')
  await turn('领取胜利结算并返回探索','leave:victory')
  assert s().game_phase.value=='exploration'
  metrics=(await c.get('/gm/metrics',headers=h)).json()
  Path(a.output).write_text(json.dumps({'passed':True,'scope':'combat' if a.combat_only else 'adventure','model':ToolProvider().model,'dice':'fixed validation rolls; real model','metrics':metrics,'rows':rows},ensure_ascii=False,indent=2))
  print('PASS '+json.dumps(metrics,ensure_ascii=False),flush=True)
original=combat_service.resolve_attack_with_equipment
def attack(actor,ac,**kwargs):
 if actor.character_class: return original(actor,ac,**kwargs)
 return dict(hit=False,damage=0,attack_roll=1,total_attack=1,target_ac=ac,damage_rolls=[],weapon_used='验收敌人')
with patch('src.engine.dice.roll_d20',return_value=20),patch('src.game.combat_service.roll_d20',return_value=20),patch('random.randint',side_effect=lambda low,high:high),patch('random.random',return_value=0.0),patch.object(combat_service,'resolve_attack_with_equipment',attack):
 asyncio.run(main())

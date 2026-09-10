import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync, readdirSync } from 'node:fs';
import worker from '../cloud/worker.mjs';
import { completionData } from '../cloud/completion.mjs';

test('authoring stream survives split Unicode and hides partial/reasoning text', async () => {
  const parts = [
    { choices: [{ index: 0, delta: { reasoning_content: 'internal', tool_calls: [{ index: 0, id: 'a', type: 'function', function: { name: 'submit_module', arguments: '{"name":' } }] } }] },
    { choices: [{ index: 0, delta: { tool_calls: [{ index: 0, function: { arguments: '"纸灯"}' } }] }, finish_reason: 'tool_calls' }] },
    { choices: [], usage: { prompt_tokens: 100, completion_tokens: 20 } },
  ];
  const raw = parts.map(p => 'data: ' + JSON.stringify(p) + '\n\n').join('');
  const stream = text => {
    const bytes = new TextEncoder().encode(text);
    return new Response(new ReadableStream({ start(controller) { for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7)); controller.close(); } }), { headers: { 'content-type': 'text/event-stream' } });
  };
  const data = await completionData(stream(raw + 'data: [DONE]\n\n'));
  assert.deepEqual(JSON.parse(data.choices[0].message.tool_calls[0].function.arguments), { name: '纸灯' });
  assert.equal(data.usage.completion_tokens, 20); assert.ok(!JSON.stringify(data).includes('internal'));
  await assert.rejects(completionData(stream(raw)), /Incomplete stream/);
});

function fixture() {
  const db = new DatabaseSync(':memory:');
  for (const file of readdirSync(new URL('../drizzle/', import.meta.url)).filter(f => f.endsWith('.sql')).sort()) db.exec(readFileSync(new URL('../drizzle/' + file, import.meta.url), 'utf8'));
  const blobs = new Map();
  const env = {
    DB: { prepare(sql) { return { bind(...params) { return { async first() { return db.prepare(sql).get(...params) ?? null; } }; } }; } },
    BUCKET: { async get(k) { return blobs.has(k) ? { json:async()=>JSON.parse(blobs.get(k)) } : null; }, async put(k,v) { blobs.set(k,v); }, async delete(k) { blobs.delete(k); } },
    GM_MODEL:'example',GM_API_URL:'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',GM_API_KEY:'test-only-secret',
  };
  async function request(user, method='GET', data, path='/api/cloud-state', origin) {
    const headers = { 'Content-Type':'application/json', ...(user?{'oai-authenticated-user-id':user}:{}), ...(origin?{Origin:origin}:{}) };
    return worker.fetch(new Request('https://game.example'+path,{method,headers,...(data?{body:JSON.stringify(data)}:{})}),env,{waitUntil: p=>p});
  }
  return {db,blobs,env,request};
}
const commit = (version, files, commit_id=crypto.randomUUID()) => ({version,files,commit_id});

test('authenticated players have separate durable state; errors never reveal credentials',async()=>{
  const f=fixture();
  assert.equal((await f.request(null)).status,401);
  assert.equal((await f.request('a','PUT',commit(0,{}),undefined,'https://other.example')).status,403);
  const files={'sessions/adventure.json':JSON.stringify({scene:'lighthouse',turn:3})};
  assert.equal((await f.request('a','PUT',commit(0,files))).status,200);
  assert.deepEqual(await (await f.request('a')).json(),{version:1,files});
  assert.deepEqual(await (await f.request('b')).json(),{version:0,files:{}});
  const config=await (await f.request('a','GET',null,'/api/model/config')).text();
  assert.ok(!config.includes('test-only-secret'));
  f.db.close();
});

test('all players share the server budget; concurrent calls and uncertain failures keep holds', async t => {
  const f = fixture();
  f.env.GM_MODEL = 'qwen3.7-plus'; f.env.GM_BUDGET_YUAN = '0.025';
  let calls = 0, release;
  const pending = new Promise(resolve => { release = resolve; });
  t.mock.method(globalThis, 'fetch', async () => {
    calls++; await pending;
    return Response.json({ choices: [], usage: { prompt_tokens: 100, completion_tokens: 10 } });
  });
  const payload = { messages: [], tools: [{ function: { name: 'respond' } }] };
  const first = f.request('a', 'POST', payload, '/api/model');
  await new Promise(resolve => setImmediate(resolve));
  const blocked = await f.request('b', 'POST', payload, '/api/model');
  assert.equal(blocked.status, 429);
  assert.equal((await blocked.json()).error.code, 'budget_exhausted');
  assert.equal(calls, 1);
  release(); assert.equal((await first).status, 200);
  assert.equal(f.db.prepare('SELECT charged FROM model_usage').get().charged, 280);
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('timeout'); });
  assert.equal((await f.request('b', 'POST', payload, '/api/model')).status, 503);
  assert.equal((await f.request('a', 'POST', payload, '/api/model')).status, 429);
  f.db.close();
});

test('browser cannot select price/model/budget, and missing usage is never free', async t => {
  const f = fixture(); f.env.GM_MODEL = 'qwen3.7-plus'; f.env.GM_BUDGET_YUAN = '0.025';
  let sent;
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    sent = JSON.parse(options.body); return Response.json({ choices: [] });
  });
  const payload = { messages: [], tools: [{ function: { name: 'respond' } }], model: 'free-model', GM_BUDGET_YUAN: 1000 };
  assert.equal((await f.request('a', 'POST', payload, '/api/model')).status, 200);
  assert.equal(sent.model, 'qwen3.7-plus');
  assert.equal(f.db.prepare('SELECT state FROM model_usage').get().state, 'reserved');
  assert.equal((await f.request('a', 'POST', payload, '/api/model')).status, 429);
  f.env.GM_BUDGET_YUAN = '26';
  assert.equal((await (await f.request('a', 'POST', payload, '/api/model')).json()).error.code, 'budget_configuration');
  f.db.close();
});

test('authoring review has the parser allowance while ordinary calls stay capped', async t => {
  const f = fixture(); f.env.GM_MODEL = 'qwen3.7-plus'; f.env.GM_API_STYLE = 'qwen'; f.env.GM_BUDGET_YUAN = '2';
  const sent = [];
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    sent.push(JSON.parse(options.body));
    return Response.json({ choices: [], usage: { prompt_tokens: 100, completion_tokens: 10 } });
  });
  for (const [name, max_tokens] of [['submit_module', 16384], ['revise_module', 8192], ['revise_module', 999999], ['respond', 999999]]) {
    assert.equal((await f.request('a', 'POST', { messages: [], tools: [{ function: { name } }], max_tokens }, '/api/model')).status, 200);
  }
  assert.deepEqual(sent.map(p => p.max_tokens), [16384, 8192, 16384, 800]);
  assert.ok(sent.slice(0, 3).every(p => p.temperature === 0.1 && p.enable_thinking === true && p.thinking_budget === 4096 && p.tool_choice === 'auto'));
  assert.equal(sent[3].enable_thinking, false);
  f.db.close();
});

test('concurrent identical retries preserve the committed blob and return the same version',async()=>{
  const f=fixture(), data=commit(0,{'saves/one.json':'{"scene":"harbor"}'});
  const responses=await Promise.all([f.request('a','PUT',data),f.request('a','PUT',data)]);
  assert.deepEqual(responses.map(r=>r.status),[200,200]);
  assert.deepEqual(await Promise.all(responses.map(r=>r.json())),[{version:1},{version:1}]);
  assert.deepEqual(await (await f.request('a')).json(),{version:1,files:data.files});
  assert.equal(f.blobs.size,1);
  assert.equal((await f.request('a','PUT',{...data,files:{}})).status,409);
  f.db.close();
});

test('competing tabs cannot overwrite the winner and missing storage halts restoration',async()=>{
  const f=fixture();
  await f.request('a','PUT',commit(0,{'sessions/a.json':'{}'}));
  const choices=[commit(1,{'sessions/a.json':'{"turn":2}'}),commit(1,{'sessions/a.json':'{"turn":9}'})];
  const responses=await Promise.all(choices.map(d=>f.request('a','PUT',d)));
  assert.deepEqual(responses.map(r=>r.status).sort(),[200,409]);
  const winner=responses.findIndex(r=>r.status===200);
  assert.deepEqual(await (await f.request('a')).json(),{version:2,files:choices[winner].files});
  assert.equal(f.blobs.size,1);
  f.blobs.clear();
  assert.equal((await f.request('a')).status,503);
  f.db.close();
});

test('invalid paths, content, and oversized bodies cannot become a snapshot',async()=>{
  const f=fixture();
  for(const files of [{'../key.json':'{}'},{'sessions/a.json':'oops'},{'sessions/a.json':{}}]) assert.equal((await f.request('a','PUT',commit(0,files))).status,400);
  assert.equal((await f.request('a','PUT',commit(0,{'saves/a.json':'x'.repeat(24*1024*1024)}))).status,413);
  assert.equal(f.blobs.size,0);
  f.db.close();
});

test('edge transport rejects redirects without forwarding secrets and selects the operator authoring model', async t => {
  const f = fixture();
  Object.assign(f.env, {GM_MODEL:'qwen3.7-plus', GM_AUTHORING_MODEL:'qwen3.8-max', GM_API_STYLE:'qwen', GM_BUDGET_YUAN:'2'});
  const sent=[];
  t.mock.method(globalThis,'fetch',async (url, options)=>{
    assert.equal(options.redirect,'manual');
    assert.equal(String(url),f.env.GM_API_URL);
    sent.push(JSON.parse(options.body));
    return new Response(null,{status:302,headers:{Location:'https://untrusted.invalid'}});
  });
  for(const name of ['respond','revise_module']) {
    const result=await f.request('a','POST',{messages:[],tools:[{function:{name}}],max_tokens:800,model:'untrusted'},'/api/model');
    assert.equal(result.status,503);
    assert.ok(!(await result.text()).includes('test-only-secret'));
  }
  assert.deepEqual(sent.map(p=>p.model),['qwen3.7-plus','qwen3.8-max']);
  assert.equal(sent[0].enable_thinking,false);
  assert.equal(sent[1].enable_thinking,true);
  f.db.close();
});

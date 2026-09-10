import test from 'node:test';
import assert from 'node:assert/strict';
import { gameFetch, pendingCommand, recoverCommand } from '../src/gameApi.ts';
const events = new EventTarget();
Object.assign(globalThis, { window: events });
const storage = new Map<string, string>();
Object.assign(globalThis, { sessionStorage: { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) } });
const api = (path: string) => `http://127.0.0.1:8000${path}`;
const init = (sid: string) => ({ method: 'POST', headers: { 'X-Session-Id': sid, Accept: 'text/event-stream' }, body: JSON.stringify({ target_scene_id: 'entrance' }) });
const envelope = { result: { narration: '抵达入口', gm_narration: '托尔金就在门旁。' }, state: { scene: { id: 'entrance' } }, changes: [], replayed: false };

test('uncertain delivery blocks new commands and recovers with the exact original request', async () => {
  const bodies: string[] = [];
  globalThis.fetch = async (_url, options) => {
    bodies.push(String(options?.body));
    if (bodies.length === 1) throw new TypeError('connection lost after commit');
    return new Response(JSON.stringify({ ...envelope, replayed: true }));
  };
  await assert.rejects(gameFetch(api, '/map/move', init('recover')), /恢复上次结果/);
  const pending = pendingCommand('recover');
  assert.ok(pending?.uncertain);
  await assert.rejects(gameFetch(api, '/map/move', init('recover')), /先恢复/);
  assert.equal(bodies.length, 1);
  const r = await recoverCommand(api, 'recover');
  assert.equal((await r!.json()).replayed, true);
  assert.equal(bodies[0], bodies[1]);
  assert.equal(pendingCommand('recover'), null);
});

test('incomplete JSON preserves recovery and completed prose stays structured', async () => {
  globalThis.fetch = async () => new Response('{');
  await assert.rejects(gameFetch(api, '/map/move', init('partial')));
  assert.ok(pendingCommand('partial')?.uncertain);
  globalThis.fetch = async () => new Response(JSON.stringify(envelope));
  await recoverCommand(api, 'partial');
  const r = await gameFetch(api, '/map/move', init('complete'));
  const result = await r.json();
  assert.equal(result.gm_narration, '托尔金就在门旁。');
  assert.equal(result.narration, '抵达入口');
  assert.equal(pendingCommand('complete'), null);
});

test('definitive permission failure clears pending, server failure retains it, reload can recover persisted IDs', async () => {
  globalThis.fetch = async () => new Response('{"detail":"场景已变化"}', { status: 409 });
  assert.equal((await gameFetch(api, '/map/move', init('denied'))).status, 409);
  assert.equal(pendingCommand('denied'), null);
  globalThis.fetch = async () => new Response('failed', { status: 500 });
  await assert.rejects(gameFetch(api, '/map/move', init('server-error')));
  assert.ok(pendingCommand('server-error'));
  storage.set('huanjie-pending:reload', JSON.stringify({ command: { kind: 'move', target_id: 'entrance', request_id: 'saved-original' }, started: Date.now(), uncertain: false }));
  assert.ok(pendingCommand('reload')?.uncertain);
  globalThis.fetch = async (_url, options) => {
    assert.equal(JSON.parse(String(options?.body)).request_id, 'saved-original');
    return new Response(JSON.stringify(envelope));
  };
  await recoverCommand(api, 'reload');
  assert.equal(pendingCommand('reload'), null);
});


test('talk and authored interaction controls carry their exact target and original input', async () => {
  const bodies: Record<string, unknown>[] = [];
  globalThis.fetch = async (_url, options) => { bodies.push(JSON.parse(String(options?.body))); return new Response(JSON.stringify(envelope)); };
  await gameFetch(api, '/talk', { ...init('talk'), body: JSON.stringify({ npc_id: 'marcus', scene_id: 'tavern', actor: 'hero', intent: '与老马库斯交谈' }) });
  assert.equal(bodies[0].kind, 'talk');
  assert.equal(bodies[0].target_id, 'marcus');
  assert.equal(bodies[0].expected_scene_id, 'tavern');
  assert.equal((bodies[0].text as { intent: string }).intent, '与老马库斯交谈');
  await gameFetch(api, '/interact', { ...init('interact'), body: JSON.stringify({ interaction_id: 'stone-door', scene_id: 'entrance', actor: 'hero', intent: '调查石门' }) });
  assert.equal(bodies[1].kind, 'interact');
  assert.equal(bodies[1].target_id, 'stone-door');
  await gameFetch(api, '/challenge', { ...init('choice'), body: JSON.stringify({ challenge_id: 'support', scene_id: 'square', choice: { approach_id: 'experience', consequence_id: 'encouragement' } }) });
  assert.deepEqual(bodies[2].choice, { approach_id: 'experience', consequence_id: 'encouragement' });
  assert.equal(bodies[2].target_id, 'support');
});

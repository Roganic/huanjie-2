/** One durable request ID per player action, shared by every game control. */
export type PendingCommand = { command: Record<string, unknown>; started: number; uncertain: boolean };
const active = new Set<string>();
const memory = new Map<string, PendingCommand>();
const storageKey = (sid: string) => `huanjie-pending:${sid}`;
export function pendingCommand(sid: string): PendingCommand | null {
  let value = memory.get(sid);
  if (!value) {
    try { const stored = sessionStorage.getItem(storageKey(sid)); if (stored) value = JSON.parse(stored); } catch { /* In-memory recovery remains available. */ }
  }
  return value ? { ...value, uncertain: value.uncertain || !active.has(sid) } : null;
}
function remember(sid: string, value: PendingCommand | null) {
  if (value) memory.set(sid, value); else memory.delete(sid);
  try { if (value) sessionStorage.setItem(storageKey(sid), JSON.stringify(value)); else sessionStorage.removeItem(storageKey(sid)); } catch { /* Storage may be full or unavailable. */ }
  window.dispatchEvent(new Event('huanjie-command'));
}
async function dispatch(apiUrl: (path: string) => string, sid: string, pending: PendingCommand) {
  active.add(sid); remember(sid, { ...pending, started: Date.now(), uncertain: false });
  try {
    const response = await fetch(apiUrl('/commands'), {
      method: 'POST', headers: { 'Content-Type': 'application/json', ...(sid ? { 'X-Session-Id': sid } : {}) },
      body: JSON.stringify(pending.command), signal: AbortSignal.timeout(45_000),
    });
    if (!response.ok) {
      // A server error may happen after commitment; keep the original ID for recovery.
      if (response.status >= 500) throw new Error('暂时未取回行动结果，请恢复上次结果后再继续。');
      remember(sid, null);
      return response;
    }
    const envelope = await response.json();
    if (!envelope.result || !envelope.state) throw new Error('行动结果不完整，请恢复上次结果。');
    remember(sid, null);
    return new Response(JSON.stringify(envelope), { headers: { 'Content-Type': 'application/json' } });
  } catch {
    remember(sid, { ...pending, uncertain: true });
    throw new Error('连接中断，行动可能已保存。点击“恢复上次结果”确认，避免重复执行。');
  } finally { active.delete(sid); window.dispatchEvent(new Event('huanjie-command')); }
}
export async function recoverCommand(apiUrl: (path: string) => string, sid: string) {
  const pending = pendingCommand(sid);
  if (!pending || active.has(sid)) return null;
  return dispatch(apiUrl, sid, pending);
}
export async function gameFetch(apiUrl: (path: string) => string, path: string, init: RequestInit): Promise<Response> {
  const body = JSON.parse(String(init.body ?? '{}'));
  const headers = new Headers(init.headers);
  const sid = headers.get('X-Session-Id') ?? '';
  if (pendingCommand(sid)) throw new Error('请先恢复上次行动结果，再进行新的行动。');
  const kinds: Record<string, string> = { '/map/move': 'move', '/inventory/pickup': 'pickup', '/inventory/equip': 'equip', '/inventory/unequip': 'unequip', '/inventory/use': 'use', '/character/rest': 'rest', '/combat/start': 'attack', '/combat/action': 'combat', '/combat/end': 'leave', '/action': 'text', '/challenge': 'challenge', '/talk': 'talk', '/interact': 'interact' };
  if (!kinds[path]) throw new Error('未知游戏操作');
  const command = { kind: kinds[path], request_id: crypto.randomUUID(),
    ...(path === '/action' ? { text: body, expected_scene_id: body.scene_id } : {
      ...(['/challenge', '/talk', '/interact'].includes(path) ? { expected_scene_id: body.scene_id } : {}),
      ...(path === '/challenge' && body.choice ? { choice: body.choice } : {}),
      ...(['/talk', '/interact', '/challenge'].includes(path) && body.intent ? { text: { scene_id: body.scene_id, actor: body.actor, intent: body.intent, approach: body.approach ?? '' } } : {}),
      target_id: body.npc_id ?? body.interaction_id ?? body.challenge_id ?? body.target_scene_id ?? body.item_id ?? body.slot ?? body.target_id,
      action: body.kind ?? body.action_type ?? body.reason,
    }) };
  const response = await dispatch(apiUrl, sid, { command, started: Date.now(), uncertain: false });
  if (!response.ok) return response;
  const envelope = await response.json();
  const raw = { ...envelope.result, changes: envelope.changes, replayed: envelope.replayed };
  return new Response(JSON.stringify(raw), { headers: { 'Content-Type': 'application/json' } });
}
export async function gameError(response: Response): Promise<string> {
  const text = await response.text();
  try { const body = JSON.parse(text); if (typeof body.detail === 'string') return body.detail; } catch { /* Plain-text response. */ }
  return '操作失败，请刷新状态后重试。';
}

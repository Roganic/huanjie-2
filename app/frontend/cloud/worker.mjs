/** Cloud boundary: authenticated snapshots and server-held model credentials. */
import { reserveModel, settleModel } from './budget.mjs';
import { completionData } from './completion.mjs';
const json = (value, status = 200) => Response.json(value, { status, headers: { 'Cache-Control': 'no-store' } });
const hash = async value => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(v => v.toString(16).padStart(2, '0')).join('');
const fail = (message, status = 400) => Object.assign(new Error(message), { status });
async function body(request, limit) {
  if (!request.headers.get('content-type')?.startsWith('application/json')) throw fail('请提交 JSON 内容。', 415);
  const reader = request.body?.getReader();
  if (!reader) throw fail('内容为空。');
  let size = 0; const parts = [];
  while (true) {
    const { value, done } = await reader.read(); if (done) break;
    size += value.byteLength;
    if (size > limit) { await reader.cancel(); throw fail('内容过大。', 413); }
    parts.push(value);
  }
  const all = new Uint8Array(size); let offset = 0;
  for (const part of parts) { all.set(part, offset); offset += part.length; }
  try { return JSON.parse(new TextDecoder().decode(all)); } catch { throw fail('内容不是有效 JSON。'); }
}
function config(env) { return { configured: Boolean(env.GM_API_KEY && env.GM_API_URL && env.GM_MODEL), model: env.GM_MODEL ?? '', authoring_model: env.GM_AUTHORING_MODEL ?? '', style: env.GM_API_STYLE ?? 'standard' }; }
async function snapshots(request, env, user, ctx) {
  const owner = await hash(user);
  const row = await env.DB.prepare('SELECT version, object_key, commit_id, digest FROM runtime_snapshots WHERE owner = ?').bind(owner).first();
  if (request.method === 'GET') {
    if (!row) return json({ version: 0, files: {} });
    const stored = await env.BUCKET.get(row.object_key);
    if (!stored) throw fail('云端存档暂时无法读取，已停止加载以保护进度。', 503);
    return json({ version: row.version, files: await stored.json() });
  }
  if (request.method !== 'PUT') throw fail('不支持的操作。', 405);
  const data = await body(request, 24 * 1024 * 1024);
  if (!Number.isSafeInteger(data.version) || data.version < 0 || !/^[0-9a-f-]{36}$/.test(data.commit_id ?? '') || !data.files || Array.isArray(data.files) || typeof data.files !== 'object') throw fail('存档格式无效。');
  const entries = Object.entries(data.files);
  if (entries.length > 2000) throw fail('存档数量过多。', 413);
  for (const [path, content] of entries) {
    if (!(path === 'profile/current.json' || /^(sessions|saves|modules|drafts)\/[a-zA-Z0-9_-]+\.json$/.test(path)) || typeof content !== 'string') throw fail('存档文件路径无效。');
    try { JSON.parse(content); } catch { throw fail('存档文件内容无效。'); }
  }
  const serialized = JSON.stringify(data.files), digest = await hash(serialized);
  if (row?.commit_id === data.commit_id) {
    if (row.digest !== digest) throw fail('相同保存编号的内容不一致。', 409);
    return json({ version: row.version });
  }
  if ((row?.version ?? 0) !== data.version) throw fail('另一页面已更新冒险。请刷新读取最新进度，避免覆盖。', 409);
  // Each attempt owns its object: a concurrent retry must never overwrite or
  // delete the blob that another attempt has already committed.
  const key = `runtime/${owner}/${data.commit_id}-${crypto.randomUUID()}.json`;
  await env.BUCKET.put(key, serialized, { httpMetadata: { contentType: 'application/json' } });
  const next = row
    ? await env.DB.prepare('UPDATE runtime_snapshots SET version = version + 1, object_key = ?, commit_id = ?, digest = ?, updated_at = ? WHERE owner = ? AND version = ? RETURNING version').bind(key, data.commit_id, digest, Date.now(), owner, data.version).first()
    : await env.DB.prepare('INSERT OR IGNORE INTO runtime_snapshots (owner, version, object_key, commit_id, digest, updated_at) VALUES (?, 1, ?, ?, ?, ?) RETURNING version').bind(owner, key, data.commit_id, digest, Date.now()).first();
  if (!next) {
    await env.BUCKET.delete(key);
    const winner = await env.DB.prepare('SELECT version, commit_id, digest FROM runtime_snapshots WHERE owner = ?').bind(owner).first();
    if (winner?.commit_id === data.commit_id && winner.digest === digest) return json({ version: winner.version });
    throw fail('另一页面先保存了进度，请刷新后继续。', 409);
  }
  if (row?.object_key) ctx.waitUntil(env.BUCKET.delete(row.object_key));
  return json({ version: next.version });
}
async function model(request, env) {
  if (request.method !== 'POST') throw fail('不支持的操作。', 405);
  if (!config(env).configured) throw fail('模型尚未配置。', 503);
  const payload = await body(request, 400000);
  const jsonTools = !payload.tools && payload.response_format?.type === 'json_object';
  if (!Array.isArray(payload.messages) || payload.messages.length > 40 || (!jsonTools && (!Array.isArray(payload.tools) || !payload.tools.length || payload.tools.length > 20))) throw fail('模型请求格式无效。');
  const parser = jsonTools ? payload.max_tokens > 800 : payload.tools.length === 1 && ['submit_module', 'revise_module'].includes(payload.tools[0]?.function?.name);
  const limit = parser ? 16384 : 800;
  const outputLimit = Number.isSafeInteger(payload.max_tokens) && payload.max_tokens > 0 ? Math.min(payload.max_tokens, limit) : limit;
  const upstream = { model: parser ? (env.GM_AUTHORING_MODEL || env.GM_MODEL) : env.GM_MODEL, messages: payload.messages, tools: payload.tools, max_tokens: outputLimit, tool_choice: env.GM_API_STYLE === 'glm' ? 'auto' : 'required' };
  if (parser) upstream.temperature = 0.1;
  if (env.GM_API_STYLE === 'glm') upstream.temperature = [0.1, 0.5].includes(payload.temperature) ? payload.temperature : 0.1;
  if (env.GM_API_STYLE !== 'glm') upstream.parallel_tool_calls = false;
  if (env.GM_API_STYLE === 'qwen') {
    upstream.enable_thinking = parser && ['qwen3.7-plus', 'qwen3.8-max'].includes(upstream.model);
    if (upstream.enable_thinking) {
      upstream.thinking_budget = 4096;
      upstream.tool_choice = 'auto';
      upstream.stream = true;
      upstream.tool_stream = true;
      upstream.stream_options = { include_usage: true };
    }
  }
  if (['glm','deepseek','kimi'].includes(env.GM_API_STYLE)) upstream.thinking = { type: 'disabled' };
  if (env.GM_API_STYLE === 'glm' && ['glm-4-flash','glm-4-flash-250414'].includes(env.GM_MODEL)) delete upstream.thinking;
  if (jsonTools) { delete upstream.tools; delete upstream.tool_choice; upstream.response_format = { type: 'json_object' }; }
  const destination = new URL(env.GM_API_URL);
  if (destination.protocol !== 'https:' || destination.username || destination.password) throw fail('模型服务配置无效。', 503);
  let reservation;
  try { reservation = await reserveModel(env, upstream); }
  catch (error) {
    if (!error.budgetCode) throw error;
    return json({ error: { code: error.budgetCode, message: '模型预算保护已暂停本次调用。' } }, 429);
  }
  let response;
  try {
    response = await fetch(destination, { method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${env.GM_API_KEY}` }, body: JSON.stringify(upstream), signal: AbortSignal.timeout(parser ? 300000 : 18000), redirect: 'manual' });
  } catch (error) {
    const detail = String(error.message ?? '').replaceAll(env.GM_API_KEY, '[redacted]').replace(/https?:\/\/\S+/g, '[endpoint]').slice(0, 160);
    console.error('model_upstream_connection', { name: error.name, detail });
    return json({ error: { code: 'upstream_unavailable', message: '模型连接暂时不可用。' } }, 503);
  }
  if (!response.ok) {
    let code = '';
    try { const rejected = await response.json(); code = String(rejected.error?.code ?? rejected.code ?? ''); } catch { /* Non-JSON upstream failure. */ }
    console.error('model_upstream_rejected', { status: response.status, code: /^[A-Za-z0-9_.-]{1,100}$/.test(code) ? code : '' });
    return json({ error: { code: 'upstream_rejected', message: '模型服务暂时不可用，请检查额度或稍后重试。' } }, [401,402,403,404,429].includes(response.status) ? response.status : 503);
  }
  let result;
  try { result = await completionData(response); } catch { throw fail('模型返回格式无效或内容不完整。', 502); }
  await settleModel(env, reservation, result?.usage);
  return json(result);
}
export default {
  async fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    if (!path.startsWith('/api/')) return env.ASSETS.fetch(request);
    try {
      // These identity headers are supplied by the Sites dispatcher, never a form field.
      const user = request.headers.get('oai-authenticated-user-id');
      if (!user) return json({ error: '请登录后继续冒险。' }, 401);
      const origin = request.headers.get('origin');
      if (origin && origin !== new URL(request.url).origin) throw fail('请从当前网站操作。', 403);
      if (path === '/api/cloud-state') return await snapshots(request, env, user, ctx);
      if (path === '/api/model/config' && request.method === 'GET') return json(config(env));
      if (path === '/api/model') return await model(request, env);
      return json({ error: '接口不存在。' }, 404);
    } catch (error) { return json({ error: error.status ? error.message : '服务暂时不可用，请稍后重试。' }, error.status ?? 503); }
  },
};

// Server-only API accounting. No user can reset or enlarge this global ledger.
// Uncached prices, yuan / million tokens, checked 2026-09-09.
// Qwen3.7 Plus charges thinking and final output at the same rate.
const prices = { 'qwen3.7-plus': [2, 8], 'qwen3.8-max': [12, 36], 'glm-4-flash': [0, 0] };
const error = code => Object.assign(new Error(code), { budgetCode: code });
export async function reserveModel(env, payload) {
  const rates = prices[payload.model];
  if (!rates) throw error('pricing_unknown');
  const host = new URL(env.GM_API_URL).hostname;
  const allowed = ['qwen3.7-plus', 'qwen3.8-max'].includes(payload.model)
    ? host === 'dashscope.aliyuncs.com' || host.endsWith('.cn-beijing.maas.aliyuncs.com')
    : host === 'open.bigmodel.cn';
  if (!allowed) throw error('pricing_unknown');
  const inputBound = new TextEncoder().encode(JSON.stringify(payload)).length + 8192;
  if (inputBound > 65536 || !Number.isInteger(payload.max_tokens) || payload.max_tokens < 1 || payload.max_tokens > 16384) throw error('budget_request_size');
  // Local development is capped separately at 20 yuan: total at most 45,
  // leaving 5 yuan for provider billing differences. Default hosted spend is 0.
  const limit = Number(env.GM_BUDGET_YUAN ?? 0);
  if (!Number.isFinite(limit) || limit < 0 || limit > 25) throw error('budget_configuration');
  const thinking = payload.enable_thinking ? payload.thinking_budget : 0;
  if (!Number.isInteger(thinking) || thinking < 0 || thinking > 4096 || (thinking && !['qwen3.7-plus', 'qwen3.8-max'].includes(payload.model))) throw error('budget_request_size');
  const amount = Math.ceil(inputBound * rates[0] + (payload.max_tokens + thinking) * rates[1]);
  const id = crypto.randomUUID();
  // One atomic D1 statement includes all other pending calls in the cap.
  const inserted = await env.DB.prepare(`INSERT INTO model_usage (id, model, created_at, reserved, charged, state)
    SELECT ?, ?, ?, ?, ?, 'reserved' WHERE
    (SELECT COALESCE(SUM(charged), 0) FROM model_usage) + ? <= ? RETURNING id`)
    .bind(id, payload.model, Date.now(), amount, amount, amount, Math.floor(limit * 1e6)).first();
  if (!inserted) throw error('budget_exhausted');
  return { id, rates };
}
export async function settleModel(env, reservation, usage) {
  const input = usage?.prompt_tokens, output = usage?.completion_tokens;
  if (!Number.isSafeInteger(input) || !Number.isSafeInteger(output) || input < 0 || output < 0) return;
  const amount = Math.ceil(input * reservation.rates[0] + output * reservation.rates[1]);
  await env.DB.prepare(`UPDATE model_usage SET charged = ?, state = 'reported', input_tokens = ?, output_tokens = ?
    WHERE id = ? AND state = 'reserved' RETURNING id`).bind(amount, input, output, reservation.id).first();
}

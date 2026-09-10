/** Aggregate an authoring stream; only complete documents cross the gateway. */
export async function completionData(response) {
  if (!response.headers.get('content-type')?.includes('text/event-stream')) return response.json();
  const reader = response.body.getReader(), decoder = new TextDecoder();
  const calls = new Map(), content = [];
  let buffer = '', size = 0, usage, finished = false;
  function line(value) {
    if (!value.startsWith('data:')) return;
    const raw = value.slice(5).trim();
    if (raw === '[DONE]') { finished = true; return; }
    const part = JSON.parse(raw);
    if (part.usage) usage = part.usage;
    for (const choice of part.choices ?? []) {
      if ((choice.index ?? 0) !== 0 || choice.finish_reason === 'length') throw new Error('Incomplete document');
      const delta = choice.delta ?? {};
      if (delta.content) content.push(delta.content);
      for (const fragment of delta.tool_calls ?? []) {
        const index = fragment.index ?? 0;
        if (!calls.has(index)) calls.set(index, { id: '', type: 'function', function: { name: '', arguments: '' } });
        const call = calls.get(index);
        if (fragment.id) call.id = fragment.id;
        if (fragment.type) call.type = fragment.type;
        for (const field of ['name', 'arguments']) call.function[field] += fragment.function?.[field] ?? '';
      }
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 2_000_000) throw new Error('Document too large');
      buffer += decoder.decode(value, { stream: true });
      let end;
      while ((end = buffer.indexOf('\n')) >= 0) { line(buffer.slice(0, end)); buffer = buffer.slice(end + 1); }
    }
    buffer += decoder.decode();
    if (buffer.trim()) line(buffer);
    if (!finished) throw new Error('Incomplete stream');
    return { choices: [{ message: { content: content.join(''), tool_calls: [...calls.entries()].sort(([a], [b]) => a - b).map(([, call]) => call) } }], usage };
  } catch (error) { await reader.cancel().catch(() => {}); throw error; }
}

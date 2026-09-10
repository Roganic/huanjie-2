/** HTTP-shaped bridge keeps one UI and one rule engine in native and hosted builds. */
export function installBrowserEngine(onProgress: (message: string) => void) {
  const worker = new Worker(new URL('./runtime.worker.ts', import.meta.url), { type: 'module' });
  const pending = new Map<string, { resolve: (r: Response) => void; reject: (e: Error) => void }>();
  worker.onmessage = event => {
    if (event.data.type === 'progress') { onProgress(event.data.message); return; }
    const waiter = pending.get(event.data.id);
    if (!waiter) return;
    pending.delete(event.data.id);
    if (event.data.error) waiter.reject(new Error(event.data.error));
    else waiter.resolve(new Response(event.data.body, { status: event.data.status, headers: event.data.headers }));
  };
  worker.onerror = () => { for (const waiter of pending.values()) waiter.reject(new Error('冒险引擎未能启动，请刷新重试。')); pending.clear(); };
  const networkFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const r = new Request(input instanceof Request ? input : new URL(String(input), location.href), init);
    const u = new URL(r.url);
    if (u.origin !== location.origin || !u.pathname.startsWith('/api/') || ['/api/model','/api/model/config','/api/cloud-state'].includes(u.pathname)) return networkFetch(input, init);
    const id = crypto.randomUUID();
    const body = ['GET','HEAD'].includes(r.method) ? undefined : await r.text();
    return new Promise<Response>((resolve, reject) => {
      pending.set(id, { resolve, reject });
      worker.postMessage({ id, path: u.pathname.slice(4) + u.search, method: r.method, headers: Object.fromEntries(r.headers), body });
    });
  };
  return worker;
}

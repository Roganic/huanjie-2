/// <reference lib="webworker" />
// Kept outside the React tree: game calculations never block painting or typing.
import { loadPyodide, type PyodideInterface } from 'pyodide';
let python: PyodideInterface;
let version = 0;
let previous = '';
let pendingCommit: { version: number; commit_id: string; files: Record<string, string> } | null = null;
const sendStatus = (message: string) => self.postMessage({ type: 'progress', message });
async function cloud(path: string, init?: RequestInit) {
  const r = await fetch(path, init);
  if (!r.ok) {
    let reason = '云端存档暂时无法连接。';
    try { reason = (await r.json()).error ?? reason; } catch { /* Transport error. */ }
    throw new Error(reason);
  }
  return r.json();
}
async function boot() {
  sendStatus('正在准备冒险规则…');
  const [saved, config, bundle] = await Promise.all([cloud('/api/cloud-state'), cloud('/api/model/config'), cloud('/runtime/game.json')]);
  python = await loadPyodide({ indexURL: '/runtime/python/' });
  await python.loadPackage(['pydantic', 'fastapi', 'httpx']);
  for (const [name, content] of Object.entries({ ...bundle.files, ...Object.fromEntries(Object.entries(saved.files ?? {}).map(([key, value]) => [`data/${key}`, value])) })) {
    if (!/^(game|data)\/[a-zA-Z0-9_./-]+$/.test(name) || name.split('/').includes('..')) throw new Error('冒险文件路径无效。');
    python.FS.mkdirTree('/' + name.slice(0, name.lastIndexOf('/')));
    python.FS.writeFile('/' + name, String(content));
  }
  python.FS.mkdirTree('/data');
  python.globals.set('config_json', JSON.stringify(config));
  await python.runPythonAsync(`import sys,json\nsys.path.insert(0,'/game')\nfrom src.browser_runtime import configure,handle,snapshot\nconfigure(json.loads(config_json))`);
  version = saved.version;
  previous = python.runPython('snapshot()');
  sendStatus('冒险已准备好');
}
async function persist(files: string) {
  pendingCommit ??= { version, commit_id: crypto.randomUUID(), files: JSON.parse(files) };
  const ack = await cloud('/api/cloud-state', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(pendingCommit) });
  version = ack.version;
  previous = JSON.stringify(pendingCommit.files); // Compare parsed strings canonically below.
  pendingCommit = null;
}
let queue = boot().catch(error => { sendStatus('无法准备冒险：' + String(error)); throw error; });
self.onmessage = event => {
  const request = event.data;
  queue = queue.then(async () => {
    try {
      if (pendingCommit) await persist('');
      python.globals.set('request_json', JSON.stringify(request));
      const result = JSON.parse(await python.runPythonAsync('await handle(request_json)'));
      const files = python.runPython('snapshot()') as string;
      if (JSON.stringify(JSON.parse(files)) !== JSON.stringify(JSON.parse(previous))) await persist(files);
      self.postMessage({ id: request.id, ...result });
    } catch (e) {
      const detail = e instanceof Error ? e.message : '';
      const message = !detail || detail.includes('Traceback (most recent call last)')
        ? '这次操作未能完成，已保存的内容仍然保留。请重试。' : detail;
      self.postMessage({ id: request.id, error: message });
    }
  }, e => { self.postMessage({ id: request.id, error: String(e) }); throw e; });
};

import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const output = path.join(root, 'public/runtime');
const python = path.join(root, 'node_modules/pyodide');
await fs.mkdir(path.join(output, 'python'), { recursive: true });
const lock = JSON.parse(await fs.readFile(path.join(python, 'pyodide-lock.json'), 'utf8'));
const selected = new Set();
function choose(name) { name = name.toLowerCase().replace(/[_\.]+/g, '-'); if (selected.has(name)) return; selected.add(name); for (const dependency of lock.packages[name].depends) choose(dependency); }
for (const name of ['pydantic','fastapi','httpx']) choose(name);
for (const name of selected) {
  const entry = lock.packages[name];
  let data;
  try { data = await fs.readFile(path.join(python, entry.file_name)); } catch {
    const response = await fetch(`https://cdn.jsdelivr.net/pyodide/v0.29.4/full/${entry.file_name}`);
    if (!response.ok) throw new Error(`Runtime package unavailable: ${name}`);
    data = Buffer.from(await response.arrayBuffer());
    await fs.writeFile(path.join(python, entry.file_name), data);
  }
  if (createHash('sha256').update(data).digest('hex') !== entry.sha256) throw new Error(`Runtime checksum mismatch: ${name}`);
  await fs.writeFile(path.join(output, 'python', entry.file_name), data);
}
for (const name of ['pyodide-lock.json','pyodide.asm.js','pyodide.asm.wasm','python_stdlib.zip']) await fs.copyFile(path.join(python,name), path.join(output,'python',name));
const files = {};
async function collect(source, target) {
  for (const entry of await fs.readdir(source, { withFileTypes: true })) {
    if (entry.name === '__pycache__') continue;
    if (entry.isDirectory()) await collect(path.join(source,entry.name),target+'/'+entry.name);
    else if (/\.(py|json)$/.test(entry.name)) files[target+'/'+entry.name] = await fs.readFile(path.join(source,entry.name),'utf8');
  }
}
const engine = await fs.access(path.join(root,'engine/src')).then(()=>path.join(root,'engine')).catch(()=>path.join(root,'../backend'));
for (const directory of ['src','routes']) await collect(path.join(engine,directory),'game/'+directory);
await fs.writeFile(path.join(output,'game.json'),JSON.stringify({ files }));
console.log(`Browser rules prepared: ${Object.keys(files).length} source files, ${selected.size} verified runtime packages.`);

import fs from 'node:fs/promises';
// Vite owns client output; the Worker has no Node or package runtime dependency.
await fs.mkdir('dist/client', { recursive: true });
for (const entry of await fs.readdir('dist')) {
  if (['client','server','.openai'].includes(entry)) continue;
  await fs.rename('dist/'+entry, 'dist/client/'+entry);
}
await fs.mkdir('dist/server', { recursive: true });
await fs.copyFile('cloud/worker.mjs', 'dist/server/index.js');
await fs.copyFile('cloud/budget.mjs', 'dist/server/budget.mjs');
await fs.copyFile('cloud/completion.mjs', 'dist/server/completion.mjs');
const { default: worker } = await import('../dist/server/index.js');
if (typeof worker.fetch !== 'function') throw new Error('The packaged site worker is incomplete.');

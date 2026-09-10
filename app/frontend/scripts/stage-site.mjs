/** Produce reproducible Sites source without local credentials, saves or caches. */
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = await fs.mkdtemp(path.join(os.tmpdir(), 'huanjie-site-source-'));
for (const file of ['package.json','package-lock.json','index.html','vite.config.ts','tsconfig.json','tsconfig.app.json','tsconfig.node.json','eslint.config.js','drizzle.config.ts']) {
  await fs.copyFile(path.join(root,file),path.join(target,file));
}
for (const directory of ['src','db','drizzle','.openai']) {
  await fs.cp(path.join(root,directory),path.join(target,directory),{recursive:true,filter:source=>!source.endsWith('.DS_Store')});
}
await fs.mkdir(path.join(target,'cloud'));await fs.copyFile(path.join(root,'cloud/worker.mjs'),path.join(target,'cloud/worker.mjs'));
await fs.copyFile(path.join(root,'cloud/budget.mjs'),path.join(target,'cloud/budget.mjs'));
await fs.copyFile(path.join(root,'cloud/completion.mjs'),path.join(target,'cloud/completion.mjs'));
await fs.mkdir(path.join(target,'scripts'));
for (const file of ['build-runtime.mjs','build-cloud.mjs']) await fs.copyFile(path.join(root,'scripts',file),path.join(target,'scripts',file));
await fs.cp(path.join(root,'public'),path.join(target,'public'),{recursive:true,filter:source=>source!==path.join(root,'public/runtime')&&!source.endsWith('.DS_Store')});
async function engine(source, destination) {
  await fs.mkdir(destination,{recursive:true});
  for(const entry of await fs.readdir(source,{withFileTypes:true})) {
    if(entry.name==='__pycache__')continue;
    if(entry.isDirectory())await engine(path.join(source,entry.name),path.join(destination,entry.name));
    else if(entry.isFile()&&/\.(py|json)$/.test(entry.name))await fs.copyFile(path.join(source,entry.name),path.join(destination,entry.name));
  }
}
for(const directory of ['src','routes'])await engine(path.join(root,'../backend',directory),path.join(target,'engine',directory));
await fs.writeFile(path.join(target,'.gitignore'),'node_modules/\ndist/\npublic/runtime/\n.env*\n');
await fs.writeFile(path.join(target,'README.md'),'# 幻界网站源码\n\n来自 huanjie-2 的可复现发布快照。`engine/` 保留同一 Python 规则实现，`cloud/` 负责受保护的模型调用和云端保存。\n\n安装依赖后运行 `npm run build:site`。密钥由 Sites 环境配置提供，不包含在源码、客户端或游戏存档中。\n\n正式维护位置：Roganic/huanjie-2，使用其中的 stage-site 脚本生成新版源码。\n');
console.log(target);

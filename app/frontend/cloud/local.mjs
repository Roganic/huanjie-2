/** Disposable local cloud simulator for hosted-engine QA; never uses user saves. */
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { DatabaseSync } from 'node:sqlite';
import worker from './worker.mjs';
const runtime = process.env.CLOUD_QA_DIR || await fs.mkdtemp(path.join(os.tmpdir(),'huanjie-cloud-qa-'));
await fs.mkdir(runtime,{recursive:true});
const sqlite = new DatabaseSync(path.join(runtime,'db.sqlite'));
if (!sqlite.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='runtime_snapshots'").get()) {
  for (const file of (await fs.readdir('drizzle')).filter(p => p.endsWith('.sql')).sort()) sqlite.exec(await fs.readFile('drizzle/'+file,'utf8'));
}
if (!sqlite.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='model_usage'").get()) {
  sqlite.exec(await fs.readFile('drizzle/0001_wealthy_gressill.sql', 'utf8'));
}
const DB = { prepare(sql) { return { bind(...params) { return { async first() { return sqlite.prepare(sql).get(...params) ?? null; } }; } }; } };
const BUCKET = {
  async get(key) { try { const content = await fs.readFile(path.join(runtime,key),'utf8'); return { json: async () => JSON.parse(content) }; } catch (e) { if(e.code==='ENOENT')return null; throw e; } },
  async put(key,value) { const p=path.join(runtime,key);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,value); },
  async delete(key) { await fs.rm(path.join(runtime,key),{force:true}); },
};
const settings = Object.fromEntries((await fs.readFile('../backend/.env.gm','utf8')).split('\n').filter(l=>l.startsWith('GM_')).map(l=>{const i=l.indexOf('=');return [l.slice(0,i),l.slice(i+1)];}));
// Disposable cloud databases must not create a fresh paid allowance on restart.
// Real paid QA uses the native persistent ledger until hosted accounting is live.
settings.GM_BUDGET_YUAN = '0';
const env={...settings,DB,BUCKET,ASSETS:{fetch:async()=>new Response('Not found',{status:404})}};
http.createServer(async (req,res)=>{
  try {
    if (req.url === '/api/qa-info' && req.method === 'GET') {
      res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({disposable:true}));return;
    }
    const chunks=[];for await(const chunk of req)chunks.push(chunk);
    const headers=new Headers(Object.fromEntries(Object.entries(req.headers).filter(([,v])=>typeof v==='string')));
    headers.set('oai-authenticated-user-id','local-qa-player');
    const origin=req.headers.origin || 'http://127.0.0.1:5175';
    const request=new Request(origin+req.url,{method:req.method,headers,...(!['GET','HEAD'].includes(req.method)?{body:Buffer.concat(chunks)}:{})});
    const response=await worker.fetch(request,env,{waitUntil:promise=>promise.catch(()=>{})});
    res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));
  } catch {res.writeHead(500);res.end('Local QA failed');}
}).listen(8002,'127.0.0.1',()=>console.log('Cloud QA listening at http://127.0.0.1:8002; runtime '+runtime));

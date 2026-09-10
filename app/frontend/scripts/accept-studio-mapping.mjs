/** Browser acceptance of generated annotations; no model requests or game mutation. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const base='http://127.0.0.1:5175';
assert.equal((await (await fetch(base+'/api/qa-info')).json()).disposable,true);
const generated=JSON.parse(await fs.readFile(process.argv[2],'utf8'));
assert.ok(generated.module && generated.coverage?.length);
const output=await fs.mkdtemp(path.join(os.tmpdir(),'huanjie-studio-mapping-'));
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
page.setDefaultTimeout(30000);
const report={complete:false,checks:[],errors:[]};
page.on('pageerror',error=>report.errors.push(error.message));
const api=(route,data)=>page.evaluate(async({route,data})=>{
 const response=await fetch('/api'+route,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});
 if(!response.ok)throw new Error(await response.text());return response.json();
},{route,data});
try{
 await page.goto(base);await page.locator('#runtime-loading').waitFor({state:'detached',timeout:90000});
 await page.waitForFunction(()=>document.querySelector('.adventure-heading h1')||document.querySelector('.adventure-creation input'));
 if(await page.getByRole('textbox',{name:'角色名',exact:true}).isVisible()){
  await page.getByRole('textbox',{name:'角色名',exact:true}).fill('工坊验收旅人');
  await page.getByRole('button',{name:'开始冒险 →',exact:true}).click();
  await page.locator('.adventure-creation').waitFor({state:'hidden'});
 }
 const before=await api('/state');
 const draft=await api('/modules/drafts',{source:generated.source,document:generated.module,coverage:generated.coverage,assumptions:generated.assumptions,questions:generated.questions});
 await page.getByRole('button',{name:'创作',exact:true}).click();
 await page.getByRole('combobox',{name:'已保存草稿',exact:true}).selectOption(draft.id);
 await page.getByText(generated.coverage[0].source_excerpt,{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'名称',exact:true}).fill('原稿对应验收');
 await page.getByRole('button',{name:'校验',exact:true}).click();
 await page.getByText('以下为生成时的审查记录；编辑后请重新对照原稿确认。',{exact:true}).waitFor();
 await page.getByRole('button',{name:'保存草稿',exact:true}).click();
 await page.getByRole('status').filter({hasText:'草稿已保存。'}).waitFor();
 const saved=(await api('/modules/drafts')).drafts.find(d=>d.id===draft.id);
 assert.equal(saved.document.name,'原稿对应验收');assert.deepEqual(saved.review.coverage,generated.coverage);
 const after=await api('/state');assert.equal(after.session_id,before.session_id);assert.deepEqual(after.actor,before.actor);assert.deepEqual(after.scene,before.scene);
 report.checks.push('模型原文对应展示、编辑校验保存，不改变进行中的冒险');
 await page.reload();await page.locator('#runtime-loading').waitFor({state:'detached',timeout:90000});
 await page.getByRole('button',{name:'创作',exact:true}).click();
 await page.getByRole('combobox',{name:'已保存草稿',exact:true}).selectOption(draft.id);
 await page.getByText(generated.coverage[0].source_excerpt,{exact:true}).waitFor();
 assert.equal(await page.getByRole('textbox',{name:'名称',exact:true}).inputValue(),'原稿对应验收');
 const downloadPromise=page.waitForEvent('download');await page.getByRole('button',{name:'导出',exact:true}).click();
 const download=await downloadPromise;await download.saveAs(path.join(output,'edited-module.json'));
 const exported=JSON.parse(await fs.readFile(path.join(output,'edited-module.json'),'utf8'));
 assert.equal(exported.name,'原稿对应验收');assert.ok(exported.endings.some(e=>e.forbidden_flags?.length));
 await page.screenshot({path:path.join(output,'studio.png'),fullPage:true});
 report.checks.push('跨刷新恢复审查对应和编辑内容、导出结局排除条件');
 const pending=await api('/modules/drafts',{source:generated.source,document:generated.module,pending:{format:'story_graph',source:JSON.stringify({...generated.outline,starting_scene_id:'missing'})}});
 await page.getByRole('button',{name:'返回游戏',exact:true}).click();
 await page.getByRole('button',{name:'创作',exact:true}).click();
 await page.getByRole('combobox',{name:'已保存草稿',exact:true}).selectOption(pending.id);
 await page.getByRole('button',{name:'让 AI 修复结构',exact:true}).click();
 await page.getByRole('status').filter({hasText:'故事未能完成解析。'}).waitFor();
 const retained=JSON.parse(await page.getByRole('textbox',{name:'模组 JSON',exact:true}).inputValue());
 assert.equal(retained.starting_scene_id,'missing');
 await page.getByRole('button',{name:'保存草稿',exact:true}).click();
 await page.getByRole('status').filter({hasText:'草稿已保存。'}).waitFor();
 report.checks.push('零额度下智能修复失败，原稿与未完成结构仍可保存');
 assert.deepEqual(report.errors,[]);report.complete=true;
}catch(error){report.failure=String(error);process.exitCode=1;await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});}
finally{await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({output,...report}));await browser.close();}

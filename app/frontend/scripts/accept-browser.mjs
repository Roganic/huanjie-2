/** Run against cloud/local.mjs + browser-engine Vite, in disposable storage only. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const base = process.env.QA_URL || 'http://127.0.0.1:5175';
assert.ok(['127.0.0.1','localhost'].includes(new URL(base).hostname),'Use the isolated local QA server.');
assert.equal((await (await fetch(base+'/api/qa-info')).json()).disposable,true);
const output=await fs.mkdtemp(path.join(os.tmpdir(),'huanjie-browser-acceptance-'));
const report={complete:false,errors:[],commands:[],checks:[]};
const browser=await chromium.launch({headless:true});
let page;
async function open(viewport={width:1440,height:1000}) {
 const p=await browser.newPage({viewport});p.setDefaultTimeout(45000);
 p.on('pageerror',e=>report.errors.push(e.message));
 await p.goto(base);await p.locator('#runtime-loading').waitFor({state:'detached',timeout:90000});
 await p.locator('.creation-shell, .exploration-guide, .adventure-conclusion').first().waitFor();
 await p.evaluate(()=>{
  const original=window.fetch;window.qaCommands=[];
  window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/commands'))window.qaCommands.push(await response.clone().json());return response;};
 });
 return p;
}
async function command(button){
 const before=await page.evaluate(()=>window.qaCommands.length);
 await page.getByRole('button',{name:button,exact:true}).click();
 await page.waitForFunction(n=>window.qaCommands.length>n,before,{timeout:50000});
 const result=await page.evaluate(()=>window.qaCommands.at(-1));assert.ok(result.state&&result.result,'Command must settle with state.');
 report.commands.push(result);await page.waitForFunction(()=>!document.body.innerText.includes('主持人正在回应…'));
 return result;
}
try {
 page=await open();
 const name=page.getByPlaceholder('例如：莱娜、阿尔德、暮刃');
 if(await name.count()) {await name.fill('验收旅人');await page.getByRole('button',{name:'开始冒险',exact:true}).click();await page.getByRole('textbox',{name:'你的行动'}).waitFor();}
 await page.locator('.game-menu summary').click();await page.getByRole('button',{name:'模组',exact:true}).click();
 await page.getByRole('button').filter({has:page.getByText('最后一盏渡灯',{exact:true})}).click();
 await page.getByRole('button',{name:/以此模组开始新冒险|以最新内容开始新冒险/}).click();
 await page.getByText('暮潮渡口',{exact:true}).first().waitFor();
 await command('与岑婆交谈');
 await command('前往 · 旧灯塔 →');
 await command('尝试：敲三短一长引航');
 await page.reload();await page.locator('#runtime-loading').waitFor({state:'detached',timeout:90000});
 await page.getByText('旧灯塔',{exact:true}).first().waitFor();
 assert.equal(await page.getByRole('button',{name:'尝试：敲三短一长引航',exact:true}).count(),0);
 report.checks.push('刷新保留行动结果，不重复开放已完成目标');
 await page.close();page=await open();
 await page.getByText('旧灯塔',{exact:true}).first().waitFor();
 report.checks.push('独立浏览器上下文恢复上次冒险');
 await command('前往 · 暮潮渡口 →');
 const end=await command('与岑婆交谈');assert.equal(end.state.journey.ending.id,'bell');
 await page.getByRole('heading',{name:'听见归航',exact:true}).waitFor();
 await page.screenshot({path:path.join(output,'ending-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 await page.screenshot({path:path.join(output,'ending-mobile.png'),fullPage:true});
 report.checks.push('短篇钟声路线结局及手机布局');
 await page.setViewportSize({width:1440,height:1000});
 await page.locator('.game-menu summary').click();await page.getByRole('button',{name:'创作工坊',exact:true}).click();
 await page.getByLabel('以现有模组为起点').selectOption('last-ferry-light');
 await page.getByLabel('名称',{exact:true}).fill('渡灯 · 编辑验收');
 await page.getByRole('button',{name:'校验',exact:true}).click();await page.getByRole('heading',{name:'格式校验通过'}).waitFor();
 await page.getByRole('button',{name:'保存并返回',exact:true}).click();
 await page.locator('.story-studio').waitFor({state:'detached'});
 await page.locator('.game-menu summary').click();await page.getByRole('button',{name:'创作工坊',exact:true}).click();
 await page.getByLabel('已保存草稿').selectOption({label:'渡灯 · 编辑验收'});
 assert.equal(await page.getByLabel('名称',{exact:true}).inputValue(),'渡灯 · 编辑验收');
 const download=page.waitForEvent('download');await page.getByRole('button',{name:'导出',exact:true}).click();
 const artifact=await download;await artifact.saveAs(path.join(output,'edited-module.json'));
 await page.screenshot({path:path.join(output,'studio.png'),fullPage:true});
 await page.getByRole('button',{name:'返回游戏',exact:true}).click();
 await page.getByRole('heading',{name:'听见归航',exact:true}).waitFor();
 report.checks.push('复制、编辑、关闭保存、重新打开和导出，原冒险保留');
 assert.deepEqual(report.errors,[]);report.complete=true;
} catch(error) {report.failure=String(error);if(page) {report.visible=await page.locator('body').innerText().catch(()=> '');await page.screenshot({path:path.join(output,'failure.png'),fullPage:true}).catch(()=>{});}process.exitCode=1;}
finally {await fs.writeFile(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({output,complete:report.complete,checks:report.checks,failure:report.failure,model:report.commands.map(c=>c.result.gm).filter(Boolean)},null,2));await browser.close();}

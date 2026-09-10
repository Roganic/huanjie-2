/** Real browser/editor persistence checks against disposable hosted-engine storage. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const base = process.env.QA_URL || 'http://127.0.0.1:5175';
assert.ok(['localhost', '127.0.0.1'].includes(new URL(base).hostname));
assert.equal((await (await fetch(base + '/api/qa-info')).json()).disposable, true);
const output = await fs.mkdtemp(path.join(os.tmpdir(), 'huanjie-studio-'));
const report = { complete: false, checks: [], errors: [] };
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(30000);
page.on('pageerror', e => report.errors.push(e.message));
const title = '工坊验收-' + Date.now();
async function openStudio() {
  await page.locator('.game-menu summary').click();
  await page.getByRole('button', { name: '创作工坊', exact: true }).click();
}
async function tab(name) { await page.getByRole('navigation', { name: '创作内容' }).getByRole('button', { name, exact: true }).click(); }
async function reopen() {
  await page.getByRole('button', { name: '保存并返回', exact: true }).click();
  await page.locator('.story-studio').waitFor({ state: 'detached' });
  await page.reload(); await page.locator('#runtime-loading').waitFor({ state: 'detached', timeout: 90000 });
  await openStudio(); await page.getByLabel('已保存草稿').selectOption({ label: title });
}
try {
  await page.goto(base); await page.locator('#runtime-loading').waitFor({ state: 'detached', timeout: 90000 });
  await page.locator('.exploration-guide, .adventure-conclusion').first().waitFor();
  await openStudio(); await page.getByLabel('以现有模组为起点').selectOption('last-ferry-light');
  await page.getByLabel('名称', { exact: true }).fill(title);
  for (const [category, id, field, value] of [
    ['地图与场景', 'ferry', '描述', '暮潮漫过石阶，灯火仍亮着。'],
    ['人物', 'cen', '对白', '先救人，别担心追责。'],
    ['装备与物品', 'harbor-token', '名称', '七道波纹铜章'],
    ['任务', 'bring-home', '任务目标', '发出引航信号，再回来报告。'],
    ['事件', 'fog', '叙事', '浓雾封住港口，拖船正在赶来。'],
  ]) {
    await tab(category); await page.getByLabel('选择' + category).selectOption(id);
    await page.getByLabel(field, { exact: true }).fill(value);
  }
  await tab('结局'); await page.locator('.studio-main > fieldset > details > summary').click();
  await page.getByLabel('标题', { exact: true }).nth(0).fill('黎明的归航');
  await tab('初始补给');
  await page.getByLabel('物品标识', { exact: true }).fill('repair-record');
  await page.getByLabel('初始数量', { exact: true }).fill('1');
  await page.getByRole('button', { name: '校验', exact: true }).click();
  await page.getByRole('heading', { name: '格式校验通过' }).waitFor();
  report.checks.push('地图、人物、物品、任务、事件、结局、初始补给分类编辑并通过契约校验');
  await tab('JSON 文件');
  const invalid = '{"name":"尚未写完的编辑';
  await page.getByRole('textbox', { name: '模组 JSON' }).fill(invalid);
  await reopen();
  assert.equal(await page.getByRole('textbox', { name: '模组 JSON' }).inputValue(), invalid);
  await page.getByRole('button', { name: '加入模组库', exact: true }).click();
  await page.getByRole('status').filter({ hasText: '请先应用文件中的修改' }).waitFor();
  report.checks.push('未应用且无效的 JSON 跨刷新恢复；不误导入旧内容');
  // Read the saved underlying document, then repair through the visible file editor.
  const saved = await page.evaluate(async label => {
    const response = await fetch('/api/modules/drafts');
    return (await response.json()).drafts.find(d => d.document.name === label);
  }, title);
  assert.equal(saved.document.characters.cen.dialogue, '先救人，别担心追责。');
  assert.equal(saved.document.items['harbor-token'].name, '七道波纹铜章');
  assert.equal(saved.document.endings[0].title, '黎明的归航');
  assert.deepEqual(saved.document.supplies, { item_id: 'repair-record', starting_quantity: 1 });
  await page.getByRole('textbox', { name: '模组 JSON' }).fill(JSON.stringify(saved.document));
  await page.getByRole('button', { name: '应用到草稿', exact: true }).click();
  await page.getByRole('heading', { name: '格式校验通过' }).waitFor();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出', exact: true }).click();
  await (await download).saveAs(path.join(output, 'edited.json'));
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.screenshot({ path: path.join(output, 'studio-mobile.png'), fullPage: true });
  report.checks.push('修复后导出，手机布局无横向溢出');
  await page.setViewportSize({ width: 1440, height: 1000 });
  const graph = { name: title + ' · 故事修复', description: '送回信件。', starting_scene_id: 'missing',
    locations: [{ id: 'home', name: '家门', description: '阿梅在等信。', exits: ['bridge'] },
      { id: 'bridge', name: '石桥', description: '信夹在桥栏里。', exits: ['home'] }],
    people: [{ id: 'mei', name: '阿梅', scene_id: 'home', type: 'friendly', dialogue: '请去石桥找回我的信。' }],
    beats: [{ id: 'find', name: '取回信', scene_id: 'bridge', trigger: 'interact', success: { narration: '你取回夹在桥栏里的信。' } }],
    quests: [{ id: 'letter', name: '找回信件', giver_id: 'mei', objective: '取回信并交给阿梅。', requires: [{ beat_id: 'find' }], ready_text: '信已经找回。', xp_reward: 10 }],
    endings: [{ id: 'lamp', title: '灯下', description: '阿梅收到了信。', completed_quests: ['letter'] }] };
  await page.evaluate(async ({ graph, document }) => {
    const r = await fetch('/api/modules/drafts', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document: { ...document, name: graph.name }, source: '找回石桥上的信，交给阿梅。',
        pending: { format: 'story_graph', source: JSON.stringify(graph) }, questions: ['信件寄自何处？'] }) });
    if (!r.ok) throw new Error('Draft creation failed');
  }, { graph, document: saved.document });
  await page.getByRole('button', { name: '保存并返回', exact: true }).click();
  await page.locator('.story-studio').waitFor({ state: 'detached' });
  await openStudio(); await page.getByLabel('已保存草稿').selectOption({ label: graph.name });
  await page.getByRole('heading', { name: '修复故事结构' }).waitFor();
  await page.getByText('信件寄自何处？', { exact: true }).waitFor();
  graph.starting_scene_id = 'home';
  await page.getByRole('textbox', { name: '模组 JSON' }).fill(JSON.stringify(graph));
  await page.getByRole('button', { name: '应用到草稿', exact: true }).click();
  await page.getByRole('heading', { name: '格式校验通过' }).waitFor();
  const translated = JSON.parse(await page.getByRole('textbox', { name: '模组 JSON' }).inputValue());
  assert.ok(translated.scenes.bridge.interactions.some(i => i.id === 'find'));
  assert.ok(translated.quests.letter.required_flags.length);
  report.checks.push('失败故事结构恢复、作者问题保留、修改后确定性编译为可玩契约');
  assert.deepEqual(report.errors, []); report.complete = true;
} catch (e) {
  report.failure = String(e); report.visible = await page.locator('body').innerText().catch(() => '');
  await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {});
  process.exitCode = 1;
} finally {
  await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ output, ...report }, null, 2)); await browser.close();
}

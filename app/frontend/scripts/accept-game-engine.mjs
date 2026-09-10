/** End-to-end game-engine QA against the disposable hosted-runtime simulator. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { layoutMap } from '../src/components/mapLayout.ts';
const base = 'http://127.0.0.1:5175';
assert.equal((await (await fetch(base + '/api/qa-info')).json()).disposable, true);
const output = await fs.mkdtemp(path.join(os.tmpdir(), 'huanjie-adventure-engine-'));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
page.setDefaultTimeout(20000);
const report = { complete: false, checks: [], errors: [] };
page.on('pageerror', error => report.errors.push(error.message));
try {
  await page.goto(base); await page.locator('#runtime-loading').waitFor({ state: 'detached', timeout: 90000 });
  await page.locator('.adventure-engine').waitFor();
  await page.waitForFunction(() => document.querySelector('.adventure-heading h1') || document.querySelector('.adventure-creation input'));
  if (await page.getByRole('textbox', { name: '角色名', exact: true }).isVisible()) {
    await page.getByRole('textbox', { name: '角色名', exact: true }).fill('引擎旅人');
    await page.getByRole('button', { name: '开始冒险 →', exact: true }).click();
    await page.locator('.adventure-creation').waitFor({ state: 'hidden' });
  }
  if (await page.getByRole('button', { name: '撤退', exact: true }).isVisible()) {
    await page.getByRole('button', { name: '撤退', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.adventure-feedback')?.innerText.includes('正在'));
  }
  if (await page.getByRole('button', { name: '继续冒险 →', exact: true }).isVisible()) {
    await page.getByRole('button', { name: '继续冒险 →', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.adventure-feedback')?.innerText.includes('正在'));
  }
  await page.getByRole('button', { name: '模组', exact: true }).click();
  await page.getByRole('button').filter({ has: page.getByText('最后一盏渡灯', { exact: true }) }).click();
  await page.getByRole('button', { name: /以此模组开始新冒险|以最新内容开始新冒险/ }).click();
  await page.locator('.module-panel-overlay').waitFor({ state: 'detached' });
  await page.getByRole('heading', { name: '暮潮渡口', exact: true }).waitFor();
  assert.equal(await page.locator('canvas').count(), 1);
  await page.screenshot({ path: path.join(output, 'desktop.png'), fullPage: true });
  await fs.writeFile(path.join(output, 'page.txt'), await page.locator('body').innerText());
  report.checks.push('主界面为 Phaser Scene；模组切换与短篇起点');
  const idle = () => page.waitForFunction(() => !document.querySelector('.adventure-feedback')?.innerText.includes('正在'));
  const read = route => page.evaluate(async route => (await fetch('/api' + route, { headers: { 'X-Session-Id': localStorage.getItem('huanjie.session_id') } })).json(), route);
  const move = async name => { await page.getByRole('button', { name, exact: true }).click(); await page.getByRole('button', { name: '前往这里 →', exact: true }).click(); await idle(); await page.getByRole('heading', { name, exact: true }).waitFor(); };
  await page.getByRole('button', { name: '交谈 · 岑婆', exact: true }).click(); await idle();
  assert.ok((await read('/state')).narrative_history.length > 0);
  assert.ok(await page.locator('.adventure-prose').count());
  report.checks.push('NPC 交谈与持久叙事显示（隔离环境使用固定主持，不作为真实 AI 验收）');
  const data = await read('/map'), layout = layoutMap(data.nodes), point = layout.positions.get('lighthouse');
  await page.getByRole('button', { name: '定位', exact: true }).click();
  await page.waitForTimeout(300); // Wait for the engine camera's bounded 200 ms pan.
  const canvas = page.locator('.adventure-stage canvas'), box = await canvas.boundingBox();
  const currentPoint = layout.positions.get(data.current_node);
  const zoom = Math.max(.25, Math.min(box.width / layout.width, box.height / layout.height, 1.15));
  await page.mouse.click(box.x + box.width / 2 + (point.x - currentPoint.x) * zoom, box.y + box.height / 2 + (point.y - currentPoint.y) * zoom);
  await page.getByRole('button', { name: '前往这里 →', exact: true }).click(); await idle();
  assert.equal((await read('/map')).current_node, 'lighthouse');
  const challenge = (await read('/exploration')).challenges.find(c => c.id === 'ring-bell');
  await page.getByRole('button', { name: challenge.name, exact: true }).click();
  await page.getByRole('dialog', { name: challenge.name }).getByRole('button', { name: '尝试', exact: true }).click(); await idle();
  await move('暮潮渡口');
  await page.getByRole('button', { name: '交谈 · 岑婆', exact: true }).click(); await idle();
  assert.equal((await read('/state')).journey.ending.id, 'bell');
  await page.screenshot({ path: path.join(output, 'ending.png'), fullPage: true });
  await page.getByRole('button', { name: '继续探索', exact: true }).click();
  report.checks.push('真实 Canvas 选择路网地点、移动、挑战选择、短篇钟声结局与继续探索');
  await page.getByRole('button', { name: '菜单', exact: true }).click(); await page.getByRole('button', { name: '保存冒险', exact: true }).click(); await idle();
  const savedState = await read('/state');
  await page.reload(); await page.locator('#runtime-loading').waitFor({ state: 'detached', timeout: 90000 }); await page.getByRole('heading', { name: '暮潮渡口', exact: true }).waitFor();
  assert.equal((await read('/state')).journey.ending.id, savedState.journey.ending.id);
  await page.getByRole('button', { name: '继续探索', exact: true }).click();
  await page.getByRole('button', { name: '角色', exact: true }).click(); await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '背包', exact: true }).click(); await page.getByRole('dialog').waitFor(); await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '手记', exact: true }).click(); await page.getByRole('dialog', { name: '冒险手记' }).waitFor(); await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => { const c = document.querySelector('.adventure-stage canvas'); return c && Math.abs(c.width - c.parentElement.clientWidth) < 2; });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  const input = await page.getByRole('textbox', { name: '你的行动', exact: true }).boundingBox(); assert.ok(input.y + input.height <= 844);
  await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  report.checks.push('保存、刷新恢复、角色/背包/手记、手机布局与可见输入框');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '模组', exact: true }).click();
  await page.getByRole('button').filter({ has: page.getByText('潮汐之下的城', { exact: true }) }).click();
  await page.getByRole('button', { name: /以此模组开始新冒险|以最新内容开始新冒险/ }).click();
  await page.locator('.module-panel-overlay').waitFor({ state: 'detached' }); await idle();
  await move('旧市集'); await move('桥下走廊');
  if ((await read('/state')).game_phase !== 'combat') {
    const enemy = (await read('/exploration')).targets.find(t => t.attackable);
    await page.getByRole('button', { name: `攻击 · ${enemy.name}`, exact: true }).click(); await idle();
  }
  assert.equal(await page.locator('.adventure-engine').getAttribute('data-mode'), 'combat');
  const combat = await read('/combat/state'); assert.equal(combat.participants.filter(p => !p.is_player).length, 2);
  const defend = combat.available_actions.find(a => a.id === 'defend' || a.id === 'dodge');
  if (defend) { await page.getByRole('button', { name: defend.name, exact: true }).click(); await idle(); }
  await page.screenshot({ path: path.join(output, 'combat.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: path.join(output, 'combat-mobile.png'), fullPage: true });
  await page.waitForFunction(() => { const c = document.querySelector('.adventure-stage canvas'); return c && Math.abs(c.width - c.parentElement.clientWidth) < 2; });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  assert.ok(await page.locator('.adventure-combat-log').count());
  report.checks.push('中篇双敌人遭遇、引擎先攻队列、战斗行动与手机战斗');
  if (await page.getByRole('button', { name: '撤退', exact: true }).isVisible()) { await page.getByRole('button', { name: '撤退', exact: true }).click(); await idle(); }
  if (await page.getByRole('button', { name: '继续冒险 →', exact: true }).isVisible()) { await page.getByRole('button', { name: '继续冒险 →', exact: true }).click(); await idle(); }

  assert.deepEqual(report.errors, []); report.complete = true;
} catch (error) { report.failure = String(error); await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {}); await fs.writeFile(path.join(output, 'page.txt'), await page.locator('body').innerText()); process.exitCode = 1; }
finally { await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify({ output, ...report })); await browser.close(); }

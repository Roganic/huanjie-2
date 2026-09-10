/** Floating-map input complements the full adventure acceptance. No paid requests. */
import { chromium } from 'playwright';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const base = 'http://127.0.0.1:5175';
assert.equal((await (await fetch(base + '/api/qa-info')).json()).disposable, true);
const output = await fs.mkdtemp(path.join(os.tmpdir(), 'huanjie-floating-engine-'));
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
page.setDefaultTimeout(20000);
const report = { complete: false, errors: [], checks: [] }; page.on('pageerror', error => report.errors.push(error.message));
try {
  await page.goto(base); await page.locator('#runtime-loading').waitFor({ state: 'detached', timeout: 90000 });
  await page.getByRole('button', { name: '浮窗 / 归位', exact: true }).click();
  const world = page.locator('.adventure-world'), handle = page.getByRole('button', { name: '移动地图', exact: true });
  const before = await world.boundingBox(), grip = await handle.boundingBox();
  await page.mouse.move(grip.x + 15, grip.y + 15); await page.mouse.down(); await page.mouse.move(grip.x + 115, grip.y + 65, { steps: 8 }); await page.mouse.up();
  const moved = await world.boundingBox(); assert.ok(moved.x > before.x + 80); assert.ok(moved.y > before.y + 30);
  await page.mouse.move(moved.x + moved.width - 3, moved.y + moved.height - 3); await page.mouse.down(); await page.mouse.move(moved.x + moved.width + 77, moved.y + moved.height + 37, { steps: 8 }); await page.mouse.up();
  const resized = await world.boundingBox(); assert.ok(resized.width > moved.width + 40); assert.ok(resized.height > moved.height + 20);
  await page.waitForFunction(() => { const c = document.querySelector('.adventure-stage canvas'); return Math.abs(c.width - c.parentElement.clientWidth) < 2; });
  await page.getByRole('button', { name: '旋转指针', exact: true }).click(); await page.getByRole('button', { name: '定位', exact: true }).click();
  await page.screenshot({ path: path.join(output, 'floating.png'), fullPage: true });
  await page.getByRole('button', { name: '浮窗 / 归位', exact: true }).click();
  const docked = await world.boundingBox(); assert.ok(docked.height > 800); assert.equal(await world.evaluate(e => e.style.width), '');
  await page.getByRole('button', { name: '关闭', exact: true }).click(); assert.equal(await world.isVisible(), false);
  await page.getByRole('button', { name: '地图', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForFunction(() => { const c = document.querySelector('.adventure-stage canvas'); return Math.abs(c.width - c.parentElement.clientWidth) < 2; });
  await page.screenshot({ path: path.join(output, 'mobile.png'), fullPage: true });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  report.checks.push('浮窗拖动、原生拉伸、Canvas 同步尺寸、归位清除浮窗尺寸、关闭/重开、手机与减少动效偏好');
  assert.deepEqual(report.errors, []); report.complete = true;
} catch (error) { report.failure = String(error); await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true }).catch(() => {}); process.exitCode = 1; }
finally { await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2)); console.log(JSON.stringify({ output, ...report })); await browser.close(); }

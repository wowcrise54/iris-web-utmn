import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const root = path.resolve('../..');
const output = path.join(root, 'v3/runtime/browser');
fs.mkdirSync(output, { recursive: true });
const env = Object.fromEntries(fs.readFileSync(path.join(root, '.env.v3.validation'), 'utf8').split(/\r?\n/)
  .filter((line) => line.includes('=')).map((line) => [line.slice(0, line.indexOf('=')), line.slice(line.indexOf('=') + 1)]));
const base = process.env.IRIS_PROBE_URL || 'https://localhost:18545';
const browser = await chromium.launch({ headless: true, channel: 'msedge' });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
try {
  await page.goto(base + '/login', { waitUntil: 'networkidle' });
  await page.getByRole('combobox', { name: 'Interface language' }).selectOption('ru');
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(() => document.documentElement.lang === 'ru');
  assert.equal(await page.locator('html').getAttribute('lang'), 'ru');
  await page.screenshot({ path: path.join(output, 'login-ru.png'), fullPage: true });
  console.log('Russian login text:', (await page.locator('body').innerText()).slice(0, 650));
  await page.locator('input[name="username"], input#username').first().fill('administrator');
  await page.locator('input[name="password"], input#password').first().fill(env.IRIS_ADM_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 45000 });
  await page.waitForLoadState('networkidle');
  console.log('Logged in:', new URL(page.url()).pathname);
  await page.goto(base + '/case/2', { waitUntil: 'networkidle' });
  await page.screenshot({ path: path.join(output, 'case-2-ru.png'), fullPage: true });
  assert.match(await page.locator('body').innerText(), /Расследование фишинга/);
  const baselinePath = path.join(root, 'v3/runtime/data-baseline.json');
  if (fs.existsSync(baselinePath)) {
    const baseline = JSON.parse(fs.readFileSync(baselinePath, 'utf8'));
    await page.goto(base + '/case/2/tasks', { waitUntil: 'networkidle' });
    const tasks = await page.locator('body').innerText();
    for (const task of baseline.case_tasks.filter((task) => task.task_case_id === 2)) {
      assert.ok(tasks.includes(task.task_title), 'Saved task is missing from the case UI');
    }
    await page.goto(base + '/case/2/assets', { waitUntil: 'networkidle' });
    const assets = await page.locator('body').innerText();
    for (const asset of baseline.case_assets.filter((asset) => asset.case_id === 2)) {
      assert.ok(assets.includes(asset.asset_name), 'Saved asset is missing from the case UI');
    }
    console.log('Saved tasks and assets visible in the live UI');
  }
  for (const route of ['/alerts', '/war-rooms', '/settings/investigation-flows']) {
    const response = await page.goto(base + route, { waitUntil: 'networkidle' });
    assert.equal(response.status(), 200);
    const body = await page.locator('body').innerText();
    assert.doesNotMatch(body, /Internal Error|Unexpected error|500: Internal/i);
    console.log('Russian page:', route, 'OK');
  }
  await page.getByRole('combobox', { name: 'Язык интерфейса' }).selectOption('en');
  await page.waitForFunction(() => document.documentElement.lang === 'en');
  await page.waitForLoadState('networkidle');
  assert.equal(await page.locator('html').getAttribute('lang'), 'en');
  await page.getByRole('combobox', { name: 'Interface language' }).selectOption('ru');
  await page.waitForFunction(() => document.documentElement.lang === 'ru');
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.locator('html').getAttribute('lang'), 'ru');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ languageRoundTrip: true,
    case2Visible: true, localePersists: true, pageErrors: errors }, null, 2));
  console.log('Browser acceptance passed');
} finally {
  await browser.close();
}

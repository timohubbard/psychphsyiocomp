#!/usr/bin/env node
/**
 * Blinks and heart rate where a researcher reads them, in headless Chrome.
 *
 * Read-only; run it on scratch data that has a blinks stage and camera heart
 * rate (process with --rppg):
 *   npm run app -- --data <scratch out> --port 5199
 *   node tools/verify_physio_view.mjs --port 5199 --session <id> --study <id> [--shots <dir>]
 *
 * Checks that the session page draws the blink strip, that a heart-rate plot
 * breaks at the windows that failed their gates instead of joining across
 * them, and that the cohort page's per-stimulus table carries blink figures
 * and heads heart rate as unvalidated.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = Number(opt('--port', 5199));
const SESSION = opt('--session', null);
const STUDY = opt('--study', 'stimulus-example');
const SHOTS = opt('--shots', null);
const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok, detail });

async function shot(page, name, selector) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  if (selector) await page.js(`document.querySelector(${JSON.stringify(selector)})?.scrollIntoView()`);
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(SHOTS, name), Buffer.from(data, 'base64'));
}

async function main() {
  const { proc, page } = await launch({ profileName: 'chrome-physio-profile', port: 9347 });
  const js = (e) => page.js(e);
  const until = (e, what, ms = 90000) => page.until(e, what, ms);
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/index.html?session=${encodeURIComponent(SESSION)}` });
    await until(`[...document.querySelectorAll('#detail h2')].some((h) => /^Blinks/.test(h.textContent))`, 'the blink strip');
    const ticks = await js(`[...document.querySelectorAll('#detail h2')].find((h) => /^Blinks/.test(h.textContent))
      .nextElementSibling.querySelectorAll('rect').length`);
    check('the session page draws a blink strip', ticks > 0, `${ticks} marks`);
    await shot(page, 'session-blinks.png', '#detail h2 + .card svg[aria-label*="blinks"]');

    const row = await js(`(() => { const tr = [...document.querySelectorAll('tr.clickable')]
      .find((t) => t.dataset.channel === 'cardiac.hr_bpm'); if (!tr) return false; tr.click(); return true; })()`);
    if (!row) {
      check('a heart-rate plot breaks at failed windows', false, 'no cardiac.hr_bpm channel in this session');
    } else {
      await until(`/cardiac\\.hr_bpm/.test(document.querySelector('#plot h2')?.textContent ?? '')`, 'the heart-rate plot');
      const moves = await js(`(document.querySelector('#plot path')?.getAttribute('d').match(/M/g) ?? []).length`);
      check('a heart-rate plot breaks at failed windows', moves > 1, `${moves} separate runs`);
      await shot(page, 'session-hr.png', '#plot');
    }

    await page.send('Page.navigate', { url: `http://localhost:${PORT}/cohort.html?study=${encodeURIComponent(STUDY)}&dev=1` });
    await until(`!!document.querySelector('table.perstim')`, 'the per-stimulus table', 180000);
    const head = await js(`document.querySelector('table.perstim thead').textContent.replace(/\\s+/g, ' ')`);
    const body = await js(`document.querySelector('table.perstim tbody').textContent.replace(/\\s+/g, ' ')`);
    check('the per-stimulus table has blink figures', /n=\d/.test(body) && /Blinks \/min/.test(head), body.slice(0, 90));
    check('heart rate is headed unvalidated', /Heart rate unvalidated/i.test(head), head.slice(0, 90));
    await shot(page, 'cohort-perstim.png', 'table.perstim');

    await page.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
    await js(`new Promise((r) => setTimeout(r, 300))`);
    const over = await js(`document.documentElement.scrollWidth - document.documentElement.clientWidth`);
    check('the cohort page fits a phone', over <= 1, `${over}px over`);
    await shot(page, 'cohort-perstim-phone.png', 'table.perstim');
  } finally {
    proc.kill();
  }
  console.log('\n  BLINKS AND HEART RATE IN VIEW');
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(44)} ${c.detail}`);
  const ok = checks.length === 5 && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'PHYSIO VIEW OK' : 'PHYSIO VIEW FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  PHYSIO VIEW: ERROR — ${err.message}\n`); process.exitCode = 2; });

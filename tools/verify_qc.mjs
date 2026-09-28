#!/usr/bin/env node
/**
 * Drive the session quality panel in headless Chrome.
 *
 * Read-only against whatever data the app serves; run it on scratch data:
 *   npm run app -- --data <scratch out> --port 5199
 *   node tools/verify_qc.mjs --port 5199 --session <id> [--shots <dir>]
 *
 * Checks that every listed session gets a QC badge; that the panel on the
 * chosen session shows the verdict, the cohort line and at least one check
 * with the basis its threshold came from; and that the page fits a phone
 * width without scrolling sideways. With --shots, saves desktop and phone
 * screenshots of the panel.
 */
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(k); return i >= 0 ? argv[i + 1] : d; };
const PORT = Number(opt('--port', 5199));
const SESSION = opt('--session', null);
const SHOTS = opt('--shots', null);
const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok, detail });

async function shot(page, name) {
  if (!SHOTS) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.js(`document.getElementById('qc')?.scrollIntoView()`);
  const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(SHOTS, name), Buffer.from(data, 'base64'));
}

async function main() {
  const { proc, page } = await launch({ profileName: 'chrome-qc-profile', port: 9345 });
  const js = (e) => page.js(e);
  const until = (e, what, ms = 60000) => page.until(e, what, ms);
  try {
    await page.send('Runtime.enable');
    const q = SESSION ? `?session=${encodeURIComponent(SESSION)}` : '';
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/index.html${q}` });
    await until(`document.querySelectorAll('.sess').length > 0`, 'the session list');
    const n = await js(`document.querySelectorAll('.sess').length`);
    await until(`[...document.querySelectorAll('.sess .pills')].every((p) => /QC:/.test(p.innerText))`, 'a badge per session', 180000);
    const badges = await js(`[...document.querySelectorAll('.sess')].map((s) => s.dataset.id + ' ' + (s.querySelector('.pills').innerText.match(/QC: [a-z ]+/) || [''])[0]).join(' · ')`);
    check('every listed session gets a QC badge', true, `${n}: ${badges.slice(0, 120)}`);

    await until(`/Usable\\?/.test(document.getElementById('qc')?.textContent ?? '')`, 'the panel', 120000);
    const head = await js(`document.querySelector('#qc h2').textContent.replace(/\\s+/g, ' ')`);
    check('the panel gives a verdict and the cohort line', /Usable\? (usable|warnings|fails a rule|unmeasured)/.test(head)
      && /(in the cohort|left out|no study|unavailable|edited)/.test(head), head);
    const basis = await js(`[...document.querySelectorAll('#qc .thr')].map((t) => t.innerText).join(' | ')`);
    check('thresholds say where they came from', /· (declared|default)/.test(basis), basis.slice(0, 100));
    await shot(page, 'qc-desktop.png');

    await page.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
    await js(`new Promise((r) => setTimeout(r, 300))`);
    const overflow = await js(`document.documentElement.scrollWidth - document.documentElement.clientWidth`);
    check('it fits a phone without sideways scroll', overflow <= 1, `${overflow}px over`);
    await shot(page, 'qc-phone.png');
  } finally {
    proc.kill();
  }
  console.log('\n  SESSION QC');
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(44)} ${c.detail}`);
  const ok = checks.length === 4 && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'SESSION QC OK' : 'SESSION QC FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  SESSION QC: ERROR — ${err.message}\n`); process.exitCode = 2; });

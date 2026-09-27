#!/usr/bin/env node
/**
 * Does the researcher app's cohort page render a cohort, in a real browser?
 *
 * The numbers are tested in Python (test_cohort.py, test_stimulus_export.py);
 * this checks the page that shows them: the funnel, a drawn epoch curve, and a
 * painted heatmap laid over its picture, from /api/studies/<id>/cohort, in
 * headless Chrome.
 *
 * Usage (app running):  node tools/verify_cohort_view.mjs <study_id> [--port 5174] [--dev]
 */
import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const study = argv.find((a) => !a.startsWith('--'));
const i = argv.indexOf('--port');
const PORT = Number(i >= 0 ? argv[i + 1] : 5174);
const DEV = argv.includes('--dev') ? '&dev=1' : '';

async function main() {
  if (!study) throw new Error('usage: verify_cohort_view.mjs <study_id>');
  const { proc, page } = await launch({ profileName: 'chrome-cohort-profile', port: 9336 });
  const checks = [];
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/cohort.html?study=${encodeURIComponent(study)}${DEV}` });
    await page.until(`!!document.querySelector('#main .funnel') || !!document.querySelector('#main .note.bad')`,
      'the cohort to render', 60_000);
    const r = await page.js(`(() => ({
      rows: [...document.querySelectorAll('#main .fstep')].map((s) => s.innerText.replace(/\\s+/g, ' ').trim()),
      curves: document.querySelectorAll('path.curve').length,
      canvases: [...document.querySelectorAll('canvas')].map((c) => {
        const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
        let lit = 0; for (let k = 0; k < d.length; k += 4) if (d[k] + d[k + 1] + d[k + 2] > 60) lit += 1;
        return { w: c.width, h: c.height, lit };
      }),
      pictures: [...document.querySelectorAll('.heat img')].map((i) => i.naturalWidth),
      error: document.querySelector('#main .note.bad')?.textContent ?? null,
    }))()`);
    checks.push(['funnel rendered', r.rows.length > 0, r.rows.join(' | ')]);
    checks.push(['an epoch curve was drawn', r.curves > 0, `${r.curves} curve(s)`]);
    checks.push(['a heatmap was painted', r.canvases.some((c) => c.lit > 0),
      r.canvases.map((c) => `${c.w}x${c.h} lit ${c.lit}`).join(', ') || 'none']);
    // A picture's heatmap is only readable over the picture; a video has none underneath.
    checks.push(['pictures under the heatmaps', r.pictures.every((w) => w > 0),
      r.pictures.length ? `${r.pictures.length} loaded` : 'no picture stimuli']);
    if (r.error) checks.push(['no error shown', false, r.error]);
  } finally {
    proc.kill();
  }
  console.log(`\n  COHORT VIEW  ${study}`);
  for (const [name, ok, detail] of checks) console.log(`  [${ok ? 'PASS' : 'FAIL'}]  ${name.padEnd(26)} ${detail}`);
  const ok = checks.every(([, pass]) => pass);
  console.log(`\n  ${ok ? 'COHORT VIEW OK' : 'COHORT VIEW FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  COHORT VIEW: ERROR — ${err.message}\n`); process.exitCode = 2; });

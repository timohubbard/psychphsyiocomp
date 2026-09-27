#!/usr/bin/env node
/**
 * Drive the Reliability page in headless Chrome.
 *
 * Run it against SCRATCH data (it saves scoring rules): a coded session whose
 * engine output is planted to match the raters, and a media folder so the
 * recording's time origin can be checked:
 *   npm run app -- --data <scratch out> --media <scratch media> --port 5198
 *   node tools/verify_reliability.mjs --port 5198
 *
 * It checks that the raters' ceiling is shown per session; that an invalid
 * rule is refused with its reason and cannot be saved; that a valid rule saves
 * as a version and the engine is then scored on the raters' terms, with its
 * coverage; and that the score is read against the ceiling, not against 1.0.
 */
import { setTimeout as sleep } from 'node:timers/promises';

import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const i = argv.indexOf('--port');
const PORT = Number(i >= 0 ? argv[i + 1] : 5198);
const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok, detail });

async function main() {
  const { proc, page } = await launch({ profileName: 'chrome-reliability-profile', port: 9344 });
  const js = (e) => page.js(e);
  const until = (e, what, ms = 30000) => page.until(e, what, ms);
  const setRule = (obj) => js(`(() => { const t = document.getElementById('ruleJson'); t.value = ${JSON.stringify(JSON.stringify(obj, null, 2))};
    t.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/reliability.html` });
    await until(`!!document.querySelector('#main table') && !!document.getElementById('ruleCheck')`, 'the page');
    const row = await js(`document.querySelector('#main tbody tr')?.innerText.replace(/\\s+/g, ' ') ?? ''`);
    check('the raters’ ceiling is shown per session', /0\.95/.test(row) && /choose a scoring rule/.test(row), row.slice(0, 90));

    const template = JSON.parse(await js(`document.getElementById('ruleJson').value`));
    await setRule({ ...template, rule_id: 'au12-smile', bins: [{ below: 0.5, category: 'neutral' }, { below: null, category: 'grin' }] });
    await until(`/problem/.test(document.getElementById('ruleCheck').innerText)`, 'the refusal');
    const refused = await js(`document.getElementById('ruleCheck').innerText`);
    check('an invalid rule is refused, with its reason', /grin/.test(refused)
      && await js(`document.getElementById('saveRule').disabled`), refused.replace(/\s+/g, ' ').slice(0, 80));

    await setRule({ ...template, rule_id: 'au12-smile', name: 'AU12 over 0.5 is a smile' });
    await until(`/Valid/.test(document.getElementById('ruleCheck').innerText)`, 'a valid rule');
    await js(`document.getElementById('saveRule').click()`);
    await until(`/Saved au12-smile/.test(document.getElementById('saved')?.innerText ?? '')`, 'the save');
    const selected = await js(`document.getElementById('rule').value`);
    check('the rule saves as a version and is selected', /^au12-smile@[0-9a-f]{16}$/.test(selected), selected);

    await until(`/of the ceiling/.test(document.querySelector('#main tbody tr')?.innerText ?? '')`, 'the engine score');
    const scored = await js(`document.querySelector('#main tbody tr td:nth-child(5)').innerText.replace(/\\s+/g, ' ')`);
    check('the engine is scored on the raters’ terms', /^1\.00 raw/.test(scored) && /answered 40 of 40/.test(scored)
      && /ceiling/.test(scored), scored.slice(0, 110));
    await sleep(100);
  } finally {
    proc.kill();
  }
  console.log('\n  RELIABILITY');
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(46)} ${c.detail}`);
  const ok = checks.length && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'RELIABILITY OK' : 'RELIABILITY FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  RELIABILITY: ERROR — ${err.message}\n`); process.exitCode = 2; });

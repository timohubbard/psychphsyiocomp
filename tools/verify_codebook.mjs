#!/usr/bin/env node
/**
 * Drive the codebook builder in headless Chrome, as a researcher would.
 *
 * Run it against a SCRATCH data directory — it saves codebooks and labels:
 *   npm run app -- --data <scratch out> --port 5198
 *   node tools/verify_codebook.mjs --port 5198 --data <scratch out>
 *
 * It checks that a new codebook is refused until its categories are defined
 * and it has moments, with each problem shown where it is fixed; that moments
 * typed, gridded and sampled land as asked (the sample reproducible from its
 * seed); that the preview is the coding page's own buttons; that a saved
 * codebook takes labels keyed the way the coding page keys them; that a
 * changed codebook is a new version which leaves the old one's labels where
 * they were; that the Annotate page offers it; and that a recording that
 * cannot be played says why.
 */
import { existsSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

import { launch } from './cdp.mjs';
import { sampleTimes } from '../web/researcher/codebook_model.js';

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const PORT = Number(opt('port', 5198));
const DATA = resolve(opt('data', ''));

const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok, detail });

async function main() {
  const { proc, page } = await launch({ profileName: 'chrome-codebook-profile', port: 9339 });
  const js = (e) => page.js(e);
  const until = (e, what, ms = 20000) => page.until(e, what, ms);
  const type = (sel, value) => js(`(() => { const el = document.querySelector(${JSON.stringify(sel)});
    el.value = ${JSON.stringify(String(value))}; el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  const click = (sel) => js(`(() => { document.querySelector(${JSON.stringify(sel)}).click(); return true; })()`);
  const status = () => js(`document.getElementById('validity')?.textContent ?? ''`);
  const items = async () => JSON.parse(await js(`document.getElementById('json').value`)).items;
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/codebook.html` });
    await until(`/problem/.test(document.getElementById('validity')?.textContent ?? '')`, 'the builder');
    const flagged = await js(`document.querySelectorAll('.catc.invalid').length`);
    const reasons = await js(`document.querySelector('#side ul.reasons')?.innerText ?? ''`);
    check('a new codebook is refused until defined', flagged === 2 && /no description/.test(reasons) && /no items/.test(reasons),
      `${await status()}; ${flagged} categories flagged`);

    await type('[data-k="codebook_id"]', 'looking-at');
    await type('[data-k="name"]', 'Where is the participant looking?');
    await type('[data-k="cat.0.label"]', 'At the screen');
    await type('[data-k="cat.0.description"]', 'Eyes directed at the monitor, including a glance at its edge.');
    await type('[data-k="cat.1.label"]', 'Away');
    await type('[data-k="cat.1.description"]', 'Eyes directed anywhere other than the monitor, or closed.');
    await sleep(400);   // the JSON pane redraws a beat after typing stops
    const ids = JSON.parse(await js(`document.getElementById('json').value`)).categories.map((c) => c.id);
    check('a category id follows its label', ids.join() === 'at-the-screen,away', ids.join());

    await type('#typeTimes', '0:01, 0:02.5, 3');
    await click('#btnAddTyped');
    await click('[data-addtab="grid"]');
    await type('#gEvery', 1); await type('#gFrom', 4); await type('#gTo', 6);
    await click('#btnAddGrid');
    await click('[data-addtab="random"]');
    await type('#rN', 3); await type('#rFrom', 10); await type('#rTo', 20); await type('#rGap', 1); await type('#rSeed', 5);
    await click('#btnAddRandom');
    const got = await items();
    const expect = [1000, 2500, 3000, 4000, 5000, 6000, ...sampleTimes(10, 20, 3, 1, 5)];
    check('moments land as typed, gridded and sampled', JSON.stringify(got) === JSON.stringify(expect),
      got.map((t) => t / 1000).join(', '));

    await until(`/^Valid/.test(document.getElementById('validity')?.textContent ?? '')`, 'valid');
    const rater = await js(`[...document.querySelectorAll('.rater .cat')].map((b) => b.innerText.replace(/\\s+/g, ' ').trim()).join(' | ')`);
    check('the preview is the coding page’s buttons', /^1 At the screen Eyes directed at the monitor/.test(rater) && /2 Away/.test(rater), rater.slice(0, 70));

    await click('#btnSave');
    await until(`/Saved/.test(document.getElementById('saveResult').textContent)`, 'the save');
    const files = existsSync(join(DATA, 'codebooks')) ? readdirSync(join(DATA, 'codebooks')) : [];
    check('saved as a version file', files.length === 1 && files[0].startsWith('looking-at.'), files.join(', '));

    // Code it exactly as annotate.js does: labels keyed String(item).
    const coded = JSON.parse(await js(`(async () => {
      const [{ codebooks }, { sessions }] = await Promise.all([fetch('/api/codebooks').then((r) => r.json()), fetch('/api/sessions').then((r) => r.json())]);
      const v = codebooks[0];
      const cb = await fetch('/api/codebooks/' + v.codebook_id + '?version=' + v.content_hash).then((r) => r.json());
      const labels = Object.fromEntries(cb.items.map((t) => [String(t), cb.categories[0].id]));
      const res = await fetch('/api/annotations', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ codebook_id: cb.codebook_id, content_hash: cb.content_hash, session_id: sessions[0].session_id, rater_id: 'r1', labels }) });
      const body = await res.json();
      return JSON.stringify({ status: res.status, complete: body.complete, n: body.n_labelled, detail: body.detail ?? null });
    })()`));
    check('it takes labels keyed as the coding page keys them', coded.status === 200 && coded.complete === true,
      `${coded.status} · ${coded.n} labelled${coded.detail ? ` · ${coded.detail}` : ''}`);

    // A changed definition is a new version, and the builder says what stays behind.
    await js(`location.reload()`);
    await until(`document.getElementById('openCb')?.options.length > 1`, 'the list');
    await js(`(() => { const s = document.getElementById('openCb'); s.value = s.options[1].value; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
    await until(`/saved version/.test(document.getElementById('versionLine')?.textContent ?? '')`, 'the opened version');
    await type('[data-k="cat.1.description"]', 'Eyes directed anywhere other than the monitor. Closed eyes are not “away”.');
    await until(`/new version/.test(document.getElementById('versionLine')?.textContent ?? '')`, 'the new-version warning');
    const warn = await js(`document.getElementById('versionLine').textContent`);
    check('editing warns that labels stay with the old version', /1 label set under earlier versions stay/.test(warn), warn.replace(/\s+/g, ' ').slice(0, 90));
    await click('#btnSave');
    await until(`/Saved/.test(document.getElementById('saveResult').textContent)`, 'the second save');
    const list = JSON.parse(await js(`fetch('/api/codebooks').then((r) => r.json()).then((b) => JSON.stringify(b.codebooks))`));
    check('the old version and its labels are kept', list.length === 2 && list.some((v) => v.n_label_sets === 1) && list.some((v) => v.n_label_sets === 0),
      list.map((v) => `${v.content_hash.slice(0, 8)}: ${v.n_label_sets} coded`).join(', '));
    await click('#btnSave');
    await until(`/Unchanged/.test(document.getElementById('saveResult').textContent)`, 'the unchanged save');
    check('saving again without a change makes no version', /Unchanged/.test(await js(`document.getElementById('saveResult').textContent`)));

    // The recording picker says why a recording cannot play (this app has no --media).
    await click('[data-addtab="video"]');
    await js(`(() => { const s = document.getElementById('pickSession'); s.value = s.options[1].value; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
    await until(`!!document.querySelector('#pickHost .note, #pickHost video')`, 'the picker');
    const why = await js(`document.getElementById('pickHost').innerText`);
    check('an unplayable recording says why', /cannot be played: .+/.test(why), why.slice(0, 80));

    await page.send('Page.navigate', { url: `http://localhost:${PORT}/annotate.html` });
    await until(`!!document.getElementById('cb')`, 'the annotate page');
    const offered = await js(`[...document.querySelectorAll('#cb option')].map((o) => o.textContent.trim()).length`);
    check('the Annotate page offers both versions', offered === 2, `${offered} option(s)`);
    await sleep(100);
  } finally {
    proc.kill();
  }
  console.log('\n  CODEBOOK BUILDER');
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(50)} ${c.detail}`);
  const ok = checks.length && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'CODEBOOK BUILDER OK' : 'CODEBOOK BUILDER FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  CODEBOOK BUILDER: ERROR — ${err.message}\n`); process.exitCode = 2; });

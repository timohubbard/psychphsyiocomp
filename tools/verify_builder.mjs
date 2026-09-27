#!/usr/bin/env node
/**
 * Drive the study builder in headless Chrome, as a researcher would.
 *
 * Run it against a SCRATCH studies directory — it saves studies:
 *   npm run app -- --data <scratch out> --studies <scratch studies> --port 5199
 *   node tools/verify_builder.mjs --port 5199 --studies <scratch studies> --stimulus <png>
 *
 * It checks that a participant study is refused until its ethics fields are
 * filled, that a picture uploads and becomes a hashed stimulus item, that the
 * consent preview is the capture page's wording, that the saved file is what
 * was built, and that a study with sessions cannot be edited in place — only
 * saved as a new id.
 */
import { existsSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const opt = (k, d) => { const i = argv.indexOf(`--${k}`); return i >= 0 ? argv[i + 1] : d; };
const PORT = Number(opt('port', 5199));
const STUDIES = resolve(opt('studies', ''));
const STIMULUS = resolve(opt('stimulus', 'studies/stimuli/scene_left.png'));
const USED = opt('used', 'm0');   // a study the scratch out/ has a session under

const checks = [];
const check = (name, ok, detail = '') => checks.push({ name, ok, detail });

async function main() {
  const { proc, page } = await launch({ profileName: 'chrome-builder-profile', port: 9337 });
  const js = (e) => page.js(e);
  const until = (e, what, ms = 20000) => page.until(e, what, ms);
  // Matched by value, not a selector: the attribute holds JSON, quotes and all.
  const setField = (path, value) => js(`(() => {
    const el = [...document.querySelectorAll('[data-path]')]
      .find((e) => e.dataset.path === ${JSON.stringify(JSON.stringify(path))});
    el.value = ${JSON.stringify(value)}; el.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  const validity = () => js(`document.getElementById('validity')?.textContent ?? ''`);
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/builder.html` });
    await until(`!!document.getElementById('validity')`, 'the builder');
    check('a blank study starts valid', /^Valid/.test(await validity()), await validity());

    await js(`(() => { const s = document.getElementById('audience'); s.value = 'participants';
      s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
    const reasons = await js(`document.querySelector('ul.reasons')?.innerText ?? ''`);
    check('participants are refused without the ethics fields',
      /irb_reference/.test(reasons) && /controller/.test(reasons), reasons.split('\n').length + ' reasons');

    await setField(['study_id'], 'builder-demo');
    await setField(['disclosure', 'contact'], 'Dr A. Researcher, a.researcher@uni.ac.uk');
    await setField(['disclosure', 'irb_reference'], 'REC-2026-0099');
    await setField(['disclosure', 'controller'], 'University of Somewhere');
    await setField(['disclosure', 'lawful_basis'], 'UK GDPR Art 6(1)(e)');
    await setField(['disclosure', 'special_category_basis'], 'UK GDPR Art 9(2)(j)');
    check('filled in, it validates', /^Valid/.test(await validity()), await validity());

    // A pictures task, and an upload through the real file input.
    await js(`(() => { document.getElementById('addTask').value = 'stimuli';
      document.getElementById('btnAddTask').click(); return true; })()`);
    const { root } = await page.send('DOM.getDocument', { depth: -1 });
    const { nodeId } = await page.send('DOM.querySelector', { nodeId: root.nodeId, selector: 'input[data-upload]' });
    await page.send('DOM.setFileInputFiles', { nodeId, files: [STIMULUS] });
    await until(`JSON.parse(document.getElementById('json').value).tasks.some((t) => t.type === 'stimuli' && t.items?.length)`,
      'the uploaded stimulus', 20000);
    const built = JSON.parse(await js(`document.getElementById('json').value`));
    const item = built.tasks.find((t) => t.type === 'stimuli').items[0];
    check('the upload became a hashed stimulus item', /^[0-9a-f]{64}$/.test(item.sha256) && item.src.startsWith('stimuli/'),
      `${item.stimulus_id} ${item.src} ${item.sha256.slice(0, 12)}…`);

    const consent = await js(`document.querySelector('.preview')?.innerText ?? ''`);
    check('the consent preview is the capture page’s wording',
      /Automated analysis/.test(consent) && /Responsible for your data: University of Somewhere/.test(consent)
      && /every measurement taken from it/.test(consent), consent.slice(0, 60).replace(/\n/g, ' '));

    await js(`document.getElementById('btnSave').click()`);
    await until(`/Saved|refused|problem/.test(document.getElementById('saveResult').textContent)`, 'the save');
    const saved = join(STUDIES, 'builder-demo.json');
    const file = existsSync(saved) ? JSON.parse(readFileSync(saved, 'utf8')) : null;
    check('saved as built, and indexed', file?.audience === 'participants'
      && file?.disclosure?.irb_reference === 'REC-2026-0099'
      && JSON.parse(readFileSync(join(STUDIES, 'index.json'), 'utf8')).studies.includes('builder-demo'),
      await js(`document.getElementById('saveResult').innerText`));

    // A study with a session under it: fixed. Only a new id.
    await js(`(() => { const s = document.getElementById('startFrom'); s.value = ${JSON.stringify(USED)};
      s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`);
    await until(`JSON.parse(document.getElementById('json').value).study_id === ${JSON.stringify(USED)}`, 'the used study');
    const before = readFileSync(join(STUDIES, `${USED}.json`), 'utf8');
    await js(`document.getElementById('btnSave').click()`);
    await until(`!!document.getElementById('btnSaveAs') || /Saved/.test(document.getElementById('saveResult').textContent)`, 'the refusal');
    const refused = await js(`document.getElementById('saveResult').innerText`);
    check('a study with sessions is not edited in place', /session\(s\) were recorded/.test(refused)
      && readFileSync(join(STUDIES, `${USED}.json`), 'utf8') === before, refused.split('\n')[0]);
    await js(`document.getElementById('btnSaveAs').click()`);
    await until(`/Saved/.test(document.getElementById('saveResult').textContent)`, 'the save as');
    check('it can be saved under the suggested new id', existsSync(join(STUDIES, `${USED}-v2.json`)),
      await js(`document.getElementById('saveResult').innerText.split('\\n')[0]`));
    await sleep(200);
  } finally {
    proc.kill();
  }
  console.log('\n  STUDY BUILDER');
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(52)} ${c.detail}`);
  const ok = checks.length && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'STUDY BUILDER OK' : 'STUDY BUILDER FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  STUDY BUILDER: ERROR — ${err.message}\n`); process.exitCode = 2; });

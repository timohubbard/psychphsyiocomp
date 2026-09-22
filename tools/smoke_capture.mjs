#!/usr/bin/env node
/**
 * End-to-end capture smoke test: real Chrome, fake camera, whole protocol.
 *
 * Why this exists. Unit tests passed while the capture page could not run the
 * study it was given: the dev server's redirect dropped `?study=`, the page
 * fell back to m0, and a four-minute session meant for posed expressions
 * recorded the gaze pilot. Every piece was tested; the page, as a person
 * reaches it, was not. `curl` would not have caught it either — it fetches the
 * paths you name, not the ones the page's JavaScript goes on to request.
 *
 * So this drives the page the way a participant does — through the server's
 * redirect, consent, the camera, every stage, and Download — and then checks
 * the files that come out, which is what the pipeline will see.
 *
 * Chrome's fake capture device supplies the video (a test pattern, no face),
 * so this proves the page RUNS the protocol and records it; it says nothing
 * about measurement quality. Driven over the DevTools protocol with Node's
 * built-in WebSocket — no new dependency.
 *
 * Usage:
 *   node tools/smoke_capture.mjs [--study au-expressions] [--port 5173]
 *                                [--out tempdata/smoke] [--headed]
 * Needs `npm run serve` running.
 */

import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]?.startsWith('--') || all[i + 1] === undefined ? true : all[i + 1]]);
  return acc;
}, []));
const STUDY = args.study ?? 'au-expressions';
const PORT = Number(args.port ?? 5173);
const OUT = resolve(args.out ?? join('tempdata', `smoke-${STUDY}`));
const DEBUG_PORT = 9333;
const TIMEOUT_MS = Number(args['timeout-s'] ?? 900) * 1000;

const CHROME_CANDIDATES = [
  process.env.CHROME,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/usr/bin/google-chrome',
].filter(Boolean);

function log(msg) { console.log(`  ${msg}`); }

async function main() {
  const chrome = CHROME_CANDIDATES.find((p) => existsSync(p));
  if (!chrome) throw new Error('no Chrome found; set CHROME=<path>');

  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });
  const profile = resolve('tempdata', 'chrome-smoke-profile');
  rmSync(profile, { recursive: true, force: true });

  const proc = spawn(chrome, [
    ...(args.headed ? [] : ['--headless=new']),
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${profile}`,
    '--use-fake-device-for-media-stream',
    '--use-fake-ui-for-media-stream',
    '--autoplay-policy=no-user-gesture-required',
    // A backgrounded tab suspends rAF and rVFC entirely (measured on this
    // project), and the clapper waits on a painted frame.
    '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding',
    '--disable-backgrounding-occluded-windows',
    '--window-size=1280,800',
    'about:blank',
  ], { stdio: 'ignore' });

  try {
    const page = await connect();
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    await page.browser.send('Browser.setDownloadBehavior', {
      behavior: 'allow', downloadPath: OUT, eventsEnabled: true,
    });

    const errors = [];
    page.on('Runtime.exceptionThrown', (p) => errors.push(p.exceptionDetails?.exception?.description
      ?? p.exceptionDetails?.text));
    page.on('Runtime.consoleAPICalled', (p) => {
      if (p.type !== 'error') return;
      const text = p.args.map((a) => a.value ?? a.description).join(' ');
      // MediaPipe's WASM build routes its own INFO/WARNING logging to stderr,
      // which the browser surfaces as console.error. Those are not errors;
      // matched by the level prefix MediaPipe writes, not by message text.
      if (/^(INFO|WARNING):/.test(text)) return;
      errors.push(text);
    });

    // Through the server's `/` redirect on purpose: that is the path Tim took,
    // and the one that dropped the query string.
    const url = `http://localhost:${PORT}/?study=${encodeURIComponent(STUDY)}`;
    log(`opening ${url}`);
    await page.send('Page.navigate', { url });

    const js = async (expr) => {
      const r = await page.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
      if (r.exceptionDetails) throw new Error(`page threw: ${r.exceptionDetails.text}`);
      return r.result.value;
    };
    const until = async (expr, what, ms = 30_000) => {
      const end = Date.now() + ms;
      while (Date.now() < end) {
        if (await js(expr).catch(() => false)) return;
        await sleep(250);
      }
      throw new Error(`timed out waiting for ${what}`);
    };

    await until(`document.getElementById('protocolLine')?.textContent.includes('${STUDY}')`,
      `the protocol line to name ${STUDY}`);
    log(`protocol line: ${await js(`document.getElementById('protocolLine').textContent`)}`);

    await js(`document.getElementById('btnEnable').click()`);
    await until(`!!document.getElementById('consentGo')`, 'the consent screen');
    const consentText = await js(`document.querySelector('.consent-panel').innerText`);
    log(`consent: ${consentText.split('\n').find((l) => l.startsWith('This session')) ?? '(no summary line)'}`);
    await js(`(() => {
      const r = document.querySelector('input[name="tier"]:checked') ?? document.querySelector('input[name="tier"]');
      r.checked = true;
      document.getElementById('consentUnderstood').checked = true;
      document.getElementById('consentGo').click();
    })()`);

    // The live engine loads MediaPipe from a CDN; allow for a cold cache.
    await until(`!document.getElementById('btnStart').disabled`, 'the camera and live engine', 90_000);
    log('camera up; starting the session');
    await js(`document.getElementById('btnStart').click()`);

    // Walk the protocol: press space whenever an instruction is waiting, and
    // let timed stages run. Chinrest screens, if the study has them, need a
    // human and fail the smoke test by timing out — which is correct for a
    // protocol that does not list the chinrest.
    const started = Date.now();
    let lastStage = '';
    while (Date.now() - started < TIMEOUT_MS) {
      const s = await js(`({
        done: document.getElementById('donePanel').style.display === 'block',
        stage: document.getElementById('hudStage')?.textContent ?? '',
        waiting: document.getElementById('stageText').style.display === 'block'
          && /Press/.test(document.getElementById('stageText').innerText),
        chinrest: !!document.querySelector('.chinrest'),
      })`);
      if (s.done) break;
      if (s.chinrest) throw new Error('a chinrest screen appeared, which this driver cannot complete');
      if (s.stage !== lastStage) { log(`stage ${s.stage}`); lastStage = s.stage; }
      if (s.waiting) {
        await sleep(1400);   // past the instruction's minimum display time
        await page.send('Input.dispatchKeyEvent', { type: 'keyDown', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
        await page.send('Input.dispatchKeyEvent', { type: 'keyUp', code: 'Space', key: ' ', windowsVirtualKeyCode: 32 });
      }
      await sleep(400);
    }
    if (!(await js(`document.getElementById('donePanel').style.display === 'block'`))) {
      throw new Error(`session did not finish within ${TIMEOUT_MS / 1000}s (last stage ${lastStage})`);
    }
    log(`session finished in ${Math.round((Date.now() - started) / 1000)}s`);

    await js(`document.getElementById('btnDownload').click()`);
    await untilFiles(OUT, ['session.json', 'browser_chunks.json'], 60_000);
    await sleep(3000);   // the video blob is the largest and lands last

    const report = checkOutput(OUT, STUDY);
    if (errors.length) report.failures.push(`page errors: ${errors.slice(0, 5).join(' | ')}`);
    printReport(report);
    process.exitCode = report.failures.length ? 1 : 0;
  } finally {
    proc.kill();
  }
}

async function untilFiles(dir, names, ms) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    const have = readdirSync(dir);
    if (names.every((n) => have.includes(n))) return;
    await sleep(250);
  }
  throw new Error(`downloads did not arrive: wanted ${names.join(', ')}, have ${readdirSync(dir).join(', ')}`);
}

/** Assertions on what the pipeline will actually receive. */
export function checkOutput(dir, studyId) {
  const failures = [];
  const facts = {};
  const session = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8'));
  facts.study_id = session.study_id;
  if (session.study_id !== studyId) failures.push(`session ran ${session.study_id}, not ${studyId}`);

  const events = session.events ?? [];
  const count = (t) => events.filter((e) => e.event_type === t).length;
  facts.events = events.length;
  facts.sync_clappers = count('sync_clapper');
  if (facts.sync_clappers !== 2) failures.push(`${facts.sync_clappers} sync clappers, expected 2`);

  const holds = events.filter((e) => e.event_type === 'expression_hold');
  facts.expression_holds = holds.length;
  if (studyId === 'au-expressions') {
    if (holds.length !== 20) failures.push(`${holds.length} expression holds, expected 20`);
    const bad = holds.filter((e) => !Array.isArray(e.metadata?.target_aus) || !e.metadata.target_aus.length
      || e.offset_native_ts == null || e.offset_native_ts <= e.onset_native_ts);
    if (bad.length) failures.push(`${bad.length} holds without target AUs or a closed span`);
    const spans = holds.map((e) => e.offset_native_ts - e.onset_native_ts);
    facts.hold_ms = spans.length ? `${Math.min(...spans).toFixed(0)}-${Math.max(...spans).toFixed(0)}` : null;
    if (events.some((e) => e.event_type === 'calibration_point')) failures.push('calibration ran in a face-only study');
    if (session.geometry?.reason !== 'not_in_protocol') failures.push(`geometry reason ${session.geometry?.reason}, expected not_in_protocol`);
  }

  const video = readdirSync(dir).find((f) => /^capture\.(webm|mp4)$/.test(f));
  facts.video = video ? `${video} ${(statSync(join(dir, video)).size / 1e6).toFixed(1)} MB` : null;
  if (!video) failures.push('no video downloaded');
  else if (statSync(join(dir, video)).size < 100_000) failures.push('video is implausibly small');
  return { facts, failures };
}

function printReport({ facts, failures }) {
  console.log('\n  SMOKE CAPTURE');
  console.log('  ' + '-'.repeat(60));
  for (const [k, v] of Object.entries(facts)) console.log(`  ${k.padEnd(18)} ${v}`);
  console.log('  ' + '-'.repeat(60));
  console.log(failures.length ? `  FAIL\n${failures.map((f) => `    - ${f}`).join('\n')}` : '  PASS');
  console.log();
}

/** Attach to the first page target and to the browser, over CDP. */
async function connect() {
  let version;
  for (let i = 0; i < 60 && !version; i += 1) {
    try { version = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/version`)).json(); } catch { await sleep(250); }
  }
  if (!version) throw new Error('Chrome did not open its debugging port');
  const targets = await (await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`)).json();
  const pageTarget = targets.find((t) => t.type === 'page');
  const page = await cdp(pageTarget.webSocketDebuggerUrl);
  page.browser = await cdp(version.webSocketDebuggerUrl);
  return page;
}

function cdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  const handlers = new Map();
  ws.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) {
      const { ok, fail } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) fail(new Error(`${msg.error.message} (${msg.error.code})`));
      else ok(msg.result);
    } else if (msg.method) {
      for (const h of handlers.get(msg.method) ?? []) h(msg.params);
    }
  };
  const open = new Promise((ok, fail) => { ws.onopen = ok; ws.onerror = fail; });
  return {
    async send(method, params = {}) {
      await open;
      id += 1;
      const myId = id;
      ws.send(JSON.stringify({ id: myId, method, params }));
      return new Promise((ok, fail) => pending.set(myId, { ok, fail }));
    },
    on(method, h) { handlers.set(method, [...(handlers.get(method) ?? []), h]); },
  };
}

if (process.argv[1]?.replace(/\\/g, '/').endsWith('tools/smoke_capture.mjs')) {
  main().catch((err) => { console.error(`\n  SMOKE CAPTURE: ERROR — ${err.message}\n`); process.exitCode = 2; });
}

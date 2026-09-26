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
 * Studies with the chinrest (m0) are driven through it with a known truth —
 * see smoke_chinrest.mjs — and the recorded geometry is checked against it.
 *
 * Usage:
 *   node tools/smoke_capture.mjs [--study au-expressions|m0] [--port 5173]
 *                                [--out tempdata/smoke] [--headed]
 * Needs `npm run serve` running.
 */

import { mkdirSync, readdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';

import { launch } from './cdp.mjs';
import { driveChinrest } from './smoke_chinrest.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]?.startsWith('--') || all[i + 1] === undefined ? true : all[i + 1]]);
  return acc;
}, []));
const STUDY = args.study ?? 'au-expressions';
const PORT = Number(args.port ?? 5173);
const OUT = resolve(args.out ?? join('tempdata', `smoke-${STUDY}`));
const TIMEOUT_MS = Number(args['timeout-s'] ?? 900) * 1000;


function log(msg) { console.log(`  ${msg}`); }

async function main() {
  rmSync(OUT, { recursive: true, force: true });
  mkdirSync(OUT, { recursive: true });

  const { proc, page, browser } = await launch({
    headed: !!args.headed, profileName: 'chrome-smoke-profile',
    extraArgs: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  });

  try {
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    await browser.send('Browser.setDownloadBehavior', {
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

    const js = (expr) => page.js(expr);
    const until = (expr, what, ms) => page.until(expr, what, ms);

    await until(`document.getElementById('protocolLine')?.textContent.includes('${STUDY}')`,
      `the protocol line to name ${STUDY}`);
    log(`protocol line: ${await js(`document.getElementById('protocolLine').textContent`)}`);
    const selfTestBanner = await js(`!!document.getElementById('selfTestBanner')`);

    await js(`document.getElementById('btnEnable').click()`);
    await until(`!!document.getElementById('consentGo')`, 'the consent screen');
    const consentText = await js(`document.querySelector('.consent-panel').innerText`);
    const consentWarnsSelfTest = /Developer self-test/.test(consentText);
    const consentHas = {
      analysis: /Automated analysis\. Software analyses the recording automatically/.test(consentText),
      withdrawal: /Changing your mind:.*every measurement taken from it/s.test(consentText),
    };
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
    // let timed stages run. The chinrest, if the study has it, is driven once
    // with a known truth (smoke_chinrest.mjs) so the geometry can be checked.
    const started = Date.now();
    let lastStage = '';
    let chinrest = null;
    while (Date.now() - started < TIMEOUT_MS) {
      const s = await js(`({
        done: document.getElementById('donePanel').style.display === 'block',
        stage: document.getElementById('hudStage')?.textContent ?? '',
        waiting: document.getElementById('stageText').style.display === 'block'
          && /Press/.test(document.getElementById('stageText').innerText),
        chinrest: !!document.querySelector('.chinrest'),
      })`);
      if (s.done) break;
      if (s.chinrest) {
        if (chinrest) throw new Error('the chinrest appeared a second time');
        chinrest = await driveChinrest(page, { log });
        continue;
      }
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

    const withdrawCode = await js(`document.getElementById('withdrawCode')?.innerText ?? ''`);
    await js(`document.getElementById('btnDownload').click()`);
    await untilFiles(OUT, ['session.json', 'browser_chunks.json'], 60_000);
    await sleep(3000);   // the video blob is the largest and lands last

    const report = checkOutput(OUT, STUDY, { chinrest });
    // Every shipped study is a developer self-test; the operator and the
    // participant must both be told so on screen, not just in the manifest.
    // The consent wording awaiting sign-off (README): on screen, in the
    // record, and the session code it tells participants to quote.
    if (!consentHas.analysis) report.failures.push('no automated-analysis notice on the consent screen');
    if (!consentHas.withdrawal) report.failures.push('no withdrawal paragraph on the consent screen');
    const consent = JSON.parse(readFileSync(join(OUT, 'session.json'), 'utf8')).consent ?? {};
    if (!consent.analysis_notice || !consent.withdrawal) {
      report.failures.push('the consent record does not store the notice and withdrawal text');
    }
    if (!withdrawCode.includes(report.facts.session_id)) {
      report.failures.push('the end screen does not show the session code to quote');
    }
    if (report.facts.audience === 'developer') {
      if (!selfTestBanner) report.failures.push('no DEVELOPER SELF-TEST line under the protocol');
      if (!consentWarnsSelfTest) report.failures.push('the consent screen does not say this is a self-test');
    }
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
export function checkOutput(dir, studyId, { chinrest = null } = {}) {
  const failures = [];
  const facts = {};
  const session = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8'));
  facts.study_id = session.study_id;
  facts.session_id = session.session_id;
  if (session.study_id !== studyId) failures.push(`session ran ${session.study_id}, not ${studyId}`);
  facts.audience = session.study?.audience ?? null;
  if (!facts.audience) failures.push('the session does not record its audience');
  if (session.consent?.audience !== facts.audience) {
    failures.push(`consent record audience ${session.consent?.audience} differs from the study's`);
  }

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

  if (studyId === 'm0' || studyId === 'in-browser-example') {
    // Both run the chinrest, the 13-point calibration and 5-point validation.
    const g = session.geometry ?? {};
    facts.geometry = g.ok ? `${(g.viewing_distance_mm / 10).toFixed(1)} cm at ${g.px_per_mm?.toFixed(3)} px/mm`
      : `refused (${g.reason})`;
    if (!g.ok) failures.push(`chinrest geometry refused: ${g.reason} ${g.detail ?? ''}`);
    else if (chinrest) {
      // The driver chose the truth; the page must recover it. ±10% on distance
      // covers the ±2 px jitter and the one-frame (2 px) marking granularity.
      if (Math.abs(g.px_per_mm - chinrest.pxPerMm) > 0.02) {
        failures.push(`px/mm ${g.px_per_mm} vs the ${chinrest.pxPerMm.toFixed(3)} the card was sized to`);
      }
      if (Math.abs(g.viewing_distance_mm - chinrest.distanceMm) > chinrest.distanceMm * 0.1) {
        failures.push(`viewing distance ${g.viewing_distance_mm.toFixed(0)} mm vs the ${chinrest.distanceMm} mm driven`);
      }
    } else failures.push('m0 ran without the chinrest being driven');
    facts.calibration_points = count('calibration_point');
    facts.validation_points = count('validation_point');
    if (facts.calibration_points !== 13) failures.push(`${facts.calibration_points} calibration points, expected 13`);
    if (facts.validation_points !== 5) failures.push(`${facts.validation_points} validation points, expected 5`);
  }

  if (studyId === 'm0') {
    // m0 alone has the speech stages and the microphone.
    for (const t of ['fixation', 'speech_read', 'speech_free']) {
      if (count(t) !== 1) failures.push(`${count(t)} ${t} events, expected 1`);
    }
    const mime = events.find((e) => e.event_type === 'recording_start')?.metadata?.mimeType ?? '';
    facts.mime = mime;
    if (!/opus/.test(mime)) failures.push(`recording ${mime} has no audio codec — m0 needs the microphone`);
  }

  const video = readdirSync(dir).find((f) => /^capture\.(webm|mp4)$/.test(f));
  facts.video = video ? `${video} ${(statSync(join(dir, video)).size / 1e6).toFixed(1)} MB` : null;
  facts.tier = session.consent?.tier ?? null;

  if (facts.tier === 'features_in_browser') {
    // The participant was told the video never leaves the device: there must
    // be no recording at all, and the gaze features must be in the chunks.
    if (video) failures.push(`${video} was downloaded under features_in_browser`);
    const start = events.find((e) => e.event_type === 'recording_start');
    if (start?.metadata?.media_recorded !== false) {
      failures.push('recording_start does not say that no media was recorded');
    }
    const chunks = JSON.parse(readFileSync(join(dir, 'browser_chunks.json'), 'utf8'));
    facts.gaze_chunks = chunks.filter((c) => c.source?.startsWith('gaze.mediapipe_features')).length;
    if (!facts.gaze_chunks) failures.push('no browser gaze-feature chunks — gaze would be unmeasurable');
  } else if (!video) failures.push('no video downloaded');
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

if (process.argv[1]?.replace(/\\/g, '/').endsWith('tools/smoke_capture.mjs')) {
  main().catch((err) => { console.error(`\n  SMOKE CAPTURE: ERROR — ${err.message}\n`); process.exitCode = 2; });
}

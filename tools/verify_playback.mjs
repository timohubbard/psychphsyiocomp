#!/usr/bin/env node
/**
 * Does a session's recording actually PLAY from the researcher app?
 *
 * The annotation page shows a coder a moment of video and asks them to label
 * it. Everything around the video was verified; the video itself was not,
 * because the Chrome extension used for browser checks refused to load any
 * media element at all. A MediaRecorder WebM has no duration and no cue index,
 * and Chrome's response to that is to sit at readyState 0 forever — which
 * looks like a slow network, not a broken file. The app remuxes it
 * (engine_contract.prepare_playback) and serves byte ranges over HTTP/1.1;
 * this checks that the result plays in Chrome's real media stack.
 *
 * It loads /api/sessions/<id>/media into a <video> exactly as annotate.js does
 * and asserts, in order: metadata loads with a finite duration; a frame decodes
 * (videoWidth > 0); a seek deep into the file lands where asked; playback then
 * advances. Each is a distinct way the path has failed or could fail.
 *
 * Usage:
 *   npm run app -- --media tempdata      (in another terminal)
 *   node tools/verify_playback.mjs <session_id> [--port 5174] [--seek-s 120]
 */

import { setTimeout as sleep } from 'node:timers/promises';

import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const sessionId = argv.find((a) => !a.startsWith('--'));
const opt = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : dflt;
};
const PORT = Number(opt('port', 5174));
const SEEK_S = Number(opt('seek-s', 120));

async function main() {
  if (!sessionId) throw new Error('usage: verify_playback.mjs <session_id>');
  const { proc, page } = await launch({ profileName: 'chrome-playback-profile', port: 9334 });
  const checks = [];
  const check = (name, ok, detail) => { checks.push({ name, ok, detail }); };
  try {
    await page.send('Runtime.enable');
    // Same origin as the app, so the page's fetches and the media request are
    // exactly what annotate.js would issue.
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/` });
    // Wait for the NEW document, not just a complete one: about:blank is
    // already "complete", and a probe created there would resolve its
    // relative src against the wrong document.
    await page.until(`location.origin === 'http://localhost:${PORT}' && document.readyState === 'complete'`,
      'the app to load');

    // --src overrides the source, for controls. A first attempt at a negative
    // control (the raw, un-remuxed MediaRecorder file from a stub server) was
    // rejected by Chrome with "URL safety check" for a reason unrelated to the
    // file, so it is not yet a working control — the readyState-0 failure the
    // remux exists for was observed in real Chrome in an earlier session.
    const src = opt('src', `/api/sessions/${encodeURIComponent(sessionId)}/media`);
    await page.js(`(() => {
      const v = document.createElement('video');
      v.id = '__probe'; v.muted = true; v.preload = 'metadata'; v.playsInline = true;
      window.__probeErr = null;
      v.addEventListener('error', () => { window.__probeErr = v.error && v.error.message || String(v.error && v.error.code); });
      v.src = ${JSON.stringify(src)};
      document.body.appendChild(v);
    })()`);

    const v = (expr) => page.js(`(() => { const v = document.getElementById('__probe'); return ${expr}; })()`);

    await page.until(`(() => { const v = document.getElementById('__probe'); return v.readyState >= 1 || window.__probeErr; })()`,
      'metadata', 60_000).catch(() => {});
    const err = await page.js('window.__probeErr');
    const duration = await v('v.duration');
    check('metadata loads with a finite duration', !err && Number.isFinite(duration) && duration > 0,
      err ? `media error: ${err}` : `duration ${Number(duration).toFixed(1)} s`);

    await v('(v.play(), true)');
    await page.until(`document.getElementById('__probe').videoWidth > 0`, 'a decoded frame', 30_000).catch(() => {});
    const w = await v('v.videoWidth'); const h = await v('v.videoHeight');
    check('a frame decodes', w > 0, `${w}x${h}`);

    const target = Math.min(SEEK_S, Math.max(0, (Number(duration) || 0) - 5));
    await v(`(v.pause(), v.currentTime = ${target}, true)`);
    await page.until(`(() => { const v = document.getElementById('__probe'); return !v.seeking && v.readyState >= 2; })()`,
      'the seek to settle', 30_000).catch(() => {});
    const landed = await v('v.currentTime');
    check(`a seek to ${target.toFixed(0)} s lands there`, Math.abs(landed - target) < 1.0,
      `currentTime ${Number(landed).toFixed(2)} s`);

    const before = await v('v.currentTime');
    await v('(v.play(), true)');
    await sleep(2500);
    const after = await v('v.currentTime');
    check('playback advances', after - before > 1.0, `${Number(before).toFixed(2)} -> ${Number(after).toFixed(2)} s in 2.5 s`);
  } finally {
    proc.kill();
  }

  console.log(`\n  PLAYBACK  ${sessionId}`);
  console.log('  ' + '-'.repeat(60));
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(36)} ${c.detail}`);
  const ok = checks.length === 4 && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'PLAYBACK OK' : 'PLAYBACK FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

main().catch((err) => { console.error(`\n  PLAYBACK: ERROR — ${err.message}\n`); process.exitCode = 2; });

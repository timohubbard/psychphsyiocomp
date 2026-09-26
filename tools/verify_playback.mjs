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
 * --control is the check on the check. A probe that passes everything proves
 * nothing until it has been seen to FAIL on the file the remux exists to fix.
 * Headless Chrome records a fresh MediaRecorder WebM from an animated canvas
 * (no participant data involved), the same remux produces the playable copy,
 * and both are probed from one throwaway same-origin server. The control holds
 * only if the raw file fails "finite duration" AND the remux passes all four.
 * The first attempt at this served the raw file from a separate stub origin
 * and Chrome refused it with "URL safety check" before any media code ran;
 * one origin for page and files removes that variable.
 *
 * Usage:
 *   npm run app -- --media tempdata      (in another terminal)
 *   node tools/verify_playback.mjs <session_id> [--port 5174] [--seek-s 120]
 *   node tools/verify_playback.mjs --control
 */

import { spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve, dirname } from 'node:path';
import { setTimeout as sleep } from 'node:timers/promises';
import { fileURLToPath } from 'node:url';

import { launch } from './cdp.mjs';
import { sendFile } from './static.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const argv = process.argv.slice(2);
const sessionId = argv.find((a) => !a.startsWith('--'));
const opt = (name, dflt) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 ? argv[i + 1] : dflt;
};
const CONTROL = argv.includes('--control');
const PORT = Number(opt('port', 5174));
const SEEK_S = Number(opt('seek-s', 120));
const CONTROL_RECORD_S = 12;

/** The four checks, against one src, in a page already on the right origin. */
async function probe(page, src, seekS) {
  const checks = [];
  const check = (name, ok, detail) => { checks.push({ name, ok, detail }); };

  await page.js(`(() => {
    document.getElementById('__probe')?.remove();
    const v = document.createElement('video');
    v.id = '__probe'; v.muted = true; v.preload = 'metadata'; v.playsInline = true;
    window.__probeErr = null;
    v.addEventListener('error', () => { window.__probeErr = v.error && v.error.message || String(v.error && v.error.code); });
    v.src = ${JSON.stringify(src)};
    document.body.appendChild(v);
  })()`);

  const v = (expr) => page.js(`(() => { const v = document.getElementById('__probe'); return ${expr}; })()`);

  await page.until(`(() => { const v = document.getElementById('__probe'); return v.readyState >= 1 || window.__probeErr; })()`,
    'metadata', CONTROL ? 15_000 : 60_000).catch(() => {});
  const err = await page.js('window.__probeErr');
  const duration = await v('v.duration');
  check('metadata loads with a finite duration', !err && Number.isFinite(duration) && duration > 0,
    err ? `media error: ${err}` : `duration ${Number(duration).toFixed(1)} s, readyState ${await v('v.readyState')}`);

  await v('(v.play().catch(() => {}), true)');
  await page.until(`document.getElementById('__probe').videoWidth > 0`, 'a decoded frame', CONTROL ? 10_000 : 30_000).catch(() => {});
  const w = await v('v.videoWidth'); const h = await v('v.videoHeight');
  check('a frame decodes', w > 0, `${w}x${h}`);

  const finite = Number.isFinite(duration) ? duration : 0;
  const target = Math.min(seekS, Math.max(0, finite - 5));
  await v(`(v.pause(), v.currentTime = ${target}, true)`);
  await page.until(`(() => { const v = document.getElementById('__probe'); return !v.seeking && v.readyState >= 2; })()`,
    'the seek to settle', CONTROL ? 10_000 : 30_000).catch(() => {});
  const landed = await v('v.currentTime');
  check(`a seek to ${target.toFixed(0)} s lands there`, target > 0 && Math.abs(landed - target) < 1.0,
    `currentTime ${Number(landed).toFixed(2)} s`);

  const before = await v('v.currentTime');
  await v('(v.play().catch(() => {}), true)');
  await sleep(2500);
  const after = await v('v.currentTime');
  check('playback advances', after - before > 1.0, `${Number(before).toFixed(2)} -> ${Number(after).toFixed(2)} s in 2.5 s`);
  return checks;
}

function report(title, checks) {
  console.log(`\n  ${title}`);
  console.log('  ' + '-'.repeat(60));
  for (const c of checks) console.log(`  [${c.ok ? 'PASS' : 'FAIL'}]  ${c.name.padEnd(36)} ${c.detail}`);
}

async function session() {
  if (!sessionId) throw new Error('usage: verify_playback.mjs <session_id> | --control');
  const { proc, page } = await launch({ profileName: 'chrome-playback-profile', port: 9334 });
  let checks;
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
    checks = await probe(page, opt('src', `/api/sessions/${encodeURIComponent(sessionId)}/media`), SEEK_S);
  } finally {
    proc.kill();
  }
  report(`PLAYBACK  ${sessionId}`, checks);
  const ok = checks.length === 4 && checks.every((c) => c.ok);
  console.log(`\n  ${ok ? 'PLAYBACK OK' : 'PLAYBACK FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

/** A throwaway server: the probe page, an upload sink, and the two files. */
function controlServer(dir) {
  const server = createServer(async (req, res) => {
    try {
      if (req.url === '/probe.html') {
        res.writeHead(200, { 'Content-Type': 'text/html' }).end('<!doctype html><body></body>');
      } else if (req.method === 'POST' && req.url === '/upload') {
        const parts = [];
        for await (const c of req) parts.push(c);
        writeFileSync(join(dir, 'raw.webm'), Buffer.concat(parts));
        res.writeHead(204).end();
      } else if (req.url === '/raw.webm' || req.url === '/remuxed.webm') {
        await sendFile(req, res, join(dir, req.url.slice(1)));
      } else {
        res.writeHead(404).end();
      }
    } catch (err) {
      res.writeHead(500).end(String(err));
    }
  });
  return new Promise((ok) => server.listen(0, '127.0.0.1', () => ok(server)));
}

async function control() {
  const dir = mkdtempSync(join(tmpdir(), 'playback-control-'));
  const server = await controlServer(dir);
  const origin = `http://127.0.0.1:${server.address().port}`;
  const { proc, page } = await launch({ profileName: 'chrome-playback-control', port: 9335 });
  let raw;
  let remuxed;
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `${origin}/probe.html` });
    await page.until(`location.origin === ${JSON.stringify(origin)} && document.readyState === 'complete'`, 'the probe page');

    // Record the way recorder.js does — MediaRecorder, 1 s timeslice — from a
    // moving canvas, so there is something to decode and something to seek to.
    const bytes = await page.js(`(async () => {
      const c = document.createElement('canvas'); c.width = 320; c.height = 240;
      document.body.appendChild(c);
      const g = c.getContext('2d');
      let t = 0; let run = true;
      const draw = () => { g.fillStyle = 'hsl(' + (t++ % 360) + ',70%,50%)'; g.fillRect(0, 0, 320, 240);
        g.fillStyle = '#fff'; g.fillRect((t * 3) % 320, 100, 20, 20); if (run) requestAnimationFrame(draw); };
      draw();
      const type = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m));
      const rec = new MediaRecorder(c.captureStream(30), { mimeType: type });
      const chunks = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      const done = new Promise((ok) => { rec.onstop = ok; });
      rec.start(1000);
      await new Promise((ok) => setTimeout(ok, ${CONTROL_RECORD_S * 1000}));
      rec.stop(); await done; run = false;
      const blob = new Blob(chunks, { type });
      await fetch('/upload', { method: 'POST', body: blob });
      return blob.size;
    })()`);
    if (!bytes) throw new Error('the control recording is empty');

    const remux = spawnSync(process.execPath, [join(ROOT, 'tools', 'py.mjs'), 'tools/remux.py',
      join(dir, 'raw.webm'), join(dir, 'remuxed.webm')], { encoding: 'utf8' });
    if (remux.status !== 0) throw new Error(`remux failed: ${remux.stderr || remux.stdout}`);

    const seek = CONTROL_RECORD_S / 2;
    raw = await probe(page, '/raw.webm', seek);
    remuxed = await probe(page, '/remuxed.webm', seek);
  } finally {
    proc.kill();
    server.close();
    rmSync(dir, { recursive: true, force: true });
  }

  report('CONTROL  raw MediaRecorder WebM (must fail)', raw);
  report('CONTROL  the same file, remuxed (must pass)', remuxed);
  const rawFails = !raw[0].ok;
  const remuxPasses = remuxed.every((c) => c.ok);
  const ok = rawFails && remuxPasses;
  console.log(`\n  raw file fails "finite duration": ${rawFails ? 'yes' : 'NO — the probe cannot tell the difference'}`);
  console.log(`  remuxed file passes all four:     ${remuxPasses ? 'yes' : 'NO'}`);
  console.log(`\n  ${ok ? 'CONTROL OK — the probe distinguishes a broken file from a fixed one' : 'CONTROL FAILED'}\n`);
  process.exitCode = ok ? 0 : 1;
}

(CONTROL ? control() : session())
  .catch((err) => { console.error(`\n  PLAYBACK: ERROR — ${err.message}\n`); process.exitCode = 2; });

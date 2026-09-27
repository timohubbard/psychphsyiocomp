#!/usr/bin/env node
/**
 * Does the browser's video time agree with the engines' frame times?
 *
 * Human labels are made at `video.currentTime` in the coding page; engines
 * stamp frames with the container's own timestamps (OpenCV POS_MSEC). The
 * scoring rules (server/scoring_rules.py) convert a coded moment to the master
 * clock with the session's recording-clock solution, which is only right if
 * those two times are the same number for the same frame.
 *
 * The sync flash is the known answer: the aligner placed each flash on the
 * recording clock from the video frames themselves. So this plays the copy the
 * coding page plays, predicts each flash's time from the solution, and steps
 * frame by frame around it measuring luminance. The first bright frame must
 * land within one frame of the prediction.
 *
 * Usage (app running with the media folder):
 *   npm run app -- --media tempdata --port 5199
 *   node tools/verify_pts_origin.mjs <session_id> [--port 5199]
 */
import { launch } from './cdp.mjs';

const argv = process.argv.slice(2);
const session = argv.find((a) => !a.startsWith('--'));
const i = argv.indexOf('--port');
const PORT = Number(i >= 0 ? argv[i + 1] : 5199);

async function main() {
  if (!session) throw new Error('usage: verify_pts_origin.mjs <session_id>');
  const { proc, page } = await launch({ profileName: 'chrome-pts-profile', port: 9343 });
  try {
    await page.send('Runtime.enable');
    await page.send('Page.navigate', { url: `http://localhost:${PORT}/annotate.html` });
    await page.until(`document.readyState === 'complete'`, 'the app');
    const r = JSON.parse(await page.js(`(async () => {
      const d = await fetch('/api/sessions/${encodeURIComponent(session)}').then((x) => x.json());
      const run = (d.runs ?? []).find((x) => x.clock_id === 'video_pts' && x.status === 'ok' && x.clock_rate);
      if (!run) return JSON.stringify({ refusal: 'no recording-clock solution for this session' });
      const flashes = (d.events ?? []).filter((e) => e.event_type === 'sync_clapper' && e.onset != null).map((e) => e.onset);
      const v = document.createElement('video');
      v.muted = true; v.preload = 'auto'; v.src = '/api/sessions/${encodeURIComponent(session)}/media';
      document.body.append(v);
      await new Promise((ok, bad) => { v.onloadedmetadata = ok; v.onerror = () => bad(new Error('media refused')); });
      const c = document.createElement('canvas'); c.width = 64; c.height = 36;
      const g = c.getContext('2d', { willReadFrequently: true });
      const luma = async (t) => {
        await new Promise((ok) => { v.onseeked = ok; v.currentTime = Math.max(0, t); });
        g.drawImage(v, 0, 0, 64, 36);
        const px = g.getImageData(0, 0, 64, 36).data;
        let s = 0; for (let k = 0; k < px.length; k += 4) s += 0.299 * px[k] + 0.587 * px[k + 1] + 0.114 * px[k + 2];
        return s / (px.length / 4);
      };
      const fps = d.meta?.achieved_fps || 30;
      const step = 1 / fps;
      const out = [];
      for (const m of flashes) {
        const pred = (m - run.clock_offset_ms) / run.clock_rate / 1000;
        // The frames before the flash give both the level and its frame-to-
        // frame noise; a flash is a rise well above that noise, whatever the
        // room's brightness (a bright room shows a smaller absolute rise).
        const before = [];
        for (let t = pred - 0.6; t <= pred - 0.25; t += step) before.push(await luma(t));
        const dark = before.reduce((a, b) => a + b, 0) / before.length;
        const noise = Math.sqrt(before.reduce((a, b) => a + (b - dark) ** 2, 0) / before.length);
        const profile = [];
        for (let t = pred - 4 * step; t <= pred + 6 * step; t += step / 2) profile.push([t, await luma(t)]);
        const peak = Math.max(...profile.map((p) => p[1]));
        const half = dark + (peak - dark) / 2;
        const first = profile.find((p) => p[1] >= half);
        out.push({ predicted_s: pred, dark, noise, peak, first_bright_s: first ? first[0] : null,
                   error_ms: first ? (first[0] - pred) * 1000 : null, frame_ms: step * 1000 });
      }
      return JSON.stringify({ duration_s: v.duration, offset_ms: run.clock_offset_ms, rate: run.clock_rate, flashes: out });
    })()`, 120000));
    console.log(`\n  PTS ORIGIN  ${session}`);
    if (r.refusal) {
      console.log(`  REFUSED: ${r.refusal}\n`);
      process.exitCode = 1;
      return;
    }
    console.log(`  recording clock: master = video × ${r.rate.toFixed(6)} + ${r.offset_ms.toFixed(1)} ms`);
    let ok = r.flashes.length > 0;
    for (const f of r.flashes) {
      // A flash was found (a rise of 6x the pre-flash noise, and at least 5
      // levels), and its first bright frame is within one frame of prediction.
      const found = f.peak - f.dark > Math.max(5, 6 * f.noise);
      const pass = found && f.error_ms !== null && Math.abs(f.error_ms) <= f.frame_ms;
      ok = ok && pass;
      console.log(`  [${pass ? 'PASS' : 'FAIL'}]  flash predicted at ${f.predicted_s.toFixed(3)} s, first bright frame `
        + `${f.first_bright_s === null ? 'not found' : `${f.first_bright_s.toFixed(3)} s (${f.error_ms >= 0 ? '+' : ''}${f.error_ms.toFixed(0)} ms)`}`
        + `, luma ${f.dark.toFixed(0)} (noise ${f.noise.toFixed(1)}) → ${f.peak.toFixed(0)}, one frame = ${f.frame_ms.toFixed(0)} ms`);
    }
    console.log(`\n  ${ok ? 'PTS ORIGIN OK — the coding page and the engines count time from the same zero'
      : 'PTS ORIGIN FAILED — engine scores against these labels would be misaligned'}\n`);
    process.exitCode = ok ? 0 : 1;
  } finally {
    proc.kill();
  }
}

main().catch((err) => { console.error(`\n  PTS ORIGIN: ERROR — ${err.message}\n`); process.exitCode = 2; });

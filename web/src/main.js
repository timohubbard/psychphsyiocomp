/**
 * Capture page runner.
 *
 * Drives the stimulus sequence, records media, logs events on the master
 * clock, and runs the live in-browser engine for participant feedback.
 *
 * The live engine's output is NOT the record. It exists so the participant and
 * the experimenter can see that the camera is working; the authoritative pass
 * runs server-side over the stored video, where it can be re-run with a better
 * engine later (REPORT.md §2.2).
 */

import { SessionRecorder } from './recorder.js';
import { now, stamp } from './clock.js';
import {
  buildM0Sequence, TIMINGS, wait, stageLabel, estimateDurationMs,
} from './sequence.js';
import { MediaPipeBlendshapesLive } from '../../engines/face.mediapipe_blendshapes/browser/engine.js';
import { runVirtualChinrest, CHINREST_CSS } from './chinrest-ui.js';
import { stimulusSizeErrorFraction } from './chinrest.js';

const el = (id) => document.getElementById(id);

const ui = {
  setupPanel: el('setupPanel'), donePanel: el('donePanel'),
  stage: el('stage'), target: el('target'), fixation: el('fixation'),
  flash: el('flash'), stageText: el('stageText'),
  preview: el('preview'), summary: el('summary'),
  btnEnable: el('btnEnable'), btnStart: el('btnStart'), btnDownload: el('btnDownload'),
  chkStream: el('chkStream'), chkLight: el('chkLight'),
  chkFps: el('chkFps'), chkAudio: el('chkAudio'),
  hud: el('hud'), hudFps: el('hudFps'), hudFace: el('hudFace'),
  hudLuma: el('hudLuma'), hudStage: el('hudStage'),
};

const state = {
  recorder: null,
  engine: null,
  chunks: [],
  videoBlob: null,
  rafHandle: null,
  geometry: null,
  quality: { fps: null, faceRate: null, luma: null },
};

document.head.appendChild(
  Object.assign(document.createElement('style'), { textContent: CHINREST_CSS }),
);

/**
 * Minimum mean luminance before we warn.
 *
 * §2.5: the rPPG heart-rate accuracy gap between Fitzpatrick type 1 and type 5
 * collapses from ~2.25 bpm to ~0.21 bpm once luminance clears 30. That is the
 * only quantified bias mitigation in the whole evidence base, which makes this
 * threshold a fairness control rather than a picture-quality preference.
 */
const MIN_LUMA = 30;

/** §5.3 uses 5 Hz as a published exclusion threshold for online eye tracking. */
const MIN_FPS = 5;

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------

ui.btnEnable.addEventListener('click', async () => {
  ui.btnEnable.disabled = true;
  ui.chkStream.textContent = 'requesting…';

  try {
    state.recorder = new SessionRecorder({
      sessionId: `s_${Date.now().toString(36)}`,
      participantId: new URLSearchParams(location.search).get('pid') || 'anonymous',
      studyId: new URLSearchParams(location.search).get('study') || 'm0',
    });

    const { appliedAudioConstraints } = await state.recorder.start();
    ui.preview.srcObject = state.recorder.stream;
    ui.chkStream.textContent = 'ok';
    ui.chkStream.style.color = 'var(--ok)';

    reportAudioConstraints(appliedAudioConstraints);

    state.engine = new MediaPipeBlendshapesLive();
    state.engine.onOutput(onEngineOutput);
    await state.engine.init();

    ui.hud.classList.add('visible');
    startPreviewLoop();

    ui.btnStart.disabled = false;
    ui.btnStart.classList.remove('secondary');
  } catch (err) {
    ui.chkStream.textContent = 'failed';
    ui.chkStream.style.color = 'var(--bad)';
    ui.btnEnable.disabled = false;
    console.error(err);
  }
});

/**
 * Report whether the browser honoured the request to disable its DSP.
 *
 * §5.2: constraints are best-effort and the UA may ignore them without
 * failing, and OS/driver processing can persist regardless. §2.3 makes this
 * consequential rather than cosmetic — noise suppression that degrades
 * intelligibility removes the lexical content that voice valence actually
 * depends on, so a session captured with it on cannot support those channels.
 */
function reportAudioConstraints(applied) {
  if (!applied) {
    ui.chkAudio.textContent = 'no audio track';
    ui.chkAudio.style.color = 'var(--muted)';
    return;
  }
  const stages = ['echoCancellation', 'noiseSuppression', 'autoGainControl'];
  const stillOn = stages.filter((k) => applied[k] === true);

  if (stillOn.length === 0) {
    ui.chkAudio.textContent = 'ok';
    ui.chkAudio.style.color = 'var(--ok)';
  } else {
    // A warning, not a blocker: the session is still usable for every channel
    // that does not depend on intelligible speech.
    ui.chkAudio.textContent = `${stillOn.length} still on`;
    ui.chkAudio.style.color = 'var(--warn)';
    ui.chkAudio.title =
      `${stillOn.join(', ')} could not be disabled on this device. ` +
      'Voice channels that rely on speech content may be unreliable.';
  }
}

function onEngineOutput(chunk) {
  if (chunk.signals?.length || chunk.events?.length || chunk.quality?.length) {
    state.chunks.push(chunk);
  }
  for (const q of chunk.quality ?? []) {
    if (q.metric === 'achieved_fps') state.quality.fps = q.value;
    if (q.metric === 'face_detect_rate') state.quality.faceRate = q.value;
    if (q.metric === 'mean_luminance') state.quality.luma = q.value;
  }
  renderHud();
}

function renderHud() {
  const { fps, faceRate, luma } = state.quality;

  setMetric(ui.hudFps, fps, (v) => v.toFixed(1), (v) => (v >= MIN_FPS ? 'ok' : 'bad'));
  setMetric(ui.hudFace, faceRate, (v) => `${(v * 100).toFixed(0)}%`,
    (v) => (v >= 0.5 ? 'ok' : v > 0 ? 'warn' : 'bad'));
  setMetric(ui.hudLuma, luma, (v) => v.toFixed(0),
    (v) => (v >= MIN_LUMA ? 'ok' : 'warn'));

  if (fps !== null) {
    ui.chkFps.textContent = `${fps.toFixed(1)} fps`;
    ui.chkFps.style.color = fps >= MIN_FPS ? 'var(--ok)' : 'var(--bad)';
  }
  if (luma !== null) {
    ui.chkLight.textContent = luma >= MIN_LUMA ? 'ok' : 'too dim';
    ui.chkLight.style.color = luma >= MIN_LUMA ? 'var(--ok)' : 'var(--warn)';
  }
}

function setMetric(node, value, format, classify) {
  if (value === null || value === undefined) {
    node.textContent = '—';
    node.className = 'v';
    return;
  }
  node.textContent = format(value);
  node.className = `v ${classify(value)}`;
}

/** Feed frames to the live engine. Purely for feedback — not the record. */
function startPreviewLoop() {
  const pump = () => {
    if (ui.preview.readyState >= 2 && state.engine) {
      try {
        const ts = stamp();
        state.engine.pushFrame(ui.preview, ts);
        state.recorder?.noteFrame(ts.native_ts);
      } catch (err) {
        console.warn('frame dropped', err);
      }
    }
    state.rafHandle = requestAnimationFrame(pump);
  };
  state.rafHandle = requestAnimationFrame(pump);
}

// ---------------------------------------------------------------------------
// sequence
// ---------------------------------------------------------------------------

ui.btnStart.addEventListener('click', runSequence);

async function runSequence() {
  ui.setupPanel.style.display = 'none';

  await runGeometry();

  ui.stage.classList.add('active');

  const sequence = buildM0Sequence();
  console.info(`sequence: ${sequence.length} stages, ~${Math.round(estimateDurationMs(sequence) / 1000)}s`);

  for (const stage of sequence) {
    ui.hudStage.textContent = stage.id;
    await runStage(stage);
  }

  await finish();
}

/**
 * Recover screen geometry before the stimulus sequence starts.
 *
 * It has to run before calibration, not after, because it is what makes the
 * calibration error interpretable: §5.1 measured viewing distance at mean
 * 47.3cm with SD 8.9 across 1,153 online participants, so an error in degrees
 * computed from a nominal distance is not an error in degrees.
 *
 * A refusal does NOT stop the session. Everything except dva conversion still
 * works without geometry, and dropping a participant who could not manage the
 * blind-spot task would discard usable pixel-space data. The refusal is
 * recorded so analysis can exclude on it deliberately rather than inherit a
 * guess (REPORT.md's `evaluateCalibration` note: gate with retry, not
 * exclusion).
 */
async function runGeometry() {
  state.geometry = state.recorder.setGeometry(
    await runVirtualChinrest(document.body, {
      onRetry: (reason) => state.recorder.logEvent('virtual_chinrest_retry', { reason }),
    }),
  );

  if (!state.geometry.ok) {
    console.warn(`geometry refused: ${state.geometry.reason} — ${state.geometry.detail}`);
  }
}

async function runStage(stage) {
  switch (stage.type) {
    case 'sync_clapper':   return runClapper(stage);
    case 'instruction':    return runInstruction(stage);
    case 'calibration_point':
    case 'validation_point': return runPoint(stage);
    case 'fixation':       return runFixation(stage);
    default:
      console.warn('unknown stage', stage);
      return undefined;
  }
}

/**
 * Sync clapper — the anchor the whole alignment rests on.
 *
 * The screen flashes white at a known master-clock time. That flash reflects
 * off the participant and raises frame luminance, so the same instant is
 * observable on both clocks and the aligner can measure the offset instead of
 * assuming it.
 *
 * The event is logged immediately BEFORE the paint, then again after the frame
 * is actually presented, so the aligner can see the paint latency rather than
 * inheriting it silently.
 */
async function runClapper(stage) {
  ui.stageText.style.display = 'none';
  ui.target.style.opacity = '0';
  await wait(TIMINGS.clapperPrerollMs);

  ui.flash.style.display = 'block';

  // requestAnimationFrame fires just before the browser paints; the stamp
  // taken inside it is the closest we can get to presentation time from JS.
  await new Promise((resolve) => {
    requestAnimationFrame(() => {
      state.recorder.logEvent('sync_clapper', { stage_id: stage.id }, stage.id);
      resolve();
    });
  });

  await wait(TIMINGS.clapperFlashMs);
  ui.flash.style.display = 'none';
  state.recorder.closeEvent('sync_clapper', stage.id);
}

async function runInstruction(stage) {
  ui.target.style.opacity = '0';
  ui.stageText.textContent = stage.text;
  ui.stageText.style.display = 'block';
  state.recorder.logEvent('instruction', { text: stage.text }, stage.id);
  await wait(4000);
  ui.stageText.style.display = 'none';
}

/**
 * Show one calibration or validation target.
 *
 * The saccade allowance before sampling matters: a sample taken the instant
 * the dot appears captures the participant still looking at the previous
 * location, which would train the estimator on the wrong association.
 */
async function runPoint(stage) {
  ui.stageText.style.display = 'none';
  ui.target.style.left = `${stage.x * 100}%`;
  ui.target.style.top = `${stage.y * 100}%`;
  ui.target.style.opacity = '1';

  state.recorder.logEvent(
    stage.type, { x: stage.x, y: stage.y }, stage.id,
  );

  await wait(TIMINGS.saccadeMs);

  const dwell = stage.type === 'calibration_point'
    ? TIMINGS.calibrationDwellMs : TIMINGS.validationDwellMs;

  state.recorder.logEvent(
    `${stage.type}_sampling`, { x: stage.x, y: stage.y }, stage.id,
  );
  await wait(dwell);

  state.recorder.closeEvent(`${stage.type}_sampling`, stage.id);
  state.recorder.closeEvent(stage.type, stage.id);
  ui.target.style.opacity = '0';
}

async function runFixation(stage) {
  ui.target.style.opacity = '0';
  ui.fixation.style.display = 'block';
  state.recorder.logEvent('fixation', null, stage.id);
  await wait(stage.durationMs ?? TIMINGS.fixationMs);
  state.recorder.closeEvent('fixation', stage.id);
  ui.fixation.style.display = 'none';
}

// ---------------------------------------------------------------------------
// completion
// ---------------------------------------------------------------------------

async function finish() {
  cancelAnimationFrame(state.rafHandle);

  const tail = await state.engine.flush(stamp());
  if (tail) onEngineOutput(tail);
  state.engine.close();

  state.videoBlob = await state.recorder.stop();

  ui.stage.classList.remove('active');
  ui.hud.classList.remove('visible');
  ui.donePanel.style.display = 'block';

  renderSummary();
}

function renderSummary() {
  const manifest = state.recorder.manifest();
  const signalRows = state.chunks.reduce((n, c) => n + (c.signals?.length ?? 0), 0);

  const g = state.geometry;
  const rows = [
    ['Session', manifest.session_id],
    // Shown with its error bar or not at all. A viewing distance quoted without
    // one invites exactly the false precision the chinrest module refuses to
    // produce — the accuracy floor is ±5.5cm however steady the participant was.
    ['Viewing distance', g?.ok
      ? `${(g.viewing_distance_mm / 10).toFixed(1)} ± ${(g.geometry_error_mm / 10).toFixed(1)} cm`
      : `not recovered (${g?.reason ?? 'not attempted'})`],
    ['Degrees-of-angle budget', g?.ok
      ? `±${(stimulusSizeErrorFraction() * 100).toFixed(0)}% of stimulus size`
      : 'unavailable — dva cannot be computed'],
    ['Events logged', String(manifest.events.length)],
    ['Live signal rows', String(signalRows)],
    ['Achieved fps', manifest.achieved_fps ? manifest.achieved_fps.toFixed(1) : '—'],
    ['Video size', state.videoBlob ? `${(state.videoBlob.size / 1e6).toFixed(1)} MB` : '—'],
    ['Clock resolution', manifest.clock.measured_resolution_ms !== null
      ? `${manifest.clock.measured_resolution_ms.toFixed(3)} ms` : '—'],
  ];

  ui.summary.innerHTML = rows
    .map(([k, v]) => `<li><span>${k}</span><span class="state">${v}</span></li>`)
    .join('');
}

ui.btnDownload.addEventListener('click', async () => {
  const manifest = state.recorder.manifest();
  manifest.browser_source = `${state.engine.manifest.engine_id}@${state.engine.manifest.version}+browser-live`;
  manifest.browser_chunk_count = state.chunks.length;

  downloadBlob(
    new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' }),
    'session.json',
  );

  // Live engine output travels beside the manifest so the pipeline can write
  // it as a second `source` alongside the server-side pass.
  downloadBlob(
    new Blob([JSON.stringify(state.chunks)], { type: 'application/json' }),
    'browser_chunks.json',
  );

  if (state.videoBlob) {
    const ext = state.videoBlob.type.includes('mp4') ? 'mp4' : 'webm';
    downloadBlob(state.videoBlob, `capture.${ext}`);
  }
});

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

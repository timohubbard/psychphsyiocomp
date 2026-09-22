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
  progress: el('progress'),
  hud: el('hud'), hudFps: el('hudFps'), hudFace: el('hudFace'),
  hudLuma: el('hudLuma'), hudStage: el('hudStage'),
};

const state = {
  recorder: null,
  engine: null,
  chunks: [],
  videoBlob: null,
  rafHandle: null,
  frameLoopKind: null,
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

/**
 * Feed frames to the live engine. Purely for feedback — not the record.
 *
 * Driven by `requestVideoFrameCallback`, which fires once per frame the video
 * element actually presents, NOT by `requestAnimationFrame`, which fires once
 * per display refresh.
 *
 * The distinction is not cosmetic. The first real capture ran a 30fps camera on
 * a ~70Hz display, and the rAF pump pushed every camera frame 2.35 times:
 *
 *   - `achieved_fps` reported **70.8** for a camera delivering **30.1**. That is
 *     the number written to the quality rows and the `sessions` row, and the one
 *     §5.3's 5Hz exclusion threshold is evaluated against — so the pre-registered
 *     exclusion variable was measuring the monitor, not the camera.
 *   - 606,906 signal rows instead of ~258,000, and a 109MB chunks file for an
 *     82MB video.
 *   - Duplicate inference on identical pixels, which MediaPipe's VIDEO-mode
 *     temporal smoothing then made *non-identical*, so the redundancy was
 *     invisible in the output. Nothing downstream could have detected it.
 *
 * rVFC also hands us `presentedFrames`, which is how a dropped frame becomes
 * observable rather than merely absent.
 */
function startPreviewLoop() {
  const video = ui.preview;
  const hasRvfc = typeof video.requestVideoFrameCallback === 'function';

  const process = () => {
    if (video.readyState >= 2 && state.engine) {
      try {
        const ts = stamp();
        state.engine.pushFrame(video, ts);
        state.recorder?.noteFrame(ts.native_ts);
      } catch (err) {
        console.warn('frame dropped', err);
      }
    }
  };

  if (hasRvfc) {
    const onFrame = () => {
      process();
      state.rafHandle = video.requestVideoFrameCallback(onFrame);
    };
    state.frameLoopKind = 'requestVideoFrameCallback';
    state.rafHandle = video.requestVideoFrameCallback(onFrame);
    return;
  }

  // Fallback for browsers without rVFC. `currentTime` only advances when a new
  // frame is presented, so it still gates on real frames rather than refreshes
  // — just with rAF's polling granularity instead of an exact callback.
  let lastMediaTime = -1;
  const pump = () => {
    if (video.currentTime !== lastMediaTime) {
      lastMediaTime = video.currentTime;
      process();
    }
    state.rafHandle = requestAnimationFrame(pump);
  };
  state.frameLoopKind = 'rAF+currentTime';
  state.rafHandle = requestAnimationFrame(pump);
}

/** Stop the frame loop, whichever kind was started. */
function stopPreviewLoop() {
  if (state.frameLoopKind === 'requestVideoFrameCallback') {
    ui.preview.cancelVideoFrameCallback?.(state.rafHandle);
  } else {
    cancelAnimationFrame(state.rafHandle);
  }
}

// ---------------------------------------------------------------------------
// sequence
// ---------------------------------------------------------------------------

ui.btnStart.addEventListener('click', runSequence);

async function runSequence() {
  ui.setupPanel.style.display = 'none';

  await runGeometry();

  ui.stage.classList.add('active');

  // Seeded so the exact presentation order can be replayed, and recorded so
  // analysis can confirm the order was randomised rather than assume it.
  const seed = (Date.now() ^ (Math.random() * 0xFFFFFFFF)) >>> 0;
  state.recorder.logEvent('sequence_seed', { seed });
  const sequence = buildM0Sequence(seed);
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

  // Let the flash actually reach the recording before anything stops it. The
  // camera lags the screen by more than a frame, so a clapper at the end of a
  // sequence is otherwise cut off mid-plateau — see TIMINGS.clapperPostrollMs.
  await wait(TIMINGS.clapperPostrollMs);
}

/**
 * Show an instruction and wait for the participant, not for a timer.
 *
 * The dwell time is recorded. It is the cheapest available signal that someone
 * actually read the screen rather than pressing through it, and a run of
 * near-instant dismissals is worth knowing about when interpreting that
 * participant's data later.
 */
async function runInstruction(stage) {
  ui.target.style.opacity = '0';
  ui.fixation.style.display = 'none';

  const lines = stage.lines ?? [stage.text];
  ui.stageText.innerHTML = `
    ${stage.title ? `<h2 class="instr-title">${stage.title}</h2>` : ''}
    <ul class="instr-lines">${lines.map((l) => `<li>${l}</li>`).join('')}</ul>
    <p class="instr-continue">Press <kbd>space</kbd> when you are ready</p>`;
  ui.stageText.style.display = 'block';

  const shownAt = now();
  state.recorder.logEvent('instruction', { id: stage.id, title: stage.title ?? null }, stage.id);

  await wait(TIMINGS.instructionMinMs);
  await waitForContinue();

  state.recorder.closeEvent('instruction', stage.id);
  state.recorder.logEvent('instruction_dwell', {
    id: stage.id, dwell_ms: Math.round(now() - shownAt),
  }, stage.id);

  ui.stageText.style.display = 'none';
}

/** Resolve on space or a click anywhere. */
function waitForContinue() {
  return new Promise((resolve) => {
    const done = (ev) => {
      if (ev.type === 'keydown' && ev.code !== 'Space') return;
      if (ev.type === 'keydown') ev.preventDefault();
      window.removeEventListener('keydown', done);
      window.removeEventListener('click', done);
      resolve();
    };
    window.addEventListener('keydown', done);
    window.addEventListener('click', done);
  });
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

  // Knowing how many are left is the difference between a short task and an
  // indefinite one. Kept in a corner, dim, and well away from every calibration
  // coordinate, so it cannot become a competing fixation target.
  if (stage.index && stage.total) {
    ui.progress.textContent = `${stage.index} of ${stage.total}`;
    ui.progress.style.display = 'block';
  }

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
  if (stage.index === stage.total) ui.progress.style.display = 'none';
}

async function runFixation(stage) {
  ui.target.style.opacity = '0';
  ui.stageText.style.display = 'none';
  ui.fixation.style.display = 'block';

  const durationMs = stage.durationMs ?? TIMINGS.fixationMs;
  state.recorder.logEvent('fixation', { duration_ms: durationMs }, stage.id);

  // A minute of staring at a cross with no feedback is indistinguishable from a
  // frozen page. The countdown is deliberately small, dim and in a corner: it
  // has to be findable if you go looking, without competing with the cross for
  // the gaze it is the whole point of this stage to hold.
  const endsAt = now() + durationMs;
  ui.progress.style.display = 'block';
  const tick = setInterval(() => {
    const left = Math.max(0, Math.ceil((endsAt - now()) / 1000));
    ui.progress.textContent = `${left}s`;
  }, 250);

  await wait(durationMs);

  clearInterval(tick);
  ui.progress.style.display = 'none';
  state.recorder.closeEvent('fixation', stage.id);
  ui.fixation.style.display = 'none';
}

// ---------------------------------------------------------------------------
// completion
// ---------------------------------------------------------------------------

async function finish() {
  stopPreviewLoop();

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
    ['Achieved fps', manifest.achieved_fps
      ? `${manifest.achieved_fps.toFixed(1)} (${state.frameLoopKind})` : '—'],
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

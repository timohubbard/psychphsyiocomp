import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  CALIBRATION_POINTS,
  VALIDATION_POINTS,
  TIMINGS,
  buildM0Sequence,
  buildSequence,
  clapperCount,
  errorInDegrees,
  estimateDurationMs,
  evaluateCalibration,
  seededShuffle,
  DEFAULT_EXPRESSIONS,
  EXPRESSION_TIMINGS,
  wantsChinrest,
} from './sequence.js';

// ---------------------------------------------------------------------------
// calibration grid
// ---------------------------------------------------------------------------

test('calibration grid takes the 9->12 gain without paying for the flat part', () => {
  // §2.1: largest single improvement is 9->12 points; 12->18 is marginal.
  assert.ok(CALIBRATION_POINTS.length >= 12,
    `expected >=12 points, got ${CALIBRATION_POINTS.length}`);
  assert.ok(CALIBRATION_POINTS.length <= 18);
});

test('all calibration points sit inside the viewport', () => {
  for (const [x, y] of CALIBRATION_POINTS) {
    assert.ok(x >= 0 && x <= 1, `x out of range: ${x}`);
    assert.ok(y >= 0 && y <= 1, `y out of range: ${y}`);
  }
});

test('calibration points are distinct', () => {
  const seen = new Set(CALIBRATION_POINTS.map(([x, y]) => `${x},${y}`));
  assert.equal(seen.size, CALIBRATION_POINTS.length, 'duplicate calibration point');
});

test('calibration covers all four quadrants and the centre', () => {
  const has = (pred) => CALIBRATION_POINTS.some(pred);
  assert.ok(has(([x, y]) => x < 0.5 && y < 0.5), 'no top-left point');
  assert.ok(has(([x, y]) => x > 0.5 && y < 0.5), 'no top-right point');
  assert.ok(has(([x, y]) => x < 0.5 && y > 0.5), 'no bottom-left point');
  assert.ok(has(([x, y]) => x > 0.5 && y > 0.5), 'no bottom-right point');
  assert.ok(has(([x, y]) => x === 0.5 && y === 0.5), 'no centre point');
});

// ---------------------------------------------------------------------------
// validation must measure generalisation, not memorisation
// ---------------------------------------------------------------------------

test('validation points are NOT a subset of calibration points', () => {
  const calib = new Set(CALIBRATION_POINTS.map(([x, y]) => `${x},${y}`));
  const overlap = VALIDATION_POINTS.filter(([x, y]) => calib.has(`${x},${y}`));
  assert.equal(overlap.length, 0,
    `validating on fitted coordinates measures memorisation: ${JSON.stringify(overlap)}`);
});

test('validation points stay inside the viewport', () => {
  for (const [x, y] of VALIDATION_POINTS) {
    assert.ok(x >= 0 && x <= 1 && y >= 0 && y <= 1);
  }
});

// ---------------------------------------------------------------------------
// sequence structure
// ---------------------------------------------------------------------------

test('sequence bookends the session with two clappers', () => {
  // One anchor gives offset only; two let the aligner fit clock drift.
  //
  // Bookending is a property of the MEASURED span, not of array index 0. The
  // clappers must enclose every stage that produces data; instruction screens
  // may sit outside them, and have to, because a participant reading one is not
  // yet doing anything worth anchoring.
  const seq = buildM0Sequence();
  assert.equal(clapperCount(seq), 2);

  const measured = seq
    .map((s, i) => ({ ...s, i }))
    .filter((s) => s.type !== 'instruction');

  assert.equal(measured[0].type, 'sync_clapper',
    'the first stage that produces data must be a clapper');
  assert.equal(measured[measured.length - 1].type, 'sync_clapper',
    'the last stage that produces data must be a clapper');
});

test('every stage a participant could be confused by is introduced', () => {
  // The first real participant — who wrote the software — reported not knowing
  // what was being asked of them. Before this, the whole session carried two
  // one-line instructions that auto-dismissed after four seconds, and the
  // 60-second fixation had none at all: a cross appeared and nothing else
  // happened for a minute, which is indistinguishable from a frozen page.
  const seq = buildM0Sequence();
  const needsIntro = new Set(['sync_clapper', 'calibration_point', 'validation_point', 'fixation']);

  const introduced = new Set();
  let sawInstructionSince = null;
  for (const stage of seq) {
    if (stage.type === 'instruction') { sawInstructionSince = stage.id; continue; }
    if (needsIntro.has(stage.type)) {
      if (sawInstructionSince) introduced.add(stage.type);
      // A run of points is introduced once, not per point.
      if (stage.index === undefined || stage.index === stage.total) sawInstructionSince = null;
    }
  }

  for (const t of needsIntro) {
    assert.ok(introduced.has(t), `${t} is not preceded by an instruction`);
  }
});

test('instructions are self-paced, not on a timer', () => {
  // A fixed dwell silently excludes anyone who reads slower than it.
  assert.ok(TIMINGS.instructionMinMs > 0, 'a minimum read time must exist');
  assert.ok(TIMINGS.instructionMinMs < 3000,
    'the minimum is an anti-skip floor, not a substitute for waiting');
});

test('instruction screens carry real content, not a single line', () => {
  const intros = buildM0Sequence().filter((s) => s.type === 'instruction');
  assert.ok(intros.length >= 4, `expected an intro per phase, got ${intros.length}`);
  for (const s of intros) {
    assert.ok(s.title, `instruction ${s.id} has no title`);
    assert.ok(Array.isArray(s.lines) && s.lines.length >= 2,
      `instruction ${s.id} should say what happens, what to do, and how long`);
  }
});

test('the fixation intro tells the participant how long it lasts', () => {
  // The single worst gap found: a minute of staring with no stated duration.
  const intro = buildM0Sequence().find((s) => s.id === 'fixation_intro');
  assert.ok(intro, 'fixation has no introduction');
  assert.ok(intro.lines.some((l) => /minute|second/i.test(l)),
    'the fixation intro must state its duration');
});

test('sequence contains every calibration and validation point', () => {
  const seq = buildM0Sequence();
  assert.equal(
    seq.filter((s) => s.type === 'calibration_point').length,
    CALIBRATION_POINTS.length,
  );
  assert.equal(
    seq.filter((s) => s.type === 'validation_point').length,
    VALIDATION_POINTS.length,
  );
});

test('calibration precedes validation', () => {
  const seq = buildM0Sequence();
  const lastCalib = seq.map((s) => s.type).lastIndexOf('calibration_point');
  const firstValid = seq.map((s) => s.type).indexOf('validation_point');
  assert.ok(lastCalib < firstValid, 'cannot validate before calibrating');
});

test('every stage has a unique id', () => {
  const ids = buildM0Sequence().map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length, 'duplicate stage id');
});

test('duration estimate is plausible and dominated by the fixation block', () => {
  const total = estimateDurationMs(buildM0Sequence());
  assert.ok(total > TIMINGS.fixationMs, 'must exceed the fixation block alone');
  assert.ok(total < 5 * 60_000, `M0 session should stay under 5 min, got ${total}ms`);
});

// ---------------------------------------------------------------------------
// error in degrees — refuses to guess without geometry
// ---------------------------------------------------------------------------

const GEOMETRY = {
  viewingDistanceMm: 500,
  pxPerMm: 4,
  viewportWidthPx: 1280,
  viewportHeightPx: 720,
};

test('perfect estimate yields zero error', () => {
  const e = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.5, y: 0.5 }, GEOMETRY);
  assert.equal(e, 0);
});

test('error grows with displacement', () => {
  const near = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.52, y: 0.5 }, GEOMETRY);
  const far = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 }, GEOMETRY);
  assert.ok(far > near);
});

test('a known displacement gives the expected angle', () => {
  // 0.5 -> 0.6 of 1280px = 128px; at 4px/mm that is 32mm; atan(32/500) ~ 3.66deg
  const e = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 }, GEOMETRY);
  assert.ok(Math.abs(e - 3.66) < 0.05, `expected ~3.66deg, got ${e}`);
});

test('returns null without viewing distance rather than assuming one', () => {
  // §5.1: viewing distance across 1,153 online participants was mean 47.3cm
  // with SD 8.9 — a nominal value produces a dva figure that is not a dva figure.
  const e = errorInDegrees(
    { x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 },
    { ...GEOMETRY, viewingDistanceMm: null },
  );
  assert.equal(e, null);
});

test('returns null without pixel scale', () => {
  const e = errorInDegrees(
    { x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 },
    { ...GEOMETRY, pxPerMm: null },
  );
  assert.equal(e, null);
});

test('closer viewing distance means larger angular error for the same pixels', () => {
  const near = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 },
    { ...GEOMETRY, viewingDistanceMm: 300 });
  const far = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.6, y: 0.5 },
    { ...GEOMETRY, viewingDistanceMm: 700 });
  assert.ok(near > far, 'angular error must scale with viewing distance');
});

// ---------------------------------------------------------------------------
// calibration gate
// ---------------------------------------------------------------------------

const CRITERIA = { maxMeanErrorDeg: 3.0, minPointsMeasured: 8 };

test('good calibration passes', () => {
  const r = evaluateCalibration([1.0, 1.2, 0.9, 1.5, 1.1, 1.3, 1.0, 1.4], CRITERIA);
  assert.ok(r.pass);
  assert.ok(r.meanErrorDeg < 3.0);
});

test('poor calibration fails with the threshold named', () => {
  const r = evaluateCalibration([4.0, 5.0, 4.5, 6.0, 5.5, 4.2, 5.1, 4.8], CRITERIA);
  assert.equal(r.pass, false);
  assert.equal(r.reason, 'error_above_threshold');
  assert.ok(r.detail.includes('3'), 'detail should name the threshold');
});

test('too few measured points fails distinctly from being inaccurate', () => {
  // A tracker that lost the face is a different problem from one that is
  // merely imprecise, and the retry advice differs.
  const r = evaluateCalibration([1.0, 1.2, null, null, null, null, null, null], CRITERIA);
  assert.equal(r.pass, false);
  assert.equal(r.reason, 'insufficient_points');
  assert.equal(r.meanErrorDeg, null);
});

test('nulls are excluded from the mean rather than counted as zero', () => {
  const withNulls = evaluateCalibration(
    [2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, null, null], CRITERIA);
  assert.ok(Math.abs(withNulls.meanErrorDeg - 2.0) < 1e-9,
    `nulls must not drag the mean down, got ${withNulls.meanErrorDeg}`);
});

test('non-finite values are treated as unmeasured', () => {
  const r = evaluateCalibration(
    [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, Infinity, NaN], CRITERIA);
  assert.ok(Number.isFinite(r.meanErrorDeg));
  assert.ok(Math.abs(r.meanErrorDeg - 1.0) < 1e-9);
});

test('the gate carries no default threshold of its own', () => {
  // §5.3: jsPsych publishes no pass/fail cutoff, so shipping one here would be
  // inventing a standard. The caller must pre-register it.
  assert.throws(
    () => evaluateCalibration([1, 2, 3], undefined),
    /Cannot read|undefined/,
    'criteria must be required, not defaulted',
  );
});


// ---------------------------------------------------------------------------
// presentation order
// ---------------------------------------------------------------------------

test('the same seed reproduces the same order', () => {
  // A session has to be replayable exactly, or the order cannot be audited.
  const a = seededShuffle(CALIBRATION_POINTS, 12345);
  const b = seededShuffle(CALIBRATION_POINTS, 12345);
  assert.deepEqual(a, b);
});

test('different seeds give different orders', () => {
  const a = seededShuffle(CALIBRATION_POINTS, 1);
  const b = seededShuffle(CALIBRATION_POINTS, 2);
  assert.notDeepEqual(a, b);
});

test('shuffling keeps every point exactly once', () => {
  const out = seededShuffle(CALIBRATION_POINTS, 999);
  assert.equal(out.length, CALIBRATION_POINTS.length);
  const key = (p) => `${p[0]},${p[1]}`;
  assert.deepEqual(new Set(out.map(key)), new Set(CALIBRATION_POINTS.map(key)));
});

test('presentation order is decorrelated from target position', () => {
  // The measured failure this exists to prevent: with the grid in its declared
  // row-by-row order, target y correlates with presentation index at r = +0.56.
  // Any feature drifting over the session then proxies for target position, and
  // leave-one-out CV cannot see it because the held-out point's temporal
  // neighbours remain in the training set.
  const corrWithIndex = (points) => {
    const n = points.length;
    const ys = points.map((p) => p[1]);
    const xs = points.map((_, i) => i);
    const mx = xs.reduce((a, b) => a + b, 0) / n;
    const my = ys.reduce((a, b) => a + b, 0) / n;
    let num = 0, dx = 0, dy = 0;
    for (let i = 0; i < n; i += 1) {
      num += (xs[i] - mx) * (ys[i] - my);
      dx += (xs[i] - mx) ** 2;
      dy += (ys[i] - my) ** 2;
    }
    return num / Math.sqrt(dx * dy);
  };

  assert.ok(Math.abs(corrWithIndex(CALIBRATION_POINTS)) > 0.5,
    'the declared order should be the confounded one this guards against');

  // Averaged over many seeds the correlation must sit near zero. Any single
  // shuffle can be unlucky, which is exactly why the seed is recorded.
  let total = 0;
  const trials = 200;
  for (let s = 1; s <= trials; s += 1) total += corrWithIndex(seededShuffle(CALIBRATION_POINTS, s));
  const mean = total / trials;
  assert.ok(Math.abs(mean) < 0.1, `mean correlation across seeds was ${mean.toFixed(3)}`);
});

test('the sequence presents points in shuffled order', () => {
  const seq = buildM0Sequence(4242);
  const shown = seq.filter((s) => s.type === 'calibration_point').map((s) => [s.x, s.y]);
  assert.deepEqual(shown, seededShuffle(CALIBRATION_POINTS, 4242));
});


// ---------------------------------------------------------------------------
// speech elicitation
// ---------------------------------------------------------------------------

test('the sequence asks the participant to speak', () => {
  // Running the voice engine over the first real session produced a voiced
  // fraction of ZERO, because the sequence only ever asked people to follow
  // dots and rest their eyes. Acoustic features cannot be recovered from a
  // recording of a silent room — the speech has to be elicited during capture
  // or it does not exist.
  const kinds = buildM0Sequence().map((s) => s.type);
  assert.ok(kinds.includes('speech_read'), 'no read-aloud task');
  assert.ok(kinds.includes('speech_free'), 'no free-speech task');
});

test('both speaking tasks are introduced before they start', () => {
  const seq = buildM0Sequence();
  for (const kind of ['speech_read', 'speech_free']) {
    const at = seq.findIndex((s) => s.type === kind);
    const before = seq.slice(0, at).reverse().find((s) => s.type === 'instruction');
    assert.ok(before, `${kind} has no preceding instruction`);
  }
});

test('the read-aloud passage is long enough for stable statistics', () => {
  // eGeMAPS functionals are statistics over a window; a two-sentence passage
  // gives too few voiced frames for F0 spread to mean anything.
  const stage = buildM0Sequence().find((s) => s.type === 'speech_read');
  assert.ok(stage.text.length > 250, `passage is only ${stage.text.length} chars`);
  assert.ok(stage.durationMs >= 30_000, 'read window under 30s');
});

test('speech stages carry an explicit duration', () => {
  // The voice engine windows by time, so a stage without one would be analysed
  // against a default that nothing recorded.
  for (const s of buildM0Sequence().filter((x) => x.type.startsWith('speech_'))) {
    assert.ok(Number.isFinite(s.durationMs) && s.durationMs > 0, s.id);
  }
});

test('speech padding exists so onset and offset are unambiguous', () => {
  // A participant who starts talking the instant text appears puts the first
  // syllables in the same analysis window as the stage transition.
  assert.ok(TIMINGS.speechPadMs >= 500);
});

test('the duration estimate accounts for the speaking tasks', () => {
  const total = estimateDurationMs(buildM0Sequence());
  const speech = buildM0Sequence()
    .filter((s) => s.type.startsWith('speech_'))
    .reduce((n, s) => n + s.durationMs, 0);
  assert.ok(total > TIMINGS.fixationMs + speech,
    'estimate does not include the speech stages');
});

// ---------------------------------------------------------------------------
// the sequence a STUDY asks for
//
// The study definition is content-hashed. A hash that covers a field nothing
// reads is worse than no field: it promises attributability it does not
// deliver. These check that `calibration.n_points` and `tasks` actually change
// what a participant sees.
// ---------------------------------------------------------------------------

function studyFor(overrides = {}) {
  return {
    modalities: ['gaze', 'face', 'voice'],
    calibration: { n_points: 13, randomise_order: true },
    ...overrides,
  };
}

test('every generated instruction line is a finished sentence', () => {
  // The test that was missing. 39 sequence tests passed while the calibration
  // screen told participants "13 dots, about NaN seconds" — the counts had
  // been derived from TIMINGS keys that do not exist. Nothing asserted on the
  // prose, because the prose used to be a literal.
  const studies = [
    studyFor(),
    studyFor({ calibration: { n_points: 5, randomise_order: true } }),
    studyFor({ modalities: ['gaze'] }),
    studyFor({ modalities: ['voice'], calibration: undefined }),
    studyFor({ tasks: [{ type: 'rest_fixation', duration_ms: 30_000 }] }),
  ];
  for (const s of studies) {
    for (const stage of buildSequence(s, 1).filter((x) => x.type === 'instruction')) {
      for (const line of stage.lines) {
        assert.ok(!/NaN|undefined|\[object/.test(line),
          `${stage.id}: ${line}`);
        assert.ok(line.trim().length > 0, `${stage.id} has an empty line`);
      }
    }
  }
});

test('the dot count in the prose matches the dots in the sequence', () => {
  const seq = buildSequence(studyFor({
    calibration: { n_points: 9, randomise_order: true } }), 3);
  const dots = seq.filter((s) => s.type === 'calibration_point').length;
  const intro = seq.find((s) => s.id === 'calib_intro');
  assert.equal(dots, 9);
  assert.ok(intro.lines.some((l) => l.startsWith('9 dots')),
    intro.lines.join(' | '));
});

test('a smaller calibration grid still spans the screen', () => {
  // Taking the first N in declaration order would give the outer ring and
  // leave the centre uncalibrated — the region a ridge model most needs.
  const seq = buildSequence(studyFor({
    calibration: { n_points: 5, randomise_order: true } }), 11);
  const pts = seq.filter((s) => s.type === 'calibration_point');
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  assert.ok(Math.max(...xs) - Math.min(...xs) > 0.5);
  assert.ok(Math.max(...ys) - Math.min(...ys) > 0.5);
});

test('asking for more calibration points than exist throws', () => {
  // The definition already validated, so this is a protocol asking for
  // something this build cannot give — running a quietly degraded version of
  // someone's protocol is the worst available option.
  assert.throws(() => buildSequence(studyFor({
    calibration: { n_points: 99, randomise_order: true } })), /only 13/);
});

test('an unknown task type throws rather than being skipped', () => {
  assert.throws(() => buildSequence(studyFor({
    tasks: [{ type: 'stroop' }] })), /unknown task type: stroop/);
});

test('a study without voice contains no speech stages', () => {
  const seq = buildSequence(studyFor({ modalities: ['gaze', 'face'] }), 5);
  assert.equal(seq.filter((s) => s.type.startsWith('speech_')).length, 0);
  assert.ok(!seq.some((s) => s.id === 'speech_intro'));
});

test('a speech task in a study without voice is dropped, not honoured', () => {
  // Asking a participant to speak into a microphone nobody requested.
  const seq = buildSequence(studyFor({
    modalities: ['gaze'], tasks: [{ type: 'calibration' }, { type: 'read_aloud' }] }), 5);
  assert.equal(seq.filter((s) => s.type === 'speech_read').length, 0);
});

test('a study without gaze contains no calibration', () => {
  const seq = buildSequence(studyFor({
    modalities: ['voice'], calibration: undefined,
    tasks: [{ type: 'read_aloud' }] }), 5);
  assert.equal(seq.filter((s) => s.type === 'calibration_point').length, 0);
});

test('tasks run in the order the study declares them', () => {
  const seq = buildSequence(studyFor({
    tasks: [{ type: 'read_aloud' }, { type: 'calibration' }] }), 5);
  const kinds = seq.map((s) => s.type);
  assert.ok(kinds.indexOf('speech_read') < kinds.indexOf('calibration_point'));
});

test('the clappers still bookend whatever the study asked for', () => {
  // Two anchors, not one: one gives an offset, two let the aligner fit a rate.
  // A study that reorders its tasks must not be able to lose that.
  const seq = buildSequence(studyFor({ tasks: [{ type: 'rest_fixation' }] }), 5);
  assert.equal(clapperCount(seq), 2);
  assert.equal(seq[seq.length - 1].type, 'sync_clapper');
  assert.equal(seq.findIndex((s) => s.type === 'sync_clapper'), 2);
});

test('a chinrest task is accepted and adds no stage', () => {
  // It runs in setup before the sequence. Listing it in a study is honest
  // about the protocol; silently rejecting it would make the task list a lie.
  const seq = buildSequence(studyFor({
    tasks: [{ type: 'chinrest' }, { type: 'rest_fixation' }] }), 5);
  assert.equal(clapperCount(seq), 2);
  assert.ok(seq.some((s) => s.type === 'fixation'));
});

test('a study may set its own rest duration', () => {
  const seq = buildSequence(studyFor({
    tasks: [{ type: 'rest_fixation', duration_ms: 20_000 }] }), 5);
  const stage = seq.find((s) => s.type === 'fixation');
  assert.equal(stage.durationMs, 20_000);
  const intro = seq.find((s) => s.id === 'fixation_intro');
  assert.ok(intro.lines.some((l) => l.includes('20 seconds')), intro.lines.join('|'));
});

test('a study may supply its own passage', () => {
  // §"Read-aloud passage": the stage takes the text as data, and researchers
  // should substitute their own.
  const seq = buildSequence(studyFor({
    tasks: [{ type: 'read_aloud', passage: ['My own text.'] }] }), 5);
  assert.deepEqual(seq.find((s) => s.type === 'speech_read').text, ['My own text.']);
});

test('buildM0Sequence matches what studies/m0.json describes', async () => {
  // The shortcut is asserted against the file, not trusted to agree with it.
  const fs = await import('node:fs/promises');
  const m0 = JSON.parse(await fs.readFile('studies/m0.json', 'utf8'));
  const fromFile = buildSequence(m0, 99).map((s) => `${s.type}:${s.id}`);
  const fromShortcut = buildM0Sequence(99).map((s) => `${s.type}:${s.id}`);
  assert.deepEqual(fromShortcut, fromFile);
});

test('a study with no calibration does not ask the participant to hold still', () => {
  // An instruction with no purpose teaches participants the rest can be
  // skimmed too — §5.1 attributes about half of a 46-66% attrition to
  // avoidable instruction failure.
  const seq = buildSequence(studyFor({
    modalities: ['voice'], calibration: undefined,
    tasks: [{ type: 'read_aloud' }] }), 5);
  const intro = seq.find((s) => s.id === 'intro');
  assert.ok(!intro.lines.some((l) => l.includes('head still')), intro.lines.join('|'));
});

test('a gaze study still asks the participant to hold still', () => {
  const intro = buildSequence(studyFor(), 5).find((s) => s.id === 'intro');
  assert.ok(intro.lines.some((l) => l.includes('head still')));
});

// ---------------------------------------------------------------------------
// posed expressions — the AU engines' positive control
// ---------------------------------------------------------------------------

const exprStudy = (task = {}) => ({
  modalities: ['face'],
  tasks: [{ type: 'expression_prompts', expressions: 'default', ...task }],
});

test('expression_prompts is a known task and needs no gaze or voice', () => {
  const seq = buildSequence(exprStudy(), 7);
  const trials = seq.filter((s) => s.type === 'expression');
  assert.equal(trials.length, 2 * DEFAULT_EXPRESSIONS.length);
  assert.ok(!seq.some((s) => s.type === 'calibration_point'));
});

test('every trial carries the AUs it asks for, so analysis can score against them', () => {
  for (const t of buildSequence(exprStudy(), 7).filter((s) => s.type === 'expression')) {
    assert.ok(Array.isArray(t.targetAus) && t.targetAus.length > 0, t.id);
    assert.ok(t.targetAus.every(Number.isInteger), t.id);
  }
});

test('instructions describe movements, never emotions', () => {
  // "Look disgusted" invites each participant's own idea of disgust.
  const banned = /happy|sad|angry|anger|disgust|fear|surpris|emotion|feel/i;
  for (const e of DEFAULT_EXPRESSIONS) assert.doesNotMatch(e.text, banned, e.id);
});

test('each repeat is shuffled, so expression is not a function of time', () => {
  // The calibration lesson: fixed order let a drifting quantity stand in for
  // target position. Same risk here with lighting, posture and fatigue.
  const trials = buildSequence(exprStudy({ repeats: 2 }), 7)
    .filter((s) => s.type === 'expression');
  const n = DEFAULT_EXPRESSIONS.length;
  const first = trials.slice(0, n).map((t) => t.expression);
  const second = trials.slice(n).map((t) => t.expression);
  assert.deepEqual([...first].sort(), [...second].sort());
  assert.notDeepEqual(first, second);
  assert.notDeepEqual(first, DEFAULT_EXPRESSIONS.map((e) => e.id));
});

test('the same seed gives the same order, so a session can be replayed', () => {
  const ids = (seed) => buildSequence(exprStudy(), seed).map((s) => s.id);
  assert.deepEqual(ids(11), ids(11));
});

test('trial ids are unique, because events are joined to prompts by them', () => {
  const ids = buildSequence(exprStudy({ repeats: 3 }), 7)
    .filter((s) => s.type === 'expression').map((s) => s.id);
  assert.equal(new Set(ids).size, ids.length);
});

test('the time estimate includes the expression trials', () => {
  const seq = buildSequence(exprStudy(), 7);
  const per = EXPRESSION_TIMINGS.readyMs + EXPRESSION_TIMINGS.holdMs + EXPRESSION_TIMINGS.relaxMs;
  assert.ok(estimateDurationMs(seq) >= 2 * DEFAULT_EXPRESSIONS.length * per);
});

test('studies/au-expressions.json validates and builds', async () => {
  const fs = await import('node:fs/promises');
  const { validateStudy } = await import('./study.js');
  const s = JSON.parse(await fs.readFile('studies/au-expressions.json', 'utf8'));
  assert.equal(validateStudy(s).valid, true);
  // Only media_retained: the AU engines run on the video, which
  // features_only deletes.
  assert.deepEqual(s.consent_tiers, ['media_retained']);
  assert.ok(buildSequence(s, 3).some((x) => x.type === 'expression'));
});

test('the chinrest runs only when the protocol asks for it', async () => {
  // It ran for every study: `chinrest` sat in the hashed task list while the
  // page ignored it, so a face-only study opened with a credit-card procedure.
  const fs = await import('node:fs/promises');
  const load = async (id) => JSON.parse(await fs.readFile(`studies/${id}.json`, 'utf8'));
  assert.equal(wantsChinrest(await load('m0')), true);
  assert.equal(wantsChinrest(await load('au-expressions')), false);
  assert.equal(wantsChinrest(await load('voice-only-example')), false);
  // No task list: the default protocol, which needs it exactly for gaze.
  assert.equal(wantsChinrest({ modalities: ['gaze', 'face'] }), true);
  assert.equal(wantsChinrest({ modalities: ['face'] }), false);
});

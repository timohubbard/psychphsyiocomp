/**
 * Stimulus sequence for the M0 walking skeleton.
 *
 *   sync clapper  →  13-point calibration  →  5-point validation  →  fixation
 *
 * Each stage exists for a specific evidenced reason, noted at its definition.
 * The sequence is data, not control flow, so a study designer can reorder it
 * without touching the runner.
 */

import { now } from './clock.js';

/**
 * Calibration grid: 13 points.
 *
 * §2.1 found raising density from 5 to 18 points cut mean spatial error ~27%
 * and angular error ~24%, with the largest single gain from 9→12 and only
 * marginal improvement 12→18. jsPsych's stock default is a 9-point grid at
 * 10/50/90% — below the useful optimum. 13 takes the 9→12 gain plus a centre
 * repeat, without paying for the flat part of the curve.
 *
 * Coordinates are fractions of viewport width/height.
 */
export const CALIBRATION_POINTS = [
  [0.1, 0.1], [0.5, 0.1], [0.9, 0.1],
  [0.1, 0.5], [0.5, 0.5], [0.9, 0.5],
  [0.1, 0.9], [0.5, 0.9], [0.9, 0.9],
  [0.3, 0.3], [0.7, 0.3],
  [0.3, 0.7], [0.7, 0.7],
];

/**
 * Validation points, deliberately NOT a subset of the calibration grid.
 *
 * Validating on the same coordinates you fitted on measures memorisation, not
 * generalisation. These sit between calibration points so the error estimate
 * reflects interpolation quality.
 *
 * Note the near-centre point is [0.45, 0.55] rather than [0.5, 0.5]: gaze
 * estimators often behave differently at centre than at the periphery, so the
 * central region is worth probing — but [0.5, 0.5] is a fitted coordinate, and
 * measuring there would flatter the estimator. A unit test enforces the
 * no-overlap rule, because this is an easy mistake to reintroduce.
 */
export const VALIDATION_POINTS = [
  [0.2, 0.2], [0.8, 0.2], [0.45, 0.55], [0.2, 0.8], [0.8, 0.8],
];

export const TIMINGS = {
  /** How long the flash stays up. Long enough to survive a dropped frame. */
  clapperFlashMs: 200,
  /**
   * Keep recording after the flash goes down.
   *
   * The camera sees the flash LATER than the browser draws it — measured at
   * ~54ms end to end on a real capture (display latency, then exposure, then
   * the encoder's own timestamping). Stopping the recorder the instant the
   * flash ends therefore truncates it in the video.
   *
   * That is not hypothetical. The first real session's closing clapper landed
   * three frames from the end of the file: the flash began and the recording
   * stopped mid-plateau, leaving it undetectable. The bookend anchor exists
   * precisely so the aligner can fit a RATE rather than just an offset
   * (consumer clocks differ by tens of ppm), and losing it silently costs
   * exactly the thing two clappers were for.
   */
  clapperPostrollMs: 600,
  /** Settle time before the flash, so the baseline luminance is stable. */
  clapperPrerollMs: 1500,
  /** Time to saccade to a newly-appeared target before sampling starts. */
  saccadeMs: 800,
  /**
   * Minimum time an instruction stays up before it can be dismissed.
   *
   * Instructions are self-paced — they wait for the participant rather than
   * expiring on a timer. The previous 4-second auto-advance meant a slower
   * reader simply missed them, with no way to get them back, and §5.1
   * attributes roughly half of a documented 46-66% attrition to avoidable
   * instruction and validation failure. A participant who did not finish
   * reading is exactly that kind of avoidable loss.
   *
   * The floor exists only to stop a reflexive keypress skipping a screen before
   * it has been seen at all.
   */
  instructionMinMs: 1200,
  /** Sampling window per calibration point. */
  calibrationDwellMs: 1200,
  /** Sampling window per validation point. */
  validationDwellMs: 1500,
  fixationMs: 60_000,
};

/**
 * Deterministic shuffle, seeded per session.
 *
 * Calibration points MUST NOT be presented in a fixed spatial order, and that
 * is not a stylistic preference — it was measured. Presenting the 13-point grid
 * row by row makes target position a function of elapsed time: on a real
 * session, target y correlated with presentation order at **r = +0.56**.
 *
 * Any feature that drifts over the session then becomes a proxy for target
 * position. Head pitch drifted at r = +0.86 with order while carrying almost no
 * genuine vertical-gaze signal (r = +0.19 with target y), and a linear model
 * duly used it to predict y. Leave-one-out cross-validation cannot detect this,
 * because the held-out point's temporal neighbours stay in the training set —
 * so the model that leaked hardest looked BEST by LOOCV (2.62 deg) while
 * scoring worst on genuinely held-out targets (5.04 deg).
 *
 * Randomising the order decorrelates target from time and the failure mode
 * disappears. §5.1 notes jsPsych presents its grid in fixed order unless
 * randomised; this is the reason to randomise it.
 *
 * Seeded rather than free-running so a session can be replayed exactly.
 */
export function seededShuffle(items, seed) {
  // mulberry32 — small, fast, and adequate for ordering 13 items. Not for
  // anything where the randomness itself needs to be unguessable.
  let a = seed >>> 0;
  const rand = () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  const out = [...items];
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/**
 * Build the M0 sequence as a list of stage descriptors.
 *
 * Every stage a participant could be confused by is preceded by an instruction,
 * and each one says what will happen, what to do, and how long it lasts. That
 * last part matters more than it looks: the fixation stage is sixty seconds of
 * staring at a cross, and a participant who does not know it is sixty seconds
 * has no way to tell it apart from the page having frozen.
 */
export function buildM0Sequence(seed = (Date.now() >>> 0)) {
  return [
    { type: 'instruction', id: 'intro',
      title: 'Here is what happens next',
      lines: [
        'Four short parts, about four minutes in total.',
        '1. The screen flashes white once. This syncs the recording — it is expected.',
        '2. A dot appears in 13 places. Look at each one.',
        '3. The same again in 5 more places, to check the first part worked.',
        '4. A cross in the middle. Rest your eyes on it for one minute.',
        'Please keep your head still and stay roughly where you are now throughout.',
      ] },

    { type: 'instruction', id: 'clapper_intro',
      title: 'The screen will flash',
      lines: [
        'In a moment the whole screen turns white for a split second.',
        'Nothing is required from you — just keep looking at the screen.',
        'This lets us line the video up with what was on screen, to the frame.',
      ] },
    { type: 'sync_clapper', id: 'clapper_1' },

    { type: 'instruction', id: 'calib_intro',
      title: 'Follow the dot',
      lines: [
        'A dot will appear, hold still for a moment, then jump somewhere else.',
        'Look straight at the centre of each dot and keep looking until it moves.',
        'Move your EYES, not your head — try to keep your head still.',
        '13 dots, about 30 seconds.',
      ] },
    ...seededShuffle(CALIBRATION_POINTS, seed).map((p, i) => ({
      type: 'calibration_point', id: `calib_${i}`, x: p[0], y: p[1],
      index: i + 1, total: CALIBRATION_POINTS.length,
    })),

    { type: 'instruction', id: 'valid_intro',
      title: 'Once more, to check it worked',
      lines: [
        'The same task again, in 5 new places.',
        'This one measures how well the first part went, so it is worth the same care.',
        '5 dots, about 10 seconds.',
      ] },
    ...seededShuffle(VALIDATION_POINTS, seed ^ 0x9E3779B9).map((p, i) => ({
      type: 'validation_point', id: `valid_${i}`, x: p[0], y: p[1],
      index: i + 1, total: VALIDATION_POINTS.length,
    })),

    { type: 'instruction', id: 'fixation_intro',
      title: 'Now just rest your eyes',
      lines: [
        'A cross will appear in the middle of the screen.',
        'Look at it and let your face relax. There is nothing to do and nothing to press.',
        'This lasts one minute. A countdown will show how long is left.',
        'Blinking is completely fine — please do not try to hold your eyes open.',
      ] },
    { type: 'fixation', id: 'fixation_1', durationMs: TIMINGS.fixationMs },

    { type: 'instruction', id: 'clapper_2_intro',
      title: 'One more flash, then you are done',
      lines: [
        'The screen flashes white once more to close the recording.',
        'Again, nothing is required — keep looking at the screen.',
      ] },
    { type: 'sync_clapper', id: 'clapper_2' },
  ];
}

/**
 * Two clappers, not one.
 *
 * One anchor gives an offset but cannot estimate drift. Two, separated by the
 * length of the session, let the aligner fit a rate as well — consumer clocks
 * routinely differ by tens of ppm, which accumulates to real skew over a long
 * recording. Bookending the session is the cheapest way to get the second
 * anchor, and it costs the participant under half a second.
 */
export function clapperCount(sequence) {
  return sequence.filter((s) => s.type === 'sync_clapper').length;
}

/** Sum of stage durations, for a participant-facing time estimate. */
export function estimateDurationMs(sequence) {
  let total = 0;
  for (const stage of sequence) {
    switch (stage.type) {
      case 'sync_clapper':
        total += TIMINGS.clapperPrerollMs + TIMINGS.clapperFlashMs
          + TIMINGS.clapperPostrollMs;
        break;
      case 'calibration_point':
        total += TIMINGS.saccadeMs + TIMINGS.calibrationDwellMs;
        break;
      case 'validation_point':
        total += TIMINGS.saccadeMs + TIMINGS.validationDwellMs;
        break;
      case 'fixation':
        total += stage.durationMs ?? TIMINGS.fixationMs;
        break;
      case 'instruction':
        // Genuinely participant-paced now, so any number here is an allowance
        // rather than a duration. Six seconds is a reasonable reading estimate
        // for these screens and keeps the participant-facing estimate honest.
        total += 6000;
        break;
      default:
        break;
    }
  }
  return total;
}

/**
 * Validation error in degrees of visual angle.
 *
 * Requires a per-participant viewing distance — §5.1 measured mean 47.3cm with
 * SD 8.9 across 1,153 online participants, so a nominal distance is useless.
 * Returns null rather than guessing when geometry is unavailable: a dva figure
 * computed from an assumed distance is not a dva figure.
 *
 * @param {{x:number,y:number}} target normalised 0..1
 * @param {{x:number,y:number}} estimate normalised 0..1
 * @param {{viewingDistanceMm:number|null, pxPerMm:number|null,
 *          viewportWidthPx:number, viewportHeightPx:number}} geometry
 */
export function errorInDegrees(target, estimate, geometry) {
  const { viewingDistanceMm, pxPerMm, viewportWidthPx, viewportHeightPx } = geometry;
  if (!viewingDistanceMm || !pxPerMm) return null;

  const dxPx = (target.x - estimate.x) * viewportWidthPx;
  const dyPx = (target.y - estimate.y) * viewportHeightPx;
  const distanceMm = Math.hypot(dxPx, dyPx) / pxPerMm;
  return (Math.atan2(distanceMm, viewingDistanceMm) * 180) / Math.PI;
}

/**
 * Decide whether calibration is good enough to proceed.
 *
 * §5.1 documents the pattern worth copying from Kaduk et al. — a gate with
 * forced RETRY, not an exclusion. Nobody is dropped by failing it; they are
 * asked to recalibrate. The threshold itself is the researcher's to
 * pre-register: §5.3 notes jsPsych publishes no pass/fail cutoff, so a default
 * here would be inventing a standard that does not exist.
 *
 * @param {number[]} errorsDeg per-point error, may contain nulls
 * @param {{maxMeanErrorDeg:number, minPointsMeasured:number}} criteria
 */
export function evaluateCalibration(errorsDeg, criteria) {
  const measured = errorsDeg.filter((e) => e !== null && Number.isFinite(e));

  if (measured.length < criteria.minPointsMeasured) {
    return {
      pass: false,
      reason: 'insufficient_points',
      detail: `${measured.length} of ${errorsDeg.length} points measured`,
      meanErrorDeg: null,
    };
  }

  const mean = measured.reduce((a, b) => a + b, 0) / measured.length;
  return {
    pass: mean <= criteria.maxMeanErrorDeg,
    reason: mean <= criteria.maxMeanErrorDeg ? null : 'error_above_threshold',
    detail: `mean ${mean.toFixed(2)}° vs threshold ${criteria.maxMeanErrorDeg}°`,
    meanErrorDeg: mean,
  };
}

/** Sleep helper that resolves on the master clock, for sequencing. */
export function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function stageLabel(stage) {
  switch (stage.type) {
    case 'sync_clapper': return 'Synchronising';
    case 'calibration_point': return 'Calibrating';
    case 'validation_point': return 'Checking calibration';
    case 'fixation': return 'Recording';
    case 'instruction': return 'Instructions';
    default: return stage.type;
  }
}

export { now };

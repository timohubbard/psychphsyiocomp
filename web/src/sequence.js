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
  /** Settle time before the flash, so the baseline luminance is stable. */
  clapperPrerollMs: 1500,
  /** Time to saccade to a newly-appeared target before sampling starts. */
  saccadeMs: 800,
  /** Sampling window per calibration point. */
  calibrationDwellMs: 1200,
  /** Sampling window per validation point. */
  validationDwellMs: 1500,
  fixationMs: 60_000,
};

/** Build the M0 sequence as a list of stage descriptors. */
export function buildM0Sequence() {
  return [
    { type: 'sync_clapper', id: 'clapper_1' },
    { type: 'instruction', id: 'calib_intro',
      text: 'Follow the dot with your eyes. Keep your head still.' },
    ...CALIBRATION_POINTS.map((p, i) => ({
      type: 'calibration_point', id: `calib_${i}`, x: p[0], y: p[1],
    })),
    { type: 'instruction', id: 'valid_intro',
      text: 'Once more — the same again, to check the calibration held.' },
    ...VALIDATION_POINTS.map((p, i) => ({
      type: 'validation_point', id: `valid_${i}`, x: p[0], y: p[1],
    })),
    { type: 'fixation', id: 'fixation_1', durationMs: TIMINGS.fixationMs },
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
        total += TIMINGS.clapperPrerollMs + TIMINGS.clapperFlashMs;
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
        total += 4000; // participant-paced in practice; a rough allowance
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

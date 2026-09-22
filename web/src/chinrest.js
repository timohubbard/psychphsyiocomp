/**
 * Virtual chinrest — per-participant screen geometry.
 *
 * Port of the method in jsPsych's `virtual-chinrest` plugin (MIT), after Li,
 * Joo, Yeatman & Reinecke. Two tasks, two unknowns:
 *
 *   1. CARD      — the participant resizes an on-screen rectangle to match a
 *                  real ID-1 card held against the screen.    →  px per mm
 *   2. BLINDSPOT — one eye closed, fixating a cross, they mark where a moving
 *                  dot vanishes into the optic disc.          →  viewing distance
 *
 * Why this is not optional: §5.1 measured viewing distance across 1,153 online
 * participants at mean 47.3cm, SD 8.9, range 17.4-68.3cm. A degrees-of-visual-
 * angle figure computed from a nominal distance is not a dva figure, it is a
 * pixel count wearing a unit. `sequence.errorInDegrees` already refuses to
 * return a number without the geometry this module recovers, and this module
 * refuses to return geometry it does not believe.
 *
 * Everything here is pure arithmetic over numbers the DOM layer collected, so
 * the entire error budget is unit-testable without a browser.
 */

/**
 * ISO/IEC 7810 ID-1 — the bank card / driving licence format, and the reason
 * this task works at all: nearly everyone has one, and it is the same size
 * everywhere in the world to a tenth of a millimetre.
 */
export const CARD_WIDTH_MM = 85.60;
export const CARD_HEIGHT_MM = 53.98;

/**
 * Temporal eccentricity of the blind spot, in degrees.
 *
 * This is a FIXED GROUP-LEVEL CONSTANT, not a per-participant measurement, and
 * that is the honest headline of the whole method. §5.1 records the validated
 * spread across participants as 11.53-16.01 degrees (mean 13.59, SD 0.96). We
 * use 13.5 to stay bit-compatible with jsPsych rather than 13.59, because the
 * 0.09 difference is a twentieth of the SD — invisible next to the real error —
 * and matching the reference implementation is worth more than false precision.
 */
export const BLIND_SPOT_DEGREES = 13.5;

/** SD of that eccentricity across participants (§5.1). Drives the error budget. */
export const BLIND_SPOT_SD_DEGREES = 0.96;

/**
 * Published accuracy floor for the whole method: 2.4-5.5cm MAE (§5.1).
 *
 * We take the pessimistic end. No participant's estimate may claim better
 * accuracy than the method has ever demonstrated, however tightly their own
 * repetitions happened to agree — see `deriveGeometry`.
 */
export const PUBLISHED_MAE_MM = 55;

const deg2rad = (d) => (d * Math.PI) / 180;

// ---------------------------------------------------------------------------
// task 1 — card resizing
// ---------------------------------------------------------------------------

/**
 * Pixel scale from the resized card.
 *
 * @param {number} renderedWidthPx width the participant settled on, in CSS px
 * @returns {number} CSS pixels per millimetre
 */
export function pxPerMmFromCard(renderedWidthPx) {
  return renderedWidthPx / CARD_WIDTH_MM;
}

/**
 * Plausibility bounds on pixel density.
 *
 * Roughly 0.7x to 8x CSS-reference density (96dpi is 3.78 px/mm), spanning
 * everything from a CSS-pixel-honest desktop display to a high-DPR phone
 * reporting physical pixels. Outside this the participant has near-certainly
 * dragged the rectangle to the wrong size, or the page is zoomed.
 */
export const PX_PER_MM_BOUNDS = { min: 2.5, max: 30 };

/**
 * Plausibility gate on the card task.
 *
 * §5.1 is blunt about why this earns its place: published Prolific deployments
 * using these procedures discarded 66% and 46% of participants, and roughly
 * HALF that loss was avoidable form-validation failure — implausible
 * self-reported height, incorrectly-measured reference objects. That half is an
 * engineering problem, not a recruitment cost.
 *
 * So the check runs at the moment of entry, where the participant can still fix
 * it by trying again, rather than at analysis time where it can only be counted
 * as attrition.
 */
export function checkCardPlausible(pxPerMm) {
  if (!Number.isFinite(pxPerMm) || pxPerMm <= 0) {
    return { plausible: false, reason: 'not_a_number', detail: 'no usable measurement' };
  }
  // The reason codes name what the PARTICIPANT did, not what the arithmetic
  // implies about the screen. A low px/mm means the drawn rectangle was small,
  // which is the same fact as "this screen would have to be enormous" — but
  // only one of those two phrasings tells the participant which way to drag,
  // and they are the only person who can fix it.
  if (pxPerMm < PX_PER_MM_BOUNDS.min) {
    return {
      plausible: false,
      reason: 'card_drawn_too_small',
      detail: 'That outline is smaller than a real card. Drag the corner out until it matches yours exactly.',
    };
  }
  if (pxPerMm > PX_PER_MM_BOUNDS.max) {
    return {
      plausible: false,
      reason: 'card_drawn_too_large',
      detail: 'That outline is larger than a real card. Drag the corner in until it matches yours exactly.',
    };
  }
  return { plausible: true, reason: null, detail: null };
}

// ---------------------------------------------------------------------------
// task 2 — blind spot
// ---------------------------------------------------------------------------

/**
 * Viewing distance from one blind-spot repetition.
 *
 * The fixation cross, the optic disc's projection, and the eye form a right
 * triangle. The angle at the eye is the assumed 13.5 degrees; the opposite side
 * is the on-screen distance from cross to vanishing dot. Hence d = s / tan(theta).
 *
 * @param {number} ballDistancePx cross-to-vanish distance, CSS px
 * @param {number} pxPerMm from the card task
 * @returns {number} viewing distance in mm
 */
export function viewingDistanceMmFromBlindSpot(ballDistancePx, pxPerMm) {
  const ballDistanceMm = ballDistancePx / pxPerMm;
  return ballDistanceMm / Math.tan(deg2rad(BLIND_SPOT_DEGREES));
}

/**
 * Relative uncertainty in viewing distance implied by the eccentricity SD.
 *
 * d = s * cot(theta), so dd/dtheta = -s * csc^2(theta), and the relative error is
 *
 *     sigma_d / d = sigma_theta * csc^2(theta) / cot(theta)
 *                 = sigma_theta * 2 / sin(2 * theta)
 *
 * which at theta = 13.5 and sigma_theta = 0.96 degrees comes out at 7.4%.
 * Applied to the §5.1 population mean distance of 47.3cm that is ±3.5cm —
 * landing inside the published 2.4-5.5cm MAE range from a completely
 * independent direction.
 *
 * That agreement is the point of computing it rather than hard-coding a number.
 * The reported error budget is *derived* from the stated assumption, so
 * changing the eccentricity constant moves the uncertainty with it instead of
 * silently invalidating a figure copied from an abstract.
 */
export function eccentricityRelativeError() {
  const theta = deg2rad(BLIND_SPOT_DEGREES);
  const sigma = deg2rad(BLIND_SPOT_SD_DEGREES);
  return (sigma * 2) / Math.sin(2 * theta);
}

/**
 * Fraction of the intended stimulus size the residual error propagates to.
 *
 * §5.1 quotes 0.11-0.18x. This is the same quantity arrived at directly, and is
 * what a study designer should quote in a methods section.
 */
export function stimulusSizeErrorFraction() {
  return eccentricityRelativeError();
}

/**
 * Combine blind-spot repetitions.
 *
 * MEDIAN, not mean. The characteristic failure of this task is not noise, it is
 * a participant who blinked, lost fixation, or closed the wrong eye on a single
 * repetition — which produces an outlier, not a spread. A mean carries that
 * outlier into the estimate; a median discards it. jsPsych averages five
 * repetitions; we keep the five and take the middle.
 *
 * The spread across repetitions is returned separately and is PRECISION, not
 * accuracy. It says the participant did the same thing five times, which is
 * evidence they followed the instructions, and no evidence whatever that 13.5
 * degrees is their true eccentricity. `deriveGeometry` keeps those two apart,
 * because conflating them is how a method with 5.5cm MAE starts reporting
 * millimetre confidence.
 */
export function summariseBlindSpotReps(distancesMm) {
  const valid = distancesMm.filter((d) => Number.isFinite(d) && d > 0);
  if (valid.length === 0) {
    return { medianMm: null, spreadMm: null, n: 0, nRejected: distancesMm.length };
  }

  const sorted = [...valid].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  const medianMm = sorted.length % 2 === 1
    ? sorted[mid]
    : (sorted[mid - 1] + sorted[mid]) / 2;

  // Median absolute deviation rather than the full range: with n=5 the range is
  // dominated by whichever single repetition went worst, which is exactly what
  // choosing a median was meant to ignore.
  const deviations = sorted.map((d) => Math.abs(d - medianMm)).sort((a, b) => a - b);
  const spreadMm = deviations[Math.floor(deviations.length / 2)];

  return {
    medianMm,
    spreadMm,
    n: valid.length,
    nRejected: distancesMm.length - valid.length,
  };
}

/**
 * Consistency gate. Wide disagreement across repetitions means the task was not
 * performed as instructed — almost always head movement between repetitions, or
 * both eyes left open.
 *
 * Expressed as a fraction of the estimate rather than an absolute, because a
 * 2cm disagreement at 25cm and at 65cm are not the same finding.
 */
export const MAX_REP_SPREAD_FRACTION = 0.15;
export const MIN_USABLE_REPS = 3;

/**
 * Physically possible viewing distances.
 *
 * Consistency is not plausibility, and this is the gap between them. A
 * participant who taps space five times in quick succession produces five
 * closely-agreeing repetitions — they sail through `MAX_REP_SPREAD_FRACTION` —
 * and yield a viewing distance of a couple of centimetres. Nothing upstream
 * catches it: the card was fine, the reps agreed, the arithmetic is correct.
 * The result is confident-looking geometry wrong by a factor of twenty.
 *
 * §5.1 observed 17.4-68.3cm across 1,153 participants. These bounds sit outside
 * that range on both sides, because the job here is to reject the impossible,
 * not to enforce the typical — someone on a large monitor legitimately sits
 * further back than anyone in that sample did. Below 15cm the eye cannot focus;
 * beyond 100cm a webcam cannot resolve the eyes well enough for gaze anyway.
 */
export const VIEWING_DISTANCE_BOUNDS_MM = { min: 150, max: 1000 };

// ---------------------------------------------------------------------------
// combined geometry
// ---------------------------------------------------------------------------

/**
 * Turn the two tasks into the geometry record the session carries, or refuse.
 *
 * Refusal follows the same contract as the alignment service — a null with a
 * recorded reason, never a plausible-looking default — and for the same reason:
 * geometry that silently falls back to 50cm produces dva figures wrong by an
 * unknown amount that look exactly like dva figures that are right.
 * `errorInDegrees` already returns null on null geometry, so a refusal here
 * propagates instead of being swallowed at the boundary.
 *
 * @param {{cardWidthPx:number|null, blindSpotDistancesPx:number[]}} raw
 * @returns geometry record matching the `sessions` columns in canonical_tables.sql
 */
export function deriveGeometry(raw) {
  const refuse = (reason, detail) => ({
    viewing_distance_mm: null,
    px_per_mm: null,
    geometry_method: 'unknown',
    geometry_error_mm: null,
    ok: false,
    reason,
    detail,
  });

  if (!Number.isFinite(raw?.cardWidthPx) || raw.cardWidthPx <= 0) {
    return refuse('card_task_missing', 'no card measurement recorded');
  }

  const pxPerMm = pxPerMmFromCard(raw.cardWidthPx);
  const card = checkCardPlausible(pxPerMm);
  if (!card.plausible) return refuse(card.reason, card.detail);

  const distances = (raw.blindSpotDistancesPx ?? []).map(
    (px) => (Number.isFinite(px) && px > 0
      ? viewingDistanceMmFromBlindSpot(px, pxPerMm)
      : NaN),
  );

  const reps = summariseBlindSpotReps(distances);
  if (reps.n < MIN_USABLE_REPS) {
    return refuse('blind_spot_insufficient_reps',
      `${reps.n} usable repetitions, need ${MIN_USABLE_REPS}`);
  }

  // Plausibility before consistency, because consistency cannot detect this.
  if (reps.medianMm < VIEWING_DISTANCE_BOUNDS_MM.min) {
    return refuse('viewing_distance_too_near',
      `${(reps.medianMm / 10).toFixed(1)}cm is nearer than anyone sits — `
      + 'the dot was probably marked before it actually disappeared');
  }
  if (reps.medianMm > VIEWING_DISTANCE_BOUNDS_MM.max) {
    return refuse('viewing_distance_too_far',
      `${(reps.medianMm / 10).toFixed(1)}cm is further than a webcam can track — `
      + 'the dot was probably missed as it vanished');
  }

  const spreadFraction = reps.spreadMm / reps.medianMm;
  if (spreadFraction > MAX_REP_SPREAD_FRACTION) {
    return refuse('blind_spot_inconsistent',
      `repetitions spread ${(spreadFraction * 100).toFixed(0)}% of the estimate `
      + `(limit ${MAX_REP_SPREAD_FRACTION * 100}%) — likely head movement between repetitions`);
  }

  // The reported error is the WORST of three things, never the best:
  //   - what the method has been shown to achieve in the literature,
  //   - what this participant's eccentricity uncertainty implies,
  //   - how much this participant's own repetitions disagreed.
  // Taking the max is the entire ethic of this file. Tight repetitions are
  // evidence of a careful participant, not evidence that 13.5 degrees was their
  // eccentricity — and no amount of care on their part can measure that.
  const eccentricityErrorMm = reps.medianMm * eccentricityRelativeError();
  const errorMm = Math.max(PUBLISHED_MAE_MM, eccentricityErrorMm, reps.spreadMm);

  return {
    viewing_distance_mm: reps.medianMm,
    px_per_mm: pxPerMm,
    geometry_method: 'virtual_chinrest',
    geometry_error_mm: errorMm,
    ok: true,
    reason: null,
    detail: `${reps.n} repetitions, precision ±${reps.spreadMm.toFixed(0)}mm, `
      + `accuracy ±${errorMm.toFixed(0)}mm`,
    // Kept apart on purpose — see summariseBlindSpotReps.
    precision_mm: reps.spreadMm,
    reps_used: reps.n,
    reps_rejected: reps.nRejected,
  };
}

/**
 * Geometry in the shape `sequence.errorInDegrees` expects.
 *
 * Deliberately a separate function: `deriveGeometry` speaks the schema's
 * snake_case so its result can be written straight to a `sessions` row, and
 * this adapts it for in-page maths. Passing a refused geometry through here
 * yields nulls, so the refusal survives the trip.
 */
export function toViewportGeometry(geometry, viewportWidthPx, viewportHeightPx) {
  return {
    viewingDistanceMm: geometry?.viewing_distance_mm ?? null,
    pxPerMm: geometry?.px_per_mm ?? null,
    viewportWidthPx,
    viewportHeightPx,
  };
}

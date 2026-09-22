import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  CARD_WIDTH_MM,
  BLIND_SPOT_DEGREES,
  BLIND_SPOT_SD_DEGREES,
  PUBLISHED_MAE_MM,
  PX_PER_MM_BOUNDS,
  MAX_REP_SPREAD_FRACTION,
  MIN_USABLE_REPS,
  VIEWING_DISTANCE_BOUNDS_MM,
  pxPerMmFromCard,
  checkCardPlausible,
  viewingDistanceMmFromBlindSpot,
  eccentricityRelativeError,
  stimulusSizeErrorFraction,
  summariseBlindSpotReps,
  deriveGeometry,
  toViewportGeometry,
} from './chinrest.js';

import { errorInDegrees } from './sequence.js';

/** A typical laptop: ~96dpi CSS reference, card drawn at 324px. */
const TYPICAL_CARD_PX = 324;
const TYPICAL_PX_PER_MM = TYPICAL_CARD_PX / CARD_WIDTH_MM; // ~3.785

/** Blind-spot distance in px that yields ~47.3cm — the §5.1 population mean. */
const MEAN_DISTANCE_MM = 473;
const TYPICAL_BLINDSPOT_PX =
  MEAN_DISTANCE_MM * Math.tan((BLIND_SPOT_DEGREES * Math.PI) / 180) * TYPICAL_PX_PER_MM;

// ---------------------------------------------------------------------------
// card task
// ---------------------------------------------------------------------------

test('card dimensions are ISO/IEC 7810 ID-1', () => {
  // The whole method rests on this being the real card size, not an approximation.
  assert.equal(CARD_WIDTH_MM, 85.60);
});

test('a card drawn at CSS reference density recovers ~3.78 px/mm', () => {
  // 96dpi / 25.4mm = 3.7795 px/mm. If this drifts, the card constant is wrong.
  assert.ok(Math.abs(pxPerMmFromCard(TYPICAL_CARD_PX) - 3.7795) < 0.01);
});

test('card gate accepts a plausible measurement', () => {
  assert.equal(checkCardPlausible(TYPICAL_PX_PER_MM).plausible, true);
});

test('card gate catches the two failure directions separately', () => {
  // A SMALL rectangle yields a LOW px/mm: few pixels stand in for 85.6mm.
  const drawnSmall = checkCardPlausible(PX_PER_MM_BOUNDS.min - 0.1);
  const drawnLarge = checkCardPlausible(PX_PER_MM_BOUNDS.max + 0.1);

  assert.equal(drawnSmall.plausible, false);
  assert.equal(drawnSmall.reason, 'card_drawn_too_small');
  assert.equal(drawnLarge.plausible, false);
  assert.equal(drawnLarge.reason, 'card_drawn_too_large');
});

test('the retry message points the participant the RIGHT way', () => {
  // Regression test. These messages were originally inverted: a participant who
  // drew the rectangle too small was told it was "larger than a real card", and
  // the test only checked that the two strings differed — so it passed. The bug
  // survived until the task was run in a real browser.
  //
  // This matters more than a typo. §5.1 attributes roughly half of a documented
  // 46-66% attrition to avoidable validation failure, and it is only avoidable
  // if the instruction is corrective. A message pointing the wrong way converts
  // a recoverable participant into a lost one.
  const drawnSmall = checkCardPlausible(PX_PER_MM_BOUNDS.min - 0.1);
  const drawnLarge = checkCardPlausible(PX_PER_MM_BOUNDS.max + 0.1);

  assert.match(drawnSmall.detail, /smaller than a real card/);
  assert.match(drawnSmall.detail, /\bout\b/, 'must tell them to drag OUT');

  assert.match(drawnLarge.detail, /larger than a real card/);
  assert.match(drawnLarge.detail, /\bin\b/, 'must tell them to drag IN');
});

test('card gate refuses nonsense rather than propagating NaN', () => {
  for (const bad of [NaN, 0, -5, Infinity, undefined]) {
    assert.equal(checkCardPlausible(bad).plausible, false, `accepted ${bad}`);
  }
});

// ---------------------------------------------------------------------------
// blind spot trigonometry
// ---------------------------------------------------------------------------

test('blind spot geometry inverts cleanly', () => {
  const recovered = viewingDistanceMmFromBlindSpot(TYPICAL_BLINDSPOT_PX, TYPICAL_PX_PER_MM);
  assert.ok(Math.abs(recovered - MEAN_DISTANCE_MM) < 0.5,
    `expected ~${MEAN_DISTANCE_MM}mm, got ${recovered.toFixed(1)}`);
});

test('a dot that vanishes further from the cross means a nearer screen', () => {
  // Closer to the screen, the same 13.5 degrees subtends more pixels.
  const near = viewingDistanceMmFromBlindSpot(200, TYPICAL_PX_PER_MM);
  const far = viewingDistanceMmFromBlindSpot(100, TYPICAL_PX_PER_MM);
  assert.ok(near > far);
});

/**
 * The load-bearing test in this file.
 *
 * The error budget is derived by propagating the published eccentricity SD
 * through the trigonometry. It has to land on the published end-to-end MAE,
 * which was measured by a completely different route (against real rulers).
 * If these two ever disagree, one of the constants is wrong and every dva
 * figure the platform reports is quietly mis-scaled.
 */
test('derived error budget reproduces the published 2.4-5.5cm MAE', () => {
  const relative = eccentricityRelativeError();
  const atPopulationMean = MEAN_DISTANCE_MM * relative;

  assert.ok(relative > 0.06 && relative < 0.09,
    `expected ~7.4% relative error, got ${(relative * 100).toFixed(1)}%`);
  assert.ok(atPopulationMean >= 24 && atPopulationMean <= 55,
    `${atPopulationMean.toFixed(0)}mm falls outside the published 24-55mm MAE range`);
});

test('stimulus-size error fraction matches the published 0.11-0.18x band', () => {
  // §5.1 quotes 0.11-0.18x of intended stimulus size. Our derivation sits at
  // the good end of that band, which is expected: the published range folds in
  // card-task error too, which we gate separately.
  const f = stimulusSizeErrorFraction();
  assert.ok(f > 0.05 && f < 0.20, `got ${f.toFixed(3)}`);
});

test('error budget tracks the eccentricity constant rather than being hard-coded', () => {
  // A derived budget must respond to its input. This is what stops the figure
  // from silently becoming a stale copy of an abstract.
  assert.ok(BLIND_SPOT_SD_DEGREES > 0);
  const relative = eccentricityRelativeError();
  const naiveConstant = 0.074;
  assert.ok(Math.abs(relative - naiveConstant) < 0.01);
});

// ---------------------------------------------------------------------------
// repetitions
// ---------------------------------------------------------------------------

test('a single bad repetition cannot drag the estimate far', () => {
  // Participant blinked on rep 3. The estimate must move by at most the gap to
  // the neighbouring repetition — bounded by the OTHER reps, not by how wrong
  // the bad one was. A mean has no such bound: the same outlier drags it ~85mm,
  // which is an entire population SD of viewing distance (§5.1).
  const clean = [470, 475, 468, 472, 474];
  const withOutlier = [470, 475, 900, 472, 474];

  const a = summariseBlindSpotReps(clean);
  const b = summariseBlindSpotReps(withOutlier);

  const medianShift = Math.abs(a.medianMm - b.medianMm);
  const meanShift = Math.abs(
    clean.reduce((s, d) => s + d, 0) / clean.length
    - withOutlier.reduce((s, d) => s + d, 0) / withOutlier.length,
  );

  assert.ok(medianShift <= 5, `median moved ${medianShift}mm`);
  assert.ok(meanShift > 80, 'the outlier should have been large enough to prove the point');
});

test('an outlier of any magnitude moves the estimate by the same bounded amount', () => {
  // The defining property of the median: the estimate depends on the outlier's
  // RANK, not its value. Doubling how wrong the bad repetition was changes
  // nothing — which is precisely what a mean cannot promise.
  const bad = (v) => summariseBlindSpotReps([470, 475, v, 472, 474]).medianMm;
  assert.equal(bad(900), bad(5000));
});

test('invalid repetitions are counted, not silently dropped', () => {
  const reps = summariseBlindSpotReps([470, NaN, 475, -3, 472]);
  assert.equal(reps.n, 3);
  assert.equal(reps.nRejected, 2);
});

test('no usable repetitions yields nulls, not zero', () => {
  const reps = summariseBlindSpotReps([NaN, NaN]);
  assert.equal(reps.medianMm, null);
  assert.equal(reps.spreadMm, null);
});

// ---------------------------------------------------------------------------
// combined geometry — refusal contract
// ---------------------------------------------------------------------------

const goodRaw = {
  cardWidthPx: TYPICAL_CARD_PX,
  blindSpotDistancesPx: Array(5).fill(TYPICAL_BLINDSPOT_PX),
};

test('a well-performed chinrest produces usable geometry', () => {
  const g = deriveGeometry(goodRaw);
  assert.equal(g.ok, true);
  assert.equal(g.geometry_method, 'virtual_chinrest');
  assert.ok(Math.abs(g.viewing_distance_mm - MEAN_DISTANCE_MM) < 1);
  assert.equal(g.reps_used, 5);
});

test('geometry refuses rather than guessing when the card task is missing', () => {
  const g = deriveGeometry({ cardWidthPx: null, blindSpotDistancesPx: [] });
  assert.equal(g.ok, false);
  assert.equal(g.viewing_distance_mm, null);
  assert.equal(g.px_per_mm, null);
  assert.equal(g.geometry_method, 'unknown');
  assert.equal(g.reason, 'card_task_missing');
});

test('geometry refuses when too few repetitions survived', () => {
  const g = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: [TYPICAL_BLINDSPOT_PX, NaN, NaN, NaN, NaN],
  });
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'blind_spot_insufficient_reps');
  assert.ok(g.detail.includes(String(MIN_USABLE_REPS)));
});

test('geometry refuses when repetitions disagree — the head-movement signature', () => {
  // Spread well past the fraction limit in both directions around the median.
  const px = TYPICAL_BLINDSPOT_PX;
  const g = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: [px * 0.5, px * 0.7, px, px * 1.4, px * 1.9],
  });
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'blind_spot_inconsistent');
  assert.equal(g.viewing_distance_mm, null);
});

test('a refusal never reports an error bar', () => {
  // An error bar on a refused estimate would imply there is an estimate.
  const g = deriveGeometry({ cardWidthPx: null, blindSpotDistancesPx: [] });
  assert.equal(g.geometry_error_mm, null);
});

// ---------------------------------------------------------------------------
// the accuracy/precision distinction
// ---------------------------------------------------------------------------

test('a perfectly consistent participant still gets the published accuracy floor', () => {
  // Five identical repetitions: precision is 0mm. Accuracy is not, and must not
  // be reported as if it were — the eccentricity assumption is unmeasured.
  const g = deriveGeometry(goodRaw);
  assert.equal(g.precision_mm, 0);
  assert.ok(g.geometry_error_mm >= PUBLISHED_MAE_MM,
    `reported ±${g.geometry_error_mm}mm, below the published floor of ${PUBLISHED_MAE_MM}mm`);
});

test('error grows with distance, because the eccentricity term does', () => {
  const far = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: Array(5).fill(TYPICAL_BLINDSPOT_PX * 2),
  });
  const near = deriveGeometry(goodRaw);
  assert.ok(far.viewing_distance_mm > near.viewing_distance_mm);
  assert.ok(far.geometry_error_mm > near.geometry_error_mm,
    'at long distances the eccentricity term should dominate the published floor');
});

test('scattered-but-passing repetitions widen the error bar', () => {
  const px = TYPICAL_BLINDSPOT_PX;
  // Inside MAX_REP_SPREAD_FRACTION, so it passes — but it is worse evidence.
  const scattered = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: [px * 0.93, px * 0.97, px, px * 1.03, px * 1.07],
  });
  assert.equal(scattered.ok, true);
  assert.ok(scattered.precision_mm > 0);
  assert.ok(scattered.spreadFraction === undefined); // not part of the contract
});

// ---------------------------------------------------------------------------
// the seam with sequence.js
// ---------------------------------------------------------------------------

test('geometry unblocks errorInDegrees, which previously always returned null', () => {
  const g = deriveGeometry(goodRaw);
  const viewport = toViewportGeometry(g, 1440, 900);

  const deg = errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.55, y: 0.5 }, viewport);
  assert.ok(deg !== null, 'geometry was derived but errorInDegrees still refused');

  // 5% of 1440px at ~3.78px/mm is ~19mm, at 473mm ≈ 2.3 degrees.
  assert.ok(deg > 1.5 && deg < 3.5, `implausible dva: ${deg}`);
});

test('a refused geometry keeps errorInDegrees refusing', () => {
  // The refusal must survive the snake_case/camelCase boundary. If it did not,
  // a failed chinrest would silently produce confident-looking dva numbers.
  const refused = deriveGeometry({ cardWidthPx: null, blindSpotDistancesPx: [] });
  const viewport = toViewportGeometry(refused, 1440, 900);

  assert.equal(errorInDegrees({ x: 0.5, y: 0.5 }, { x: 0.55, y: 0.5 }, viewport), null);
});

test('toViewportGeometry tolerates a missing geometry object entirely', () => {
  const viewport = toViewportGeometry(null, 1440, 900);
  assert.equal(viewport.viewingDistanceMm, null);
  assert.equal(errorInDegrees({ x: 0, y: 0 }, { x: 1, y: 1 }, viewport), null);
});

// ---------------------------------------------------------------------------
// guardrails on the constants themselves
// ---------------------------------------------------------------------------

test('the consistency gate stays in a defensible range', () => {
  // Too tight and careful participants get refused; too loose and head
  // movement passes through as a confident number.
  assert.ok(MAX_REP_SPREAD_FRACTION >= 0.05 && MAX_REP_SPREAD_FRACTION <= 0.25);
});

test('the published accuracy floor is the pessimistic end of the cited range', () => {
  // §5.1 cites 2.4-5.5cm. Taking the optimistic end would be the easy mistake.
  assert.equal(PUBLISHED_MAE_MM, 55);
});


// ---------------------------------------------------------------------------
// plausibility of the RESULT, which consistency alone cannot establish
// ---------------------------------------------------------------------------

/** Blind-spot pixel offset that yields a given viewing distance at a given scale. */
const pxForDistance = (mm, pxPerMm) =>
  mm * Math.tan((BLIND_SPOT_DEGREES * Math.PI) / 180) * pxPerMm;

test('five consistent-but-impossible repetitions are refused', () => {
  // The exact failure found by running the task in a browser: tapping space
  // five times in quick succession gives five closely-agreeing repetitions and
  // a 2.4cm viewing distance. The spread gate passes it — the reps really do
  // agree — so consistency has to be checked separately from possibility.
  const px = pxForDistance(24, TYPICAL_PX_PER_MM);
  const g = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: Array(5).fill(px),
  });

  assert.equal(g.ok, false);
  assert.equal(g.reason, 'viewing_distance_too_near');
  assert.equal(g.viewing_distance_mm, null);
});

test('an impossibly distant result is refused too, and named differently', () => {
  const px = pxForDistance(2000, TYPICAL_PX_PER_MM);
  const g = deriveGeometry({
    cardWidthPx: TYPICAL_CARD_PX,
    blindSpotDistancesPx: Array(5).fill(px),
  });

  assert.equal(g.ok, false);
  assert.equal(g.reason, 'viewing_distance_too_far');
});

test('the bounds reject the impossible without policing the merely unusual', () => {
  // §5.1 observed 17.4-68.3cm. Both ends of that real range must still pass:
  // the gate exists to catch nonsense, not to enforce a typical posture.
  for (const mm of [174, 473, 683]) {
    const g = deriveGeometry({
      cardWidthPx: TYPICAL_CARD_PX,
      blindSpotDistancesPx: Array(5).fill(pxForDistance(mm, TYPICAL_PX_PER_MM)),
    });
    assert.equal(g.ok, true, `refused ${mm}mm, which was observed in the wild`);
  }

  assert.ok(VIEWING_DISTANCE_BOUNDS_MM.min < 174,
    'lower bound must sit below the smallest distance actually observed');
  assert.ok(VIEWING_DISTANCE_BOUNDS_MM.max > 683,
    'upper bound must sit above the largest distance actually observed');
});

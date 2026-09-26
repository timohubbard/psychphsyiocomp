/**
 * The browser placement computes the same features as the server placement.
 *
 * Both suites read ../fixtures/landmarks_golden.json, whose expected values
 * the SERVER engine produced. If either implementation changes its maths, one
 * suite fails — rather than browser-processed and server-processed sessions
 * quietly measuring different things.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { FEATURE_CHANNELS, eyeFeatures, featuresFromLandmarks } from './features.js';

const golden = JSON.parse(readFileSync(
  new URL('../fixtures/landmarks_golden.json', import.meta.url), 'utf8'));

test('every golden frame reproduces the server engine to 1e-9', () => {
  for (const [i, f] of golden.frames.entries()) {
    const lm = f.landmarks.map(([x, y]) => ({ x, y }));
    const got = featuresFromLandmarks(lm, golden.width_px, golden.height_px);
    if (f.expected === null) {
      assert.equal(got, null, `frame ${i} should be unusable`);
      continue;
    }
    assert.deepEqual(Object.keys(got).sort(), Object.keys(f.expected).sort(), `frame ${i} channels`);
    for (const [ch, v] of Object.entries(f.expected)) {
      assert.ok(Math.abs(got[ch] - v) < 1e-9, `frame ${i} ${ch}: ${got[ch]} vs ${v}`);
    }
  }
});

test('the fixture exercises open eyes, a near-blink and an unusable frame', () => {
  const kinds = golden.frames.map((f) => (f.expected === null ? 'null'
    : f.expected['eye.left_openness'] < 0.1 ? 'closed' : 'open'));
  assert.deepEqual(kinds, ['open', 'closed', 'null']);
});

test('coincident eye corners are unusable, not a division by zero', () => {
  assert.ok(eyeFeatures([1, 1], [0, 0], [0, 0], [0, 1], [0, 2]).every(Number.isNaN));
});

test('too few landmarks is unusable', () => {
  assert.equal(featuresFromLandmarks([{ x: 0, y: 0 }], 100, 100), null);
});

test('the channel order is the server engine\'s', () => {
  // Pinned literally: FEATURE_CHANNELS in ../server/engine.py.
  assert.deepEqual(FEATURE_CHANNELS, [
    'eye.left_iris_dx', 'eye.left_iris_dy', 'eye.right_iris_dx', 'eye.right_iris_dy',
    'eye.left_openness', 'eye.right_openness', 'eye.inter_ocular_px',
    'head_pose.yaw', 'head_pose.pitch', 'head_pose.roll',
  ]);
});

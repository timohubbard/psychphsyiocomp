import { test } from 'node:test';
import assert from 'node:assert/strict';

import { eulerFromMatrix, meanLuma, toDegrees } from './pose.js';

/** Build a 16-element COLUMN-MAJOR matrix from a row-major 3x3 rotation. */
function colMajorFrom3x3(r) {
  const m = new Float32Array(16);
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      m[col * 4 + row] = r[row][col];
    }
  }
  m[15] = 1;
  return m;
}

const identity3 = [
  [1, 0, 0],
  [0, 1, 0],
  [0, 0, 1],
];

function rotY(deg) {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t), s = Math.sin(t);
  return [
    [c, 0, s],
    [0, 1, 0],
    [-s, 0, c],
  ];
}

function rotX(deg) {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t), s = Math.sin(t);
  return [
    [1, 0, 0],
    [0, c, -s],
    [0, s, c],
  ];
}

function rotZ(deg) {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t), s = Math.sin(t);
  return [
    [c, -s, 0],
    [s, c, 0],
    [0, 0, 1],
  ];
}

const CLOSE = 1e-4;

test('identity matrix yields zero rotation', () => {
  const { yaw, pitch, roll } = eulerFromMatrix(colMajorFrom3x3(identity3));
  assert.ok(Math.abs(yaw) < CLOSE, `yaw ${yaw}`);
  assert.ok(Math.abs(pitch) < CLOSE, `pitch ${pitch}`);
  assert.ok(Math.abs(roll) < CLOSE, `roll ${roll}`);
});

test('pure yaw is recovered on the yaw axis only', () => {
  for (const deg of [-60, -30, -5, 5, 30, 60]) {
    const { yaw, pitch, roll } = eulerFromMatrix(colMajorFrom3x3(rotY(deg)));
    assert.ok(Math.abs(yaw - deg) < 1e-3, `yaw ${yaw} != ${deg}`);
    assert.ok(Math.abs(pitch) < 1e-3, `pitch leaked: ${pitch}`);
    assert.ok(Math.abs(roll) < 1e-3, `roll leaked: ${roll}`);
  }
});

test('pure pitch is recovered on the pitch axis only', () => {
  // A nod must read as pitch, never as roll. Under the aerospace Z-Y-X
  // convention this lands in roll instead — that was a real bug this pinned.
  for (const deg of [-45, -20, 20, 45]) {
    const { yaw, pitch, roll } = eulerFromMatrix(colMajorFrom3x3(rotX(deg)));
    assert.ok(Math.abs(pitch - deg) < 1e-3, `pitch ${pitch} != ${deg}`);
    assert.ok(Math.abs(yaw) < 1e-3, `yaw leaked: ${yaw}`);
    assert.ok(Math.abs(roll) < 1e-3, `roll leaked: ${roll}`);
  }
});

test('pure roll is recovered on the roll axis only', () => {
  // A head tilt toward the shoulder must read as roll, with no yaw leakage.
  for (const deg of [-40, -15, 15, 40]) {
    const { yaw, pitch, roll } = eulerFromMatrix(colMajorFrom3x3(rotZ(deg)));
    assert.ok(Math.abs(roll - deg) < 1e-3, `roll ${roll} != ${deg}`);
    assert.ok(Math.abs(yaw) < 1e-3, `yaw leaked: ${yaw}`);
    assert.ok(Math.abs(pitch) < 1e-3, `pitch leaked: ${pitch}`);
  }
});

test('the three axes stay independent under combined rotation', () => {
  // Composed as Ry·Rx·Rz, matching the decomposition. Angles kept modest to
  // stay well clear of gimbal lock at pitch = +/-90.
  const compose = (a, b) =>
    a.map((row, i) => row.map((_, j) => row.reduce((s, v, k) => s + v * b[k][j], 0)));
  const expected = { yaw: 25, pitch: -15, roll: 10 };
  const R = compose(compose(rotY(expected.yaw), rotX(expected.pitch)), rotZ(expected.roll));
  const got = eulerFromMatrix(colMajorFrom3x3(R));
  for (const axis of ['yaw', 'pitch', 'roll']) {
    assert.ok(Math.abs(got[axis] - expected[axis]) < 1e-3,
      `${axis}: got ${got[axis]}, expected ${expected[axis]}`);
  }
});

test('rejects a malformed matrix rather than returning NaN', () => {
  assert.throws(() => eulerFromMatrix([1, 2, 3]), TypeError);
  assert.throws(() => eulerFromMatrix(null), TypeError);
});

test('output is finite across a sweep — no NaN from atan2 edge cases', () => {
  for (let d = -89; d <= 89; d += 7) {
    const { yaw, pitch, roll } = eulerFromMatrix(colMajorFrom3x3(rotY(d)));
    assert.ok(Number.isFinite(yaw) && Number.isFinite(pitch) && Number.isFinite(roll),
      `non-finite at ${d}deg`);
  }
});

test('toDegrees converts correctly', () => {
  assert.ok(Math.abs(toDegrees(Math.PI) - 180) < CLOSE);
  assert.ok(Math.abs(toDegrees(Math.PI / 2) - 90) < CLOSE);
  assert.ok(Math.abs(toDegrees(0)) < CLOSE);
});

test('meanLuma: pure white and pure black anchor the range', () => {
  const white = new Uint8ClampedArray([255, 255, 255, 255]);
  const black = new Uint8ClampedArray([0, 0, 0, 255]);
  assert.ok(Math.abs(meanLuma(white) - 255) < 0.01, `white -> ${meanLuma(white)}`);
  assert.equal(meanLuma(black), 0);
});

test('meanLuma: weights green most, per Rec. 601', () => {
  const red = new Uint8ClampedArray([255, 0, 0, 255]);
  const green = new Uint8ClampedArray([0, 255, 0, 255]);
  const blue = new Uint8ClampedArray([0, 0, 255, 255]);
  assert.ok(meanLuma(green) > meanLuma(red), 'green should outweigh red');
  assert.ok(meanLuma(red) > meanLuma(blue), 'red should outweigh blue');
});

test('meanLuma: averages across pixels and tolerates empty input', () => {
  // one white pixel, one black -> ~127.5
  const mixed = new Uint8ClampedArray([255, 255, 255, 255, 0, 0, 0, 255]);
  assert.ok(Math.abs(meanLuma(mixed) - 127.5) < 0.01, `mixed -> ${meanLuma(mixed)}`);
  assert.equal(meanLuma(new Uint8ClampedArray([])), 0);
  assert.equal(meanLuma(null), 0);
});

test('meanLuma: the 30-luminance bias threshold is discriminable', () => {
  // §2.5 — the rPPG skin-tone gap largely closes above luminance 30, so the
  // capture flow gates on it. Verify the metric actually separates around there.
  const dim = new Uint8ClampedArray([20, 20, 20, 255]);
  const lit = new Uint8ClampedArray([40, 40, 40, 255]);
  assert.ok(meanLuma(dim) < 30, `dim ${meanLuma(dim)} should fall below the gate`);
  assert.ok(meanLuma(lit) > 30, `lit ${meanLuma(lit)} should clear the gate`);
});

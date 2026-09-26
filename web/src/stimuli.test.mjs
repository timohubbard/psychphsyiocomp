import { test } from 'node:test';
import assert from 'node:assert/strict';

import { fitRect, preloadStimuli, rectNorm, sha256Hex, stimulusItems } from './stimuli.js';

const bytes = new TextEncoder().encode('abc');
// SHA-256("abc"), the FIPS 180-2 test vector.
const ABC = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';

const study = (sha = ABC) => ({
  tasks: [
    { type: 'calibration' },
    { type: 'stimuli', items: [{ stimulus_id: 'a', kind: 'image', src: 'stimuli/a.png', sha256: sha, duration_ms: 1000 }] },
  ],
});

const fakeFetch = (body, status = 200) => async () => ({
  ok: status === 200, status, arrayBuffer: async () => body.buffer,
  headers: { get: () => 'image/png' },
});

test('sha256Hex matches the FIPS test vector', async () => {
  assert.equal(await sha256Hex(bytes), ABC);
});

test('items are gathered from every stimuli task and nothing else', () => {
  assert.deepEqual(stimulusItems(study()).map((i) => i.stimulus_id), ['a']);
  assert.deepEqual(stimulusItems({ tasks: [{ type: 'calibration' }] }), []);
});

test('a stimulus whose bytes match the study loads', async () => {
  const m = await preloadStimuli(study(), { fetchFn: fakeFetch(bytes), makeUrl: () => 'blob:x' });
  assert.equal(m.get('a').url, 'blob:x');
  assert.equal(m.get('a').bytes, 3);
});

test('a stimulus edited after the study was fixed is refused, by name', async () => {
  await assert.rejects(
    preloadStimuli(study(), { fetchFn: fakeFetch(new TextEncoder().encode('abd')), makeUrl: () => 'x' }),
    /stimulus a: .* does not match the study's sha256/);
});

test('a stimulus that cannot be fetched is refused, not skipped', async () => {
  await assert.rejects(
    preloadStimuli(study(), { fetchFn: fakeFetch(bytes, 404), makeUrl: () => 'x' }),
    /could not be loaded \(HTTP 404\)/);
});

test('fitRect keeps the aspect ratio, centres, and fits in 80% of the stage', () => {
  const r = fitRect(1600, 900, 1000, 1000);
  assert.ok(Math.abs(r.w / r.h - 16 / 9) < 1e-9);
  assert.equal(r.w, 800);
  assert.equal(r.x, 100);
  assert.equal(r.y, (1000 - 450) / 2);
});

test('fitRect never upscales a small stimulus', () => {
  const r = fitRect(200, 100, 1920, 1080);
  assert.deepEqual([r.w, r.h], [200, 100]);
});

test('rectNorm is in stage fractions', () => {
  assert.deepEqual(rectNorm({ x: 100, y: 50, w: 800, h: 450 }, 1000, 1000),
    { x0: 0.1, y0: 0.05, x1: 0.9, y1: 0.5 });
});

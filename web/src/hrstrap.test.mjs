import assert from 'node:assert/strict';
import test from 'node:test';

import { HeartRateStrap, REFERENCE_SOURCE, parseHeartRateMeasurement, rowsForReading } from './hrstrap.js';

const packet = (...bytes) => new DataView(Uint8Array.from(bytes).buffer);

test('a uint8 rate with no extras', () => {
  assert.deepEqual(parseHeartRateMeasurement(packet(0x00, 72)),
    { hr_bpm: 72, contact: null, energy_kj: null, rr_ms: [] });
});

test('a uint16 rate is little-endian', () => {
  assert.equal(parseHeartRateMeasurement(packet(0x01, 0x2c, 0x01)).hr_bpm, 300);
});

test('RR intervals are in 1/1024 s, converted to ms', () => {
  // 0x0400 = 1024 → 1000 ms; 0x0333 = 819 → 799.8 ms
  const r = parseHeartRateMeasurement(packet(0x10, 60, 0x00, 0x04, 0x33, 0x03));
  assert.equal(r.rr_ms.length, 2);
  assert.equal(r.rr_ms[0], 1000);
  assert.ok(Math.abs(r.rr_ms[1] - 799.8) < 0.1);
});

test('energy expended sits between the rate and the RR intervals', () => {
  const r = parseHeartRateMeasurement(packet(0x18, 80, 0x10, 0x00, 0x00, 0x03));
  assert.equal(r.energy_kj, 16);
  assert.deepEqual(r.rr_ms, [750]);
});

test('contact is reported only when the strap supports reporting it', () => {
  assert.equal(parseHeartRateMeasurement(packet(0x06, 70)).contact, true);
  assert.equal(parseHeartRateMeasurement(packet(0x04, 70)).contact, false);
  assert.equal(parseHeartRateMeasurement(packet(0x02, 70)).contact, null);  // bit 1 alone means nothing
});

test('a truncated packet throws rather than inventing a value', () => {
  assert.throws(() => parseHeartRateMeasurement(packet(0x00)));
  assert.throws(() => parseHeartRateMeasurement(packet(0x01, 0x48)));
  assert.throws(() => parseHeartRateMeasurement(packet(0x08, 70, 0x01)));
});

test('an odd trailing byte after RR intervals is ignored, not half-read', () => {
  assert.deepEqual(parseHeartRateMeasurement(packet(0x10, 60, 0x00, 0x04, 0x07)).rr_ms, [1000]);
});

test('without skin contact there is no heart rate row, only the contact row', () => {
  const rows = rowsForReading({ hr_bpm: 0, contact: false, energy_kj: null, rr_ms: [] }, 5);
  assert.deepEqual(rows.map((r) => [r.channel, r.value]), [['reference.contact', 0]]);
  assert.deepEqual(rowsForReading({ hr_bpm: 0, contact: null, energy_kj: null, rr_ms: [] }, 5), []);
});

test('rows are on the master clock and say what they are', () => {
  const rows = rowsForReading({ hr_bpm: 64, contact: true, energy_kj: null, rr_ms: [940] }, 1234.5);
  assert.deepEqual(rows.map((r) => r.channel), ['reference.contact', 'reference.hr_bpm', 'reference.rr_ms']);
  assert.ok(rows.every((r) => r.native_clock_id === 'performance.now' && r.native_ts === 1234.5
    && r.reliability_tier === 'high'));
});

test('the strap hands on chunks under its own source, and flushes the rest on disconnect', async () => {
  const chunks = [];
  let t = 0;
  const strap = new HeartRateStrap({ onChunk: (c) => chunks.push(c), now: () => (t += 1000) });
  for (let k = 0; k < 13; k += 1) strap.receive(packet(0x00, 60 + k));
  assert.equal(chunks.length, 1);
  assert.equal(chunks[0].source, REFERENCE_SOURCE);
  assert.equal(chunks[0].signals.length, 10);
  await strap.disconnect();
  assert.equal(chunks.length, 2);
  assert.equal(chunks[1].signals.length, 3);
  assert.deepEqual(chunks.flatMap((c) => c.signals).map((r) => r.native_ts).slice(0, 3), [1000, 2000, 3000]);
});

/**
 * The smoke test's own assertions, fed doctored bundles. A check that has only
 * ever been seen to pass has not been shown to check anything.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { checkOutput } from './smoke_capture.mjs';

const DRIVEN = { pxPerMm: 3.78, distanceMm: 500 };

function m0Session() {
  const ev = (event_type, extra = {}) => ({ event_type, onset_native_ts: 1, ...extra });
  return {
    study_id: 'm0',
    study: { study_id: 'm0', audience: 'developer' },
    consent: { tier: 'features_only', audience: 'developer' },
    geometry: { ok: true, viewing_distance_mm: 501, px_per_mm: 3.775 },
    events: [
      ev('recording_start', { metadata: { mimeType: 'video/webm;codecs=vp9,opus' } }),
      ev('sync_clapper'), ev('sync_clapper'),
      ...Array.from({ length: 13 }, () => ev('calibration_point')),
      ...Array.from({ length: 5 }, () => ev('validation_point')),
      ev('fixation'), ev('speech_read'), ev('speech_free'),
    ],
  };
}

/** Failures for an m0 bundle after `edit` has doctored its session.json. */
function failuresAfter(edit = () => {}, opts = { chinrest: DRIVEN }) {
  const session = m0Session();
  edit(session);
  const dir = mkdtempSync(join(tmpdir(), 'smoke-check-'));
  try {
    writeFileSync(join(dir, 'session.json'), JSON.stringify(session));
    writeFileSync(join(dir, 'capture.webm'), Buffer.alloc(200_000));
    return checkOutput(dir, 'm0', opts).failures;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const has = (failures, re) => assert.ok(failures.some((f) => re.test(f)), failures.join('; ') || '(no failures)');

test('a correct m0 bundle passes', () => {
  assert.deepEqual(failuresAfter(), []);
});

test('geometry that does not recover the driven distance fails', () => {
  has(failuresAfter((s) => { s.geometry.viewing_distance_mm = 620; }), /viewing distance/);
});

test('a card sized to the wrong density fails', () => {
  has(failuresAfter((s) => { s.geometry.px_per_mm = 5.1; }), /px\/mm/);
});

test('a refused chinrest fails, with its reason', () => {
  has(failuresAfter((s) => { s.geometry = { ok: false, reason: 'edge_saturated' }; }), /edge_saturated/);
});

test('m0 without the chinrest being driven fails', () => {
  has(failuresAfter(() => {}, { chinrest: null }), /without the chinrest/);
});

test('a missing calibration point fails', () => {
  has(failuresAfter((s) => {
    s.events.splice(s.events.findIndex((e) => e.event_type === 'calibration_point'), 1);
  }), /12 calibration points/);
});

test('a session that does not record its audience fails', () => {
  has(failuresAfter((s) => { delete s.study.audience; }), /does not record its audience/);
});

test('a consent record whose audience disagrees with the study fails', () => {
  has(failuresAfter((s) => { s.consent.audience = 'participants'; }), /consent record audience/);
});

test('a recording with no audio codec fails — m0 needs the microphone', () => {
  has(failuresAfter((s) => { s.events[0].metadata.mimeType = 'video/webm;codecs=vp9'; }), /no audio codec/);
});

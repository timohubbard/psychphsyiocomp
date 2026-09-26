import { test } from 'node:test';
import assert from 'node:assert/strict';

import { parseRange } from './static.mjs';

test('no header, or one that is not a byte range, means the whole file', () => {
  assert.equal(parseRange(undefined, 100), null);
  assert.equal(parseRange('items=0-5', 100), null);
  assert.equal(parseRange('bytes=-', 100), null);
});

test('an open-ended range runs to the last byte — what Chrome sends first', () => {
  assert.deepEqual(parseRange('bytes=0-', 100), { start: 0, end: 99 });
  assert.deepEqual(parseRange('bytes=40-', 100), { start: 40, end: 99 });
});

test('a closed range is inclusive and clamped to the file', () => {
  assert.deepEqual(parseRange('bytes=10-19', 100), { start: 10, end: 19 });
  assert.deepEqual(parseRange('bytes=90-500', 100), { start: 90, end: 99 });
});

test('a suffix range is the last N bytes', () => {
  assert.deepEqual(parseRange('bytes=-10', 100), { start: 90, end: 99 });
  assert.deepEqual(parseRange('bytes=-500', 100), { start: 0, end: 99 });
});

test('a range past the end is unsatisfiable, not silently the whole file', () => {
  assert.equal(parseRange('bytes=100-', 100), 'unsatisfiable');
  assert.equal(parseRange('bytes=50-40', 100), 'unsatisfiable');
  assert.equal(parseRange('bytes=-0', 100), 'unsatisfiable');
});

test('a multi-range request falls back to the whole file', () => {
  assert.equal(parseRange('bytes=0-1,5-6', 100), null);
});

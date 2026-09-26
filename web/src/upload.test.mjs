import { test } from 'node:test';
import assert from 'node:assert/strict';

import { uploadAvailable, uploadOrder } from './upload.js';

test('session.json goes first and the recording last', () => {
  const names = uploadOrder([
    { name: 'capture.webm' }, { name: 'identifiers.json' },
    { name: 'browser_chunks.json' }, { name: 'session.json' },
  ]).map((f) => f.name);
  assert.equal(names[0], 'session.json');
  assert.equal(names.at(-1), 'capture.webm');
});

test('uploading is available only when the health check answers', async () => {
  assert.equal(await uploadAvailable(async () => ({ ok: true })), true);
  assert.equal(await uploadAvailable(async () => ({ ok: false })), false);
  assert.equal(await uploadAvailable(async () => { throw new Error('offline'); }), false);
});

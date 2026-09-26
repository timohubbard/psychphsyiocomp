import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  PENDING_PARTICIPANT, assignCondition, completionUrl, isSafeCompletionUrl,
  manifestParticipantId, panelIdentifiers,
} from './recruitment.js';

test('Prolific parameters are read verbatim, and win over pid', () => {
  const ids = panelIdentifiers('?study=x&PROLIFIC_PID=5f3A9&STUDY_ID=st1&SESSION_ID=se1&pid=other');
  assert.deepEqual(ids, { platform: 'prolific', participant: '5f3A9', study: 'st1', session: 'se1' });
});

test('a bare pid is a url-platform identifier; none is null', () => {
  assert.deepEqual(panelIdentifiers('?pid=abc'), { platform: 'url', participant: 'abc', study: null, session: null });
  assert.equal(panelIdentifiers('?study=m0'), null);
});

test('the manifest never carries the raw identifier', () => {
  assert.equal(manifestParticipantId(panelIdentifiers('?PROLIFIC_PID=5f3A9')), PENDING_PARTICIPANT);
  assert.equal(manifestParticipantId(null), 'anonymous');
});

const STUDY = { study_id: 's', version: '1', conditions: { arms: ['A', 'B', 'C'] } };

function memoryStorage() {
  const m = new Map();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, String(v)) };
}

test('an arm is drawn from the seed, and the draw is recorded', () => {
  const c = assignCondition(STUDY, { random: () => [7] });
  assert.deepEqual(c, { arm: 'B', seed: 7, method: 'uniform_random', n_arms: 3, reused: false });
});

test('a reload keeps the same arm', () => {
  const storage = memoryStorage();
  const first = assignCondition(STUDY, { random: () => [4], storage });
  const again = assignCondition(STUDY, { random: () => [5], storage });
  assert.equal(again.arm, first.arm);
  assert.equal(again.reused, true);
});

test('an arm the study no longer has is redrawn, not reused', () => {
  const storage = memoryStorage();
  assignCondition(STUDY, { random: () => [2], storage });                 // C
  const edited = { ...STUDY, conditions: { arms: ['A', 'B'] } };
  const c = assignCondition(edited, { random: () => [1], storage });
  assert.equal(c.arm, 'B');
  assert.equal(c.reused, false);
});

test('a study without conditions assigns none', () => {
  assert.equal(assignCondition({ study_id: 's' }), null);
});

test('completion links must be https (or localhost for testing)', () => {
  assert.equal(isSafeCompletionUrl('https://app.prolific.com/submissions/complete?cc=ABC'), true);
  assert.equal(isSafeCompletionUrl('http://localhost:5173/done'), true);
  assert.equal(isSafeCompletionUrl('http://example.org/?cc=ABC'), false);
  assert.equal(isSafeCompletionUrl('javascript:alert(1)'), false);
  assert.equal(completionUrl({ recruitment: { completion_url: 'http://x.org' } }), null);
});

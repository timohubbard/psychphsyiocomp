import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { buildSequence, estimateDurationMs, wantsChinrest } from '../src/sequence.js';
import { flowModel, flowModels } from './flow.js';

const deps = { buildSequence, estimateDurationMs, wantsChinrest };
const load = (id) => JSON.parse(readFileSync(`studies/${id}.json`, 'utf8'));

test('m0 reads as the protocol a participant gets', () => {
  const f = flowModel(load('m0'), deps);
  assert.deepEqual(f.before.map((b) => b.title), ['Consent', 'Camera and microphone', 'Screen distance check']);
  const titles = f.blocks.map((b) => b.title);
  assert.equal(titles[0], 'Overview');
  assert.equal(titles[1], 'Screen flash');
  assert.ok(titles.includes('13 calibration dots') && titles.includes('5 validation dots'));
  assert.ok(titles.includes('Read a passage aloud'));
  assert.equal(titles.at(-1), 'Screen flash');
  assert.ok(f.totalMs > 3 * 60_000);
});

test('each task block points back at its task in the study', () => {
  const s = load('m0');
  const f = flowModel(s, deps);
  for (const b of f.blocks.filter((x) => x.taskIndex !== null)) {
    assert.ok(s.tasks[b.taskIndex], b.title);
  }
  const cal = f.blocks.find((b) => b.title.includes('calibration'));
  assert.equal(s.tasks[cal.taskIndex].type, 'calibration');
});

test('a stimuli block lists its pictures and videos', () => {
  const f = flowModel(load('stimulus-example'), deps);
  const stim = f.blocks.find((b) => b.kind === 'stimuli');
  assert.equal(stim.n, 3);
  assert.deepEqual(stim.items.map((i) => i.kind).sort(), ['image', 'image', 'video']);
});

test('conditions give one lane per arm, and the lanes differ where the arms do', () => {
  const [a, b] = flowModels(load('panel-example'), deps);
  assert.equal(a.arm, 'A');
  assert.equal(b.arm, 'B');
  assert.deepEqual(a.blocks.find((x) => x.kind === 'stimuli').items.map((i) => i.id), ['scene_left']);
  assert.deepEqual(b.blocks.find((x) => x.kind === 'stimuli').items.map((i) => i.id), ['scene_right']);
  assert.ok(a.after.some((x) => x.title === 'Back to the panel'));
});

test('the in-browser tier says nothing is recorded', () => {
  assert.match(flowModel(load('in-browser-example'), deps).records, /nothing recorded/);
});

test('a questions task is one block, sized by its questions', () => {
  const f = flowModel(load('questions-example'), deps);
  const q = f.blocks.find((b) => b.kind === 'questions');
  assert.equal(q.title, '4 questions');
  assert.equal(q.detail, 'likert, choice, slider, text');
  assert.ok(q.taskIndex === 1);
});
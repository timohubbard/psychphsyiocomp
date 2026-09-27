import { test } from 'node:test';
import assert from 'node:assert/strict';

import { validateStudy } from '../src/study.js';
import {
  TASK_TYPES, blankStudy, getPath, parseList, setPath, stimulusIdFrom, summarise,
} from './builder_model.js';

test('a blank study is valid as it stands', () => {
  assert.deepEqual(validateStudy(blankStudy()).reasons, []);
});

test('every task template is a type the capture page accepts', () => {
  for (const [type, t] of Object.entries(TASK_TYPES)) {
    const s = blankStudy();
    s.modalities = ['gaze', 'face', 'voice'];
    s.calibration = { n_points: 13, randomise_order: true };
    s.tasks = [t.make()];
    if (type === 'stimuli') s.tasks[0].items = [{ stimulus_id: 'a', kind: 'image', src: 'stimuli/a.png', sha256: 'a'.repeat(64), duration_ms: 1000 }];
    assert.deepEqual(validateStudy(s).reasons, [], type);
  }
});

test('setPath creates the way and undefined deletes — an empty optional field is absent', () => {
  const s = {};
  setPath(s, ['disclosure', 'controller'], 'Uni');
  setPath(s, ['tasks', 0, 'type'], 'chinrest');
  assert.deepEqual(s, { disclosure: { controller: 'Uni' }, tasks: [{ type: 'chinrest' }] });
  setPath(s, ['disclosure', 'controller'], undefined);
  assert.ok(!('controller' in s.disclosure));
  setPath(s, ['tasks', 0], undefined);
  assert.deepEqual(s.tasks, []);
  assert.equal(getPath({ a: [{ b: 2 }] }, ['a', 0, 'b']), 2);
  assert.equal(getPath({}, ['a', 'b']), undefined);
});

test('lists and stimulus ids are cleaned up', () => {
  assert.deepEqual(parseList(' A, B ,,C '), ['A', 'B', 'C']);
  assert.equal(stimulusIdFrom('My Forest (1).png'), 'My_Forest_1_');
  assert.equal(stimulusIdFrom('.png'), 'stimulus');
});

test('summarise counts stage types in order', () => {
  assert.deepEqual(summarise([{ type: 'a' }, { type: 'b' }, { type: 'a' }]),
    [{ type: 'a', n: 2 }, { type: 'b', n: 1 }]);
});

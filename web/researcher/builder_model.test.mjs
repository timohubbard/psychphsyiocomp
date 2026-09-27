import { test } from 'node:test';
import assert from 'node:assert/strict';

import { validateStudy } from '../src/study.js';
import {
  QUESTION_TEMPLATES, SECTIONS, TASK_TYPES, blankStudy, fieldOf, getPath, parseList, sectionOf, setPath,
  stimulusIdFrom, uniqueId,
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

// The routing is tested on the capture page's real refusal text, not copies of
// it, so a reworded reason in web/src/study.js shows up here as a failure.
const reasonsOf = (edit) => { const s = blankStudy(); edit(s); return validateStudy(s).reasons; };
const routed = (edit) => reasonsOf(edit).map((r) => [sectionOf(r), fieldOf(r)]);

test('the participant gate lands on the ethics fields', () => {
  const got = routed((s) => { s.audience = 'participants'; });
  assert.ok(got.length >= 5 && got.every(([sec]) => sec === 'told'), JSON.stringify(got));
  const fields = got.map(([, f]) => f);
  for (const f of ['disclosure.irb_reference', 'disclosure.contact', 'disclosure.controller',
    'disclosure.lawful_basis', 'disclosure.special_category_basis']) assert.ok(fields.includes(f), f);
});

test('each part of a broken study is routed to its own section', () => {
  const cases = [
    [(s) => { s.study_id = 'no spaces'; }, 'basics', 'study_id'],
    [(s) => { delete s.name; }, 'basics', 'name'],
    [(s) => { s.modalities = []; }, 'measures', null],
    [(s) => { s.modalities = ['gaze']; s.calibration = { n_points: 3 }; }, 'measures', 'calibration.n_points'],
    [(s) => { s.consent_tiers = ['features_only', 'media_plus_transcript']; }, 'consent', null],
    [(s) => { s.tasks = [{ type: 'stimuli', items: [] }]; }, 'tasks', null],
    [(s) => { s.conditions = { arms: ['A'] }; }, 'conditions', null],
    [(s) => { s.recruitment = { completion_url: 'http://example.com' }; }, 'conditions', 'recruitment.completion_url'],
    [(s) => { s.analysis = { aoi_pad_deg: 40 }; }, 'analysis', 'analysis.aoi_pad_deg'],
    [(s) => { s.analysis = { exclusions: [{ metric: 'x' }] }; }, 'analysis', null],
  ];
  for (const [edit, section, fieldPath] of cases) {
    const got = routed(edit);
    assert.equal(got.length, 1, JSON.stringify(reasonsOf(edit)));
    assert.deepEqual(got[0], [section, fieldPath], reasonsOf(edit)[0]);
  }
});

test('every section a reason can be routed to is one the form draws', () => {
  const ids = new Set(SECTIONS.map((s) => s.id));
  for (const r of ['anything unforeseen', 'unknown audience: x']) assert.ok(ids.has(sectionOf(r)));
  for (const t of Object.values(TASK_TYPES)) assert.ok(t.kind && t.hint, t.label);
});

test('every question template is valid as it stands — text only once the study opts in', () => {
  for (const [kind, make] of Object.entries(QUESTION_TEMPLATES)) {
    const s = blankStudy();
    s.tasks = [{ type: 'questions', id: 'qs', items: [make('q1')] }];
    const reasons = validateStudy(s).reasons;
    if (kind === 'text') {
      assert.match(reasons.join(), /must opt in with disclosure\.free_text/);
      s.disclosure.free_text = true;
      assert.deepEqual(validateStudy(s).reasons, [], kind);
    } else {
      assert.deepEqual(reasons, [], kind);
    }
  }
});

test('a second questions task gets its own id', () => {
  assert.equal(uniqueId('questions', ['questions']), 'questions-2');
  assert.notEqual(TASK_TYPES.questions.make(['questions']).id, 'questions');
});

test('question refusals land under Tasks', () => {
  const s = blankStudy();
  s.tasks = [{ type: 'questions', id: 'qs', items: [{ id: 'x', kind: 'likert', prompt: 'p', points: 99, anchors: ['a', 'b'] }] }];
  const [reason] = validateStudy(s).reasons;
  assert.equal(sectionOf(reason), 'tasks');
});
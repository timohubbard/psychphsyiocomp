/**
 * Tests for study definitions.
 *
 * The behaviour worth pinning here is what the module REFUSES. A study that
 * validates is unremarkable; a study that runs despite missing the retention
 * period, or that changes its protocol without changing its hash, is how a set
 * of sessions quietly stops being comparable.
 */

import assert from 'node:assert/strict';
import test from 'node:test';

import { MAX_RETENTION_DAYS } from './consent.js';
import {
  AUDIO_MODALITIES,
  BROWSER_MODALITIES,
  MODALITIES,
  SPECIAL_CATEGORY_MODALITIES,
  audienceOf,
  canonicalise,
  contentHash,
  disclosureFor,
  needsAudio,
  offeredTiers,
  protocolFor,
  studyProvenance,
  validateStudy,
} from './study.js';

function study(overrides = {}) {
  return {
    study_id: 'reading-2026',
    name: 'Reading study',
    version: '1.0.0',
    disclosure: {
      retention_days: 365,
      secondary_use: 'Analysed by the named team only.',
      contact: 'pi@example.edu',
      irb_reference: 'IRB-2026-0142',
    },
    consent_tiers: ['features_only', 'media_retained'],
    default_tier: 'features_only',
    modalities: ['gaze', 'face'],
    calibration: { n_points: 13, randomise_order: true },
    tasks: [{ type: 'passage', id: 'p1' }],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// what it refuses
// ---------------------------------------------------------------------------

test('a complete study validates', () => {
  const { valid, reasons } = validateStudy(study());
  assert.deepEqual(reasons, []);
  assert.equal(valid, true);
});

test('a missing retention period is a refusal, not a default', () => {
  // 45 CFR 46.116 requires the element to be STATED. Supplying one here would
  // put an unreviewed promise in front of a participant.
  const s = study();
  delete s.disclosure.retention_days;
  const { valid, reasons } = validateStudy(s);
  assert.equal(valid, false);
  assert.ok(reasons.some((r) => r.includes('retention_days')));
});

test('retention beyond the BIPA cap is refused', () => {
  const s = study({ disclosure: { ...study().disclosure,
    retention_days: MAX_RETENTION_DAYS + 1 } });
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('exceeds')));
});

test('a study may promise less retention than the cap', () => {
  const s = study({ disclosure: { ...study().disclosure, retention_days: 30 } });
  assert.equal(validateStudy(s).valid, true);
});

test('no contact route is a missing required element', () => {
  const s = study();
  delete s.disclosure.contact;
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('46.116(b)(7)')));
});

test('an unknown consent tier is refused rather than dropped', () => {
  const s = study({ consent_tiers: ['features_only', 'keep_everything_forever'] });
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('keep_everything_forever')));
});

test('a default tier the study does not offer is refused', () => {
  const s = study({ consent_tiers: ['features_only'], default_tier: 'media_retained' });
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('default_tier')));
});

test('a study that measures nothing is refused', () => {
  assert.ok(validateStudy(study({ modalities: [] })).reasons
    .some((r) => r.includes('measures nothing')));
});

test('an unknown modality is refused', () => {
  assert.ok(validateStudy(study({ modalities: ['gaze', 'telepathy'] })).reasons
    .some((r) => r.includes('telepathy')));
});

test('gaze without enough calibration points is refused', () => {
  // The features would be collected and could never become gaze.
  const s = study({ calibration: { n_points: 3, randomise_order: true } });
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('n_points')));
});

test('gaze with no calibration block at all is refused', () => {
  const s = study();
  delete s.calibration;
  assert.ok(validateStudy(s).reasons.some((r) => r.includes('n_points')));
});

test('a study without gaze does not need calibration', () => {
  const s = study({ modalities: ['voice'] });
  delete s.calibration;
  assert.equal(validateStudy(s).valid, true);
});

test('fixed calibration order is refused with the reason spelled out', () => {
  // LOOCV picked the worst gaze model confidently because fixed order made
  // target position a function of time.
  const s = study({ calibration: { n_points: 13, randomise_order: false } });
  const { reasons } = validateStudy(s);
  assert.ok(reasons.some((r) => r.includes('confounds')));
});

test('nothing at all is refused without throwing', () => {
  assert.equal(validateStudy(undefined).valid, false);
  assert.equal(validateStudy(null).valid, false);
  assert.equal(validateStudy('reading-2026').valid, false);
});

// ---------------------------------------------------------------------------
// the hash
// ---------------------------------------------------------------------------

test('the same study hashes the same', async () => {
  assert.equal(await contentHash(study()), await contentHash(study()));
});

test('key order in the source file does not change the hash', async () => {
  const a = study();
  const b = { modalities: a.modalities, version: a.version, tasks: a.tasks,
    calibration: a.calibration, default_tier: a.default_tier,
    consent_tiers: a.consent_tiers, disclosure: a.disclosure,
    name: a.name, study_id: a.study_id };
  assert.equal(await contentHash(a), await contentHash(b));
});

test('changing the retention promise changes the hash', async () => {
  // Two sessions run under different retention promises were not run under the
  // same study, even if everything measured was identical.
  const other = study({ disclosure: { ...study().disclosure, retention_days: 90 } });
  assert.notEqual(await contentHash(study()), await contentHash(other));
});

test('changing the calibration grid changes the hash', async () => {
  const other = study({ calibration: { n_points: 9, randomise_order: true } });
  assert.notEqual(await contentHash(study()), await contentHash(other));
});

test('adding a modality changes the hash', async () => {
  const other = study({ modalities: ['gaze', 'face', 'respiration'] });
  assert.notEqual(await contentHash(study()), await contentHash(other));
});

test('reordering the modality list does not change the hash', async () => {
  // A list is a set here. Churn on incidental ordering gets a hash ignored.
  const other = study({ modalities: ['face', 'gaze'] });
  assert.equal(await contentHash(study()), await contentHash(other));
});

test('retitling a study does not change the hash', async () => {
  const other = study({ name: 'Reading study (pilot)' });
  assert.equal(await contentHash(study()), await contentHash(other));
});

test('the canonical form carries no prose fields', () => {
  const keys = canonicalise(study()).map(([k]) => k);
  assert.ok(!keys.includes('name'));
  assert.ok(keys.includes('retention_days'));
});

test('provenance carries the hash, not the definition', async () => {
  const p = await studyProvenance(study());
  assert.equal(p.study_id, 'reading-2026');
  assert.equal(p.study_version, '1.0.0');
  assert.equal(p.study_content_hash.length, 16);
  assert.deepEqual(p.modalities, ['face', 'gaze']);
  assert.ok(!('disclosure' in p));
});

// ---------------------------------------------------------------------------
// what it drives
// ---------------------------------------------------------------------------

test('only a voice study asks for the microphone', () => {
  assert.equal(needsAudio(study({ modalities: ['gaze', 'face'] })), false);
  assert.equal(needsAudio(study({ modalities: ['gaze', 'voice'] })), true);
});

test('respiration is a camera modality, not an audio one', () => {
  // It is chest/shoulder motion, not rPPG and not sound (§2.4).
  assert.equal(needsAudio(study({ modalities: ['respiration'] })), false);
  assert.ok(!AUDIO_MODALITIES.includes('respiration'));
});

test('offered tiers come back in the canonical order, not the file order', () => {
  const s = study({ consent_tiers: ['media_retained', 'features_only'] });
  assert.deepEqual(offeredTiers(s).map((t) => t.id),
    ['features_only', 'media_retained']);
});

test('a study offering one tier still offers a real choice object', () => {
  const [tier] = offeredTiers(study({ consent_tiers: ['features_only'] }));
  assert.ok(tier.summary && tier.consequence);
});

test('the disclosure comes from the study, not from a constant', () => {
  const d = disclosureFor(study());
  assert.equal(d.retentionDays, 365);
  assert.equal(d.contact, 'pi@example.edu');
  assert.equal(d.irbReference, 'IRB-2026-0142');
});

test('an invalid study throws rather than yielding a partial disclosure', () => {
  // Every caller is about to put this text in front of a participant.
  const s = study();
  delete s.disclosure.secondary_use;
  assert.throws(() => disclosureFor(s), /not usable/);
});

test('respiration declares its legal standing where it is ticked', () => {
  const resp = MODALITIES.find((m) => m.id === 'respiration');
  assert.match(resp.note, /4\(15\)/);
  assert.match(resp.note, /no breathing rate/i);
});

test('heart rate declares that it is health data, unvalidated and without HRV', () => {
  const c = MODALITIES.find((m) => m.id === 'cardiac');
  assert.match(c.note, /Art\. 9/);
  assert.match(c.note, /unvalidated/i);
  assert.match(c.note, /no HRV/);
  assert.ok(SPECIAL_CATEGORY_MODALITIES.includes('cardiac'));
  assert.ok(!BROWSER_MODALITIES.includes('cardiac'));
  assert.equal(needsAudio(study({ modalities: ['cardiac'] })), false);
});

test('voice declares that no valence channel exists', () => {
  const voice = MODALITIES.find((m) => m.id === 'voice');
  assert.match(voice.note, /valence/i);
});

// ---------------------------------------------------------------------------
// the shipped study, and agreement with the Python mirror
// ---------------------------------------------------------------------------

test('the shipped m0 study validates', async () => {
  const fs = await import('node:fs/promises');
  const s = JSON.parse(await fs.readFile('studies/m0.json', 'utf8'));
  assert.deepEqual(validateStudy(s).reasons, []);
});

test('the shipped m0 study hashes to the value the Python mirror pins', async () => {
  // `server/study.py` validates sessions against the study file on disk, and
  // reports a mismatch as "this study was edited after that session". If the
  // two implementations ever canonicalise differently, every session starts
  // reporting that — a false alarm indistinguishable from a real one. So the
  // hash is pinned on both sides, and drift fails a test instead.
  const fs = await import('node:fs/promises');
  const s = JSON.parse(await fs.readFile('studies/m0.json', 'utf8'));
  assert.equal(await contentHash(s), '5b54b291bc9d74b0');
});

test('the participant fixture hashes to the value the Python mirror pins', async () => {
  // Every field added after m0 is set in this fixture. m0's pin proves the
  // fixed part agrees; this one proves the optional part does too.
  const fs = await import('node:fs/promises');
  const s = JSON.parse(await fs.readFile('server/fixtures/participant-study.json', 'utf8'));
  assert.deepEqual(validateStudy(s).reasons, []);
  assert.equal(await contentHash(s), 'bbf9131e9314dc57');
});

// ---------------------------------------------------------------------------
// who a study may be run on
// ---------------------------------------------------------------------------

function participantStudy(overrides = {}, disclosure = {}) {
  const s = study({ audience: 'participants', ...overrides });
  s.disclosure = {
    ...s.disclosure,
    contact: 'a.researcher@uni.ac.uk',
    irb_reference: 'REC-2026-0417',
    controller: 'University of Somewhere',
    lawful_basis: 'UK GDPR Art 6(1)(e)',
    special_category_basis: 'UK GDPR Art 9(2)(j)',
    ...disclosure,
  };
  return s;
}

test('a complete participant study validates', () => {
  assert.deepEqual(validateStudy(participantStudy()).reasons, []);
});

test('a study with no audience is a developer self-test, and is still valid', () => {
  // m0 and the other shipped studies: runnable on the developer, flagged as such.
  assert.equal(audienceOf(study()), 'developer');
  assert.deepEqual(validateStudy(study()).reasons, []);
});

test('an unknown audience is refused', () => {
  assert.match(validateStudy(study({ audience: 'everyone' })).reasons.join(), /unknown audience/);
});

test('participants without an ethics reference are refused', () => {
  const s = participantStudy({}, { irb_reference: null });
  assert.match(validateStudy(s).reasons.join(), /irb_reference/);
});

test('the shipped placeholder contact is refused for participants', () => {
  // m0's contact line, verbatim in spirit: non-empty, so the old check passed it.
  const s = participantStudy({}, {
    contact: 'Replace this with the investigator and the route to the ethics board.',
  });
  assert.match(validateStudy(s).reasons.join(), /placeholder/);
});

test('a contact with no email or web address is refused for participants', () => {
  assert.match(validateStudy(participantStudy({}, { contact: 'the PI' })).reasons.join(),
    /no email address/);
});

test('an example.org address is a template, not a contact', () => {
  assert.match(validateStudy(participantStudy({}, { contact: 'pi@example.org' })).reasons.join(),
    /placeholder/);
});

test('participants need the controller and the Art 6 basis', () => {
  const r = validateStudy(participantStudy({}, { controller: null, lawful_basis: null })).reasons.join();
  assert.match(r, /controller/);
  assert.match(r, /lawful_basis/);
});

test('face, voice or respiration need an Art 9 condition; gaze alone does not', () => {
  assert.match(validateStudy(participantStudy({}, { special_category_basis: null })).reasons.join(),
    /face recorded but no disclosure.special_category_basis/);
  const gazeOnly = participantStudy({ modalities: ['gaze'] }, { special_category_basis: null });
  assert.deepEqual(validateStudy(gazeOnly).reasons, []);
});

test('present-but-empty disclosure fields are refused whoever the audience', () => {
  const s = study();
  s.disclosure.controller = '  ';
  assert.match(validateStudy(s).reasons.join(), /controller is present but empty/);
});

test('fields added after m0 are hashed only when set, so older hashes hold', () => {
  const keys = canonicalise(study()).map(([k]) => k);
  assert.equal(keys.length, 11);
  assert.ok(!keys.includes('audience'));
  const full = canonicalise(participantStudy()).map(([k]) => k);
  assert.deepEqual(full.slice(11),
    ['audience', 'controller', 'lawful_basis', 'special_category_basis']);
});

test('changing the audience changes the hash', async () => {
  assert.notEqual(await contentHash(study()), await contentHash(study({ audience: 'participants' })));
});

const item = (over = {}) => ({
  stimulus_id: 'forest', kind: 'image', src: 'stimuli/forest.png',
  sha256: 'a'.repeat(64), duration_ms: 4000, ...over,
});
const withStimuli = (items, extra = {}) => study({ tasks: [{ type: 'stimuli', items, ...extra }] });

test('a well-formed stimuli task validates', () => {
  assert.deepEqual(validateStudy(withStimuli([item(), item({ stimulus_id: 'sea', kind: 'video',
    src: 'stimuli/sea.webm' })])).reasons, []);
});

test('stimulus refusals: empty, duplicate id, bad kind, path, hash, duration, sound', () => {
  const r = (s) => validateStudy(s).reasons.join(' | ');
  assert.match(r(withStimuli([])), /no items/);
  assert.match(r(withStimuli([item(), item()])), /forest is used twice/);
  assert.match(r(withStimuli([item({ kind: 'audio' })])), /kind must be image or video/);
  assert.match(r(withStimuli([item({ src: '../out/x.png' })])), /path under stimuli/);
  assert.match(r(withStimuli([item({ src: 'stimuli/../../x.png' })])), /path under stimuli/);
  assert.match(r(withStimuli([item({ src: '/etc/passwd' })])), /path under stimuli/);
  assert.match(r(withStimuli([item({ sha256: 'ABC' })])), /sha256 must be 64/);
  assert.match(r(withStimuli([item({ duration_ms: 0 })])), /duration_ms must be between/);
  assert.match(r(withStimuli([item({ sound: 'yes' })])), /sound must be true or false/);
  assert.match(r(withStimuli([item()], { randomise: 'no' })), /randomise must be true or false/);
});

test('conditions: at least two unique slug arms; tasks may name a subset', () => {
  const r = (s) => validateStudy(s).reasons.join(' | ');
  const ok = study({ conditions: { arms: ['A', 'B'] }, tasks: [{ type: 'calibration', arms: ['A'] }] });
  assert.deepEqual(validateStudy(ok).reasons, []);
  assert.match(r(study({ conditions: { arms: ['A'] } })), /at least two arms/);
  assert.match(r(study({ conditions: { arms: ['A', 'A'] } })), /repeats an arm/);
  assert.match(r(study({ tasks: [{ type: 'calibration', arms: ['A'] }] })), /defines no conditions/);
  assert.match(r(study({ conditions: { arms: ['A', 'B'] }, tasks: [{ type: 'calibration', arms: ['C'] }] })),
    /non-empty subset/);
});

test('conditions are part of the protocol hash; the completion link is not', async () => {
  const base = study({ conditions: { arms: ['A', 'B'] } });
  assert.notEqual(await contentHash(base), await contentHash(study({ conditions: { arms: ['A', 'C'] } })));
  assert.equal(await contentHash(base), await contentHash({
    ...base, recruitment: { completion_url: 'https://app.prolific.com/submissions/complete?cc=X' } }));
});

test('an unsafe completion link is refused', () => {
  assert.match(validateStudy(study({ recruitment: { completion_url: 'http://example.org/?cc=X' } }))
    .reasons.join(), /https address/);
});

test('analysis refusals mirror server/study.py', () => {
  const r = (a) => validateStudy(study({ analysis: a })).reasons.join(' | ');
  assert.match(r({ exclusions: [{ min: 1 }] }), /needs a metric/);
  assert.match(r({ exclusions: [{ metric: 'x' }] }), /needs a min or a max/);
  assert.match(r({ exclusions: [{ metric: 'x', min: 2, max: 1 }] }), /min is above max/);
  const base = { name: 'e', event_type: 'stimulus', channels: ['c'], pre_ms: 200, post_ms: 500 };
  assert.match(r({ epochs: [base, base] }), /unique slug name/);
  assert.match(r({ epochs: [{ ...base, channels: [] }] }), /list of channels/);
  assert.match(r({ epochs: [{ ...base, baseline_ms: [-500, 0] }] }), /inside the window/);
  assert.match(r({ epochs: [{ ...base, resample_hz: 0 }] }), /resample_hz/);
  assert.equal(r({ exclusions: [{ metric: 'achieved_fps', min: 5 }], epochs: [base] }), '');
});

const Q = (items, over = {}) => study({
  tasks: [{ type: 'questions', id: 'qs', items }], ...over });
const likert = { id: 'l', kind: 'likert', prompt: 'How?', points: 7, anchors: ['low', 'high'] };

test('questions validate, and free text needs the study to opt in', () => {
  const choice = { id: 'c', kind: 'choice', prompt: 'Which?', options: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }] };
  const slider = { id: 's', kind: 'slider', prompt: 'How much?', min: 0, max: 100, anchors: ['none', 'lots'], allow_skip: true };
  assert.deepEqual(validateStudy(Q([likert, choice, slider])).reasons, []);
  const text = { id: 't', kind: 'text', prompt: 'Anything?' };
  assert.match(validateStudy(Q([text])).reasons.join(), /must opt in with disclosure\.free_text: true/);
  const optedIn = Q([text]);
  optedIn.disclosure.free_text = true;
  assert.deepEqual(validateStudy(optedIn).reasons, []);
});

test('question refusals mirror server/study.py', () => {
  const r = (items, over) => validateStudy(Q(items, over)).reasons.join(' | ');
  assert.match(r([{ ...likert, anchor: ['x'] }]), /unknown keys for a likert item: anchor/);
  assert.match(r([{ ...likert, points: 12 }]), /points must be a whole number from 2 to 11/);
  assert.match(r([{ ...likert, anchors: ['only one'] }]), /anchors must be two labels/);
  assert.match(r([likert, likert]), /item 2 needs a unique slug id/);
  assert.match(r([{ ...likert, kind: 'essay' }]), /kind must be likert, choice, slider or text/);
  assert.match(r([{ id: 'c', kind: 'choice', prompt: 'x', options: [{ id: 'a', label: 'A' }] }]), /options must be 2 to 12/);
  assert.match(r([{ id: 's', kind: 'slider', prompt: 'x', min: 5, max: 5, anchors: ['a', 'b'] }]), /min < max/);
  assert.match(r([]), /needs 1 to 50 items/);
  assert.match(r([{ ...likert, prompt: '' }]), /prompt must be 1 to 500 characters/);
  const withFlag = Q([likert]);
  withFlag.disclosure.free_text = true;
  assert.match(validateStudy(withFlag).reasons.join(), /free_text is true but no question asks for typed text/);
  const badFlag = Q([likert]);
  badFlag.disclosure.free_text = 'yes';
  assert.match(validateStudy(badFlag).reasons.join(), /free_text must be true or false/);
});

test('adding questions changes only the studies that have them; free_text is hashed when present', async () => {
  const s = Q([likert]);
  assert.notEqual(await contentHash(s), await contentHash(study()));
  const t = Q([{ id: 't', kind: 'text', prompt: 'x' }]);
  t.disclosure.free_text = true;
  const noFlag = structuredClone(t);
  delete noFlag.disclosure.free_text;
  assert.notEqual(await contentHash(t), await contentHash(noFlag));
});

const withContrast = (over = {}) => {
  const epochs = [{ name: 'e', event_type: 'stimulus', channels: ['c'], pre_ms: 500, post_ms: 2000 }];
  const c = { name: 'k', epochs: 'e', channel: 'c', arms: ['A', 'B'], window_ms: [200, 1000],
    n_permutations: 5000, seed: 1, cluster: { p_threshold: 0.05 }, ...over };
  return study({ conditions: { arms: ['A', 'B'] }, analysis: { epochs, contrasts: [c] } });
};

test('a declared contrast validates and leaves the protocol hash alone', async () => {
  assert.deepEqual(validateStudy(withContrast()).reasons, []);
  assert.equal(await contentHash(withContrast()), await contentHash(study({ conditions: { arms: ['A', 'B'] } })));
});

test('contrast refusals mirror server/study.py', () => {
  const r = (over) => validateStudy(withContrast(over)).reasons.join(' | ');
  assert.match(r({ windows_ms: [0, 1] }), /unknown keys: windows_ms/);
  assert.match(r({ epochs: 'nope' }), /epoch set in analysis\.epochs/);
  assert.match(r({ channel: 'x' }), /one of that epoch set's channels/);
  assert.match(r({ arms: ['A', 'A'] }), /two different arms/);
  assert.match(r({ arms: ['A', 'C'] }), /two different arms/);
  assert.match(r({ window_ms: [-900, 100] }), /inside the epoch/);
  assert.match(r({ n_permutations: 10 }), /from 1000 to 100000/);
  assert.match(r({ seed: true }), /seed must be a whole number/);
  assert.doesNotMatch(r({ seed: 3.0 }), /seed must be a whole number/);
  assert.match(r({ tail: 'both' }), /tail must be/);
  assert.match(r({ cluster: { p_threshold: 2 } }), /p_threshold/);
  assert.match(r({ cluster: { tail: 'two' } }), /cluster has unknown keys: tail/);
  assert.match(validateStudy(study({ analysis: withContrast().analysis })).reasons.join(), /defines no conditions/);
  assert.match(validateStudy(study({ analysis: { contrasts: null } })).reasons.join(), /must be a list/);
});

test('the shipped stimulus example validates', async () => {
  const fs = await import('node:fs/promises');
  const s = JSON.parse(await fs.readFile('studies/stimulus-example.json', 'utf8'));
  assert.deepEqual(validateStudy(s).reasons, []);
});

test('the in-browser tier may be offered for gaze and face', () => {
  const s = study({ consent_tiers: ['features_in_browser', 'features_only'],
    default_tier: 'features_in_browser', modalities: ['gaze', 'face'] });
  assert.deepEqual(validateStudy(s).reasons, []);
});

test('the in-browser tier is refused for modalities only a server can measure', () => {
  // The participant would consent to a measurement that then never happens.
  for (const m of ['voice', 'respiration', 'cardiac']) {
    const s = study({ consent_tiers: ['features_in_browser'], default_tier: 'features_in_browser',
      modalities: ['gaze', m] });
    assert.match(validateStudy(s).reasons.join(), new RegExp(`${m} can only be measured`));
  }
});

test('the consent flow is told what each enabled modality measures, in canonical order', () => {
  const p = protocolFor(study({ modalities: ['face', 'gaze'], tasks: [] }));
  assert.deepEqual(p.activity.measures,
    ['where on the screen you look', 'how the muscles of your face move']);
  assert.ok(MODALITIES.every((m) => typeof m.measures === 'string' && m.measures));
});

test('provenance and disclosure carry the audience', async () => {
  assert.equal((await studyProvenance(study())).audience, 'developer');
  assert.equal(disclosureFor(participantStudy()).audience, 'participants');
  assert.equal(disclosureFor(participantStudy()).controller, 'University of Somewhere');
});

test('non-ASCII disclosure text is not escaped before hashing', async () => {
  // Disclosures are prose, so a curly apostrophe is a matter of time.
  // JSON.stringify leaves it as a character; Python escapes it unless told not
  // to, and the two would then disagree.
  const s = study({ disclosure: { ...study().disclosure,
    secondary_use: 'We don’t sell your data — ever.' } });
  const payload = JSON.stringify(canonicalise(s));
  assert.ok(!payload.includes('\\u'));
  assert.equal((await contentHash(s)).length, 16);
});

// ---------------------------------------------------------------------------
// choosing a study: never by default
// ---------------------------------------------------------------------------

test('a URL without ?study= chooses nothing, rather than m0', async () => {
  // It used to default to m0, and a session meant for au-expressions recorded
  // the whole gaze pilot before anyone could tell.
  const { studyIdFromUrl } = await import('./study.js');
  assert.equal(studyIdFromUrl(''), null);
  assert.equal(studyIdFromUrl('?pid=p1'), null);
  assert.equal(studyIdFromUrl('?study='), null);
  assert.equal(studyIdFromUrl('?study=au-expressions'), 'au-expressions');
});

test('the study index lists exactly the study files that exist', async () => {
  const fs = await import('node:fs/promises');
  const files = (await fs.readdir('studies'))
    .filter((f) => f.endsWith('.json') && f !== 'index.json')
    .map((f) => f.replace(/\.json$/, '')).sort();
  const index = JSON.parse(await fs.readFile('studies/index.json', 'utf8'));
  assert.deepEqual([...index.studies].sort(), files);
});

test('every indexed study validates, so the chooser never offers a dead end', async () => {
  const fs = await import('node:fs/promises');
  const { validateStudy } = await import('./study.js');
  const index = JSON.parse(await fs.readFile('studies/index.json', 'utf8'));
  for (const id of index.studies) {
    const s = JSON.parse(await fs.readFile(`studies/${id}.json`, 'utf8'));
    assert.equal(s.study_id, id);
    assert.equal(validateStudy(s).valid, true, id);
  }
});

test('the protocol line names the study, its version and what it will do', async () => {
  const fs = await import('node:fs/promises');
  const { describeStudy } = await import('./study.js');
  const s = JSON.parse(await fs.readFile('studies/au-expressions.json', 'utf8'));
  const line = describeStudy(s);
  assert.match(line, /au-expressions v1\.0\.0/);
  assert.match(line, /expression_prompts/);
  assert.doesNotMatch(describeStudy(JSON.parse(
    await fs.readFile('studies/m0.json', 'utf8'))), /chinrest/);
});

test('the consent text describes the protocol being consented to', async () => {
  // It was a literal about dots and a read-aloud passage, true of m0 only. The
  // face-only expression study uses no microphone and shows no dots.
  const fs = await import('node:fs/promises');
  const { protocolFor } = await import('./study.js');
  const load = async (id) => JSON.parse(await fs.readFile(`studies/${id}.json`, 'utf8'));

  const expr = protocolFor(await load('au-expressions')).activity;
  assert.equal(expr.devices, 'camera');
  assert.match(expr.records, /no audio/);
  assert.deepEqual(expr.doing,
    ['rest your eyes on a cross', 'make some facial movements when asked']);

  const m0 = protocolFor(await load('m0')).activity;
  assert.equal(m0.devices, 'camera and microphone');
  assert.ok(m0.doing.includes('follow a dot around the screen with your eyes'));
  assert.ok(m0.doing.includes('read a short passage aloud'));
  assert.ok(m0.doing[0].includes('bank card'), 'the chinrest is disclosed first');
});

test('joinAnd reads as a sentence', async () => {
  const { joinAnd } = await import('./consent.js');
  assert.equal(joinAnd(['a']), 'a');
  assert.equal(joinAnd(['a', 'b']), 'a and b');
  assert.equal(joinAnd(['a', 'b', 'c']), 'a, b and c');
});

test('a transcript tier needs a microphone (mirrors server/study.py)', async () => {
  const { validateStudy } = await import('./study.js');
  const fs = await import('node:fs/promises');
  const s = JSON.parse(await fs.readFile('studies/au-expressions.json', 'utf8'));
  s.consent_tiers = ['media_retained', 'media_plus_transcript'];
  const v = validateStudy(s);
  assert.equal(v.valid, false);
  assert.ok(v.reasons.some((r) => r.includes('no modality records audio')));
});

test('a study without audio is not told its audio is kept', async () => {
  const fs = await import('node:fs/promises');
  const { protocolFor } = await import('./study.js');
  const { consentRecord } = await import('./consent.js');
  const s = JSON.parse(await fs.readFile('studies/au-expressions.json', 'utf8'));
  const [tier] = protocolFor(s).tiers;
  assert.doesNotMatch(tier.summary + tier.keeps.join(' '), /audio are|video and audio|voice is itself/);
  assert.match(tier.summary, /No audio is recorded/);
  // The record stores what was shown, not the canonical audio wording.
  const rec = consentRecord({ tier: 'media_retained', retentionDays: 30, secondaryUse: 'x',
    contact: 'y', studyId: s.study_id, audio: false });
  assert.deepEqual(rec.disclosed.keeps, tier.keeps);
  // And a study with audio still says so.
  const m0 = JSON.parse(await fs.readFile('studies/m0.json', 'utf8'));
  const kept = protocolFor(m0).tiers.find((t) => t.id === 'media_retained');
  assert.match(kept.summary, /video and audio/);
});

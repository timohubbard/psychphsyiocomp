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
  MODALITIES,
  canonicalise,
  contentHash,
  disclosureFor,
  needsAudio,
  offeredTiers,
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

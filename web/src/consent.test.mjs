import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  CONSENT_TIERS,
  DEFAULT_TIER,
  MAX_RETENTION_DAYS,
  allowsTranscript,
  analysisNotice,
  consentRecord,
  retainsMedia,
  validateConsent,
  withdrawalText,
} from './consent.js';

const VALID = {
  tier: 'features_only',
  understood: true,
  retentionDays: 365,
  secondaryUse: 'Analysis by the named research team only; no sharing.',
};

// ---------------------------------------------------------------------------
// the tiers are separate decisions
// ---------------------------------------------------------------------------

test('the default tier keeps no recording', () => {
  // §6.5: raw video processed and discarded within the session by default,
  // with retention as an explicit separately-consented opt-in.
  assert.equal(DEFAULT_TIER, 'features_only');
  assert.equal(retainsMedia(DEFAULT_TIER), false);
});

test('each tier adds exactly one capability', () => {
  assert.equal(retainsMedia('features_only'), false);
  assert.equal(retainsMedia('media_retained'), true);
  assert.equal(retainsMedia('media_plus_transcript'), true);

  assert.equal(allowsTranscript('media_retained'), false);
  assert.equal(allowsTranscript('media_plus_transcript'), true);
});

test('an unknown tier grants nothing', () => {
  // Failing open here would turn a typo into a retention decision.
  assert.equal(retainsMedia('everything'), false);
  assert.equal(allowsTranscript(undefined), false);
});

test('no tier describes the data as anonymised', () => {
  /* §6.4: face video resists simple de-identification — blurring leaves gait,
     body and voice cues — and voice is itself a biometric identifier that
     pitch-shifting does not reliably defeat. The honest default is that raw
     face and voice recordings are identifiable data, and the participant-facing
     text has to say so rather than imply otherwise. */
  const prose = JSON.stringify(CONSENT_TIERS).toLowerCase();
  for (const word of ['anonymis', 'anonymiz', 'de-identif', 'deidentif']) {
    assert.ok(!prose.includes(word), `consent copy claims ${word}`);
  }
});

test('the retaining tier says plainly that the data is identifiable', () => {
  const tier = CONSENT_TIERS.find((t) => t.id === 'media_retained');
  const text = [...tier.keeps, tier.summary].join(' ').toLowerCase();
  assert.ok(text.includes('identifiable'));
});

test('every tier states what is kept and what it costs', () => {
  for (const t of CONSENT_TIERS) {
    assert.ok(t.keeps.length >= 2, `${t.id} does not say what is kept`);
    assert.ok(t.consequence, `${t.id} does not say what choosing it means`);
  }
});

// ---------------------------------------------------------------------------
// validation refuses rather than defaulting
// ---------------------------------------------------------------------------

test('a complete record validates', () => {
  assert.equal(validateConsent(VALID).valid, true);
});

test('a missing record is refused, not defaulted to the safest tier', () => {
  // Silently assuming the most restrictive tier is still assuming, and leaves
  // a session with no defensible basis for having run at all.
  for (const bad of [null, undefined, 'features_only', 42]) {
    assert.equal(validateConsent(bad).valid, false);
  }
});

test('an unacknowledged disclosure is refused', () => {
  const r = validateConsent({ ...VALID, understood: false });
  assert.equal(r.valid, false);
  assert.ok(r.reasons.some((x) => x.includes('acknowledged')));
});

test('a missing retention period is refused', () => {
  // 45 CFR 46.116 requires informed-consent elements to address retention
  // EXPLICITLY for video/audio/biometric capture. Omitting it is a missing
  // required element, not a thin flow.
  const r = validateConsent({ ...VALID, retentionDays: undefined });
  assert.equal(r.valid, false);
  assert.ok(r.reasons.some((x) => x.includes('retention')));
});

test('retention beyond the cap is refused', () => {
  /* §6.4 found no published reconciliation of BIPA's three-year outer bound
     with GDPR's "no longer than necessary". The synthesis: take the shorter of
     the research need and three years. Three years is the hard cap. */
  assert.equal(MAX_RETENTION_DAYS, 1095);
  const r = validateConsent({ ...VALID, retentionDays: MAX_RETENTION_DAYS + 1 });
  assert.equal(r.valid, false);
  assert.ok(r.reasons.some((x) => x.includes('cap')));
});

test('a missing secondary-use disclosure is refused', () => {
  const r = validateConsent({ ...VALID, secondaryUse: '   ' });
  assert.equal(r.valid, false);
  assert.ok(r.reasons.some((x) => x.includes('secondary-use')));
});

test('every failure is named, not just the first', () => {
  // A participant-facing flow can only fix what it is told about.
  const r = validateConsent({ tier: 'nope', understood: false });
  assert.equal(r.valid, false);
  assert.ok(r.reasons.length >= 3, r.reasons);
});

// ---------------------------------------------------------------------------
// the record is auditable
// ---------------------------------------------------------------------------

test('the record stores what was disclosed, not only what was agreed', () => {
  // "They consented to media retention" is not answerable later without
  // knowing what they were told retention meant.
  const rec = consentRecord({
    tier: 'media_retained', retentionDays: 180,
    secondaryUse: 'none', studyId: 'm0',
  });
  assert.equal(rec.tier, 'media_retained');
  assert.ok(rec.disclosed.keeps.length >= 2);
  assert.ok(rec.disclosed.consequence);
});

test('the record is timestamped and names the basis it was built against', () => {
  const rec = consentRecord({
    tier: 'features_only', retentionDays: 30, secondaryUse: 'none',
  });
  assert.ok(Date.parse(rec.agreed_utc) > 0);
  assert.ok(rec.basis.includes('46.116'));
});

test('the automated-analysis notice names what is measured and what is not done', () => {
  const n = analysisNotice(['where on the screen you look', 'how the muscles of your face move']);
  assert.match(n, /automatically/);
  assert.match(n, /where on the screen you look and how the muscles of your face move/);
  // The three things a participant is most likely to assume.
  assert.match(n, /does not identify who you are/);
  assert.match(n, /does not label your emotions/);
  assert.match(n, /nothing is decided about you/);
});

test('a study that measures nothing gets no analysis notice rather than an empty one', () => {
  assert.equal(analysisNotice([]), '');
});

test('the withdrawal text states the period, the scope, the exception and the complaint route', () => {
  const w = withdrawalText(180);
  assert.match(w, /within the 180 days/);
  assert.match(w, /session code/);
  assert.match(w, /every measurement taken from it/);
  assert.match(w, /published summary that does not identify anyone/);
  assert.match(w, /Information Commissioner/);
});

test('measurements only says the measurements are still personal data', () => {
  const t = CONSENT_TIERS.find((x) => x.id === 'features_only');
  assert.ok(t.keeps.some((k) => /still personal data/.test(k) && /help identify you/.test(k)));
});

test('the record stores the notice and the withdrawal text exactly as shown', () => {
  const rec = consentRecord({
    tier: 'features_only', retentionDays: 30, secondaryUse: 'none',
    analysis: 'A', withdrawal: 'B',
  });
  assert.equal(rec.analysis_notice, 'A');
  assert.equal(rec.withdrawal, 'B');
  assert.match(rec.basis, /Art 50\(3\)/);
  assert.match(rec.basis, /UK GDPR Art 13/);
});

test('a record built from the tiers validates', () => {
  const rec = consentRecord({
    tier: 'media_plus_transcript', retentionDays: 90,
    secondaryUse: 'Shared with collaborators under agreement.',
  });
  assert.equal(validateConsent(rec).valid, true);
});

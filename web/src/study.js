/**
 * Study definitions.
 *
 * A study is the protocol: what the participant was told, what they were asked
 * to do, and which measurements were taken. None of those are properties of
 * this software, and until now two of them were hard-coded in it —
 * `STUDY_DISCLOSURE` stated a retention period on every study's behalf, and the
 * stimulus sequence was whatever `buildM0Sequence` happened to produce.
 *
 * Three things this module insists on, each for a reason the project has
 * already paid for elsewhere:
 *
 * **Content-hashed, like AOI sets.** §4.2 found the same fixations yielded
 * 77%, 88% and 93% dwell depending on AOI boundaries, which is why AOI versions
 * are immutable and hashed. A protocol has the same property and more force: a
 * different calibration grid, a different passage, a different tier on offer,
 * and the sessions are not comparable. `contentHash` is derived from the
 * definition, so editing a field changes it whether or not anyone remembers to
 * bump `version`.
 *
 * **Validated, never defaulted.** A study missing a retention period is not a
 * study with a sensible default retention period — 45 CFR 46.116 requires the
 * element to be *stated*, and inventing one here would put words in a
 * researcher's mouth and an unreviewed promise in front of a participant.
 *
 * **Modalities are opt-in and enumerated.** Respiration in particular is
 * plausibly health data under GDPR Art. 4(15) (§6.3), so a study runs it
 * because it said so, never because the engine was installed.
 */

import { CONSENT_TIERS, MAX_RETENTION_DAYS, tierCopy } from './consent.js';
import { activitiesFor } from './sequence.js';

/** Every modality this platform can collect, and what it costs to say yes. */
export const MODALITIES = [
  {
    id: 'gaze',
    label: 'Screen-based eye tracking',
    needs: ['camera'],
    note: 'Requires the chinrest step and a calibration grid.',
  },
  {
    id: 'face',
    label: 'Facial expression (Action Units)',
    needs: ['camera'],
    note: 'Action Units only. No emotion labels are produced.',
  },
  {
    id: 'voice',
    label: 'Voice acoustics',
    needs: ['microphone'],
    note: 'eGeMAPS acoustic features. No valence channel exists (§2.3).',
  },
  {
    id: 'respiration',
    label: 'Respiration waveform',
    needs: ['camera'],
    // Spelled out here rather than in a doc, because this is the field a
    // researcher ticks and the consequence should be attached to the tick.
    note: 'Waveform only — no breathing rate (§2.4). Plausibly health data '
      + 'under GDPR Art. 4(15), so it carries higher legal risk than the '
      + 'others (§6.3).',
  },
];

export const MODALITY_IDS = MODALITIES.map((m) => m.id);

/** Modalities that cannot be collected without asking for the microphone. */
export const AUDIO_MODALITIES = MODALITIES
  .filter((m) => m.needs.includes('microphone')).map((m) => m.id);

/**
 * Validate a study definition.
 *
 * Returns `{ valid, reasons }` and never repairs. A study that does not
 * validate does not run: a session collected under a protocol nobody could
 * describe afterwards is not salvageable by guessing what was meant.
 */
export function validateStudy(study) {
  const reasons = [];

  if (!study || typeof study !== 'object') {
    return { valid: false, reasons: ['no study definition'] };
  }

  if (!isId(study.study_id)) {
    reasons.push('study_id must be a slug of letters, digits, dash or underscore');
  }
  if (!nonEmpty(study.name)) reasons.push('no study name');
  if (!nonEmpty(study.version)) reasons.push('no study version');

  // --- what the participant is told ---------------------------------------
  const d = study.disclosure;
  if (!d || typeof d !== 'object') {
    reasons.push('no disclosure block');
  } else {
    if (!Number.isFinite(d.retention_days) || d.retention_days <= 0) {
      reasons.push('disclosure.retention_days must be a positive number of days');
    } else if (d.retention_days > MAX_RETENTION_DAYS) {
      // BIPA's 3-year outer bound. A study may promise less; it may not promise
      // more through this software.
      reasons.push(
        `disclosure.retention_days ${d.retention_days} exceeds the `
        + `${MAX_RETENTION_DAYS}-day cap`);
    }
    if (!nonEmpty(d.secondary_use)) reasons.push('no disclosure.secondary_use');
    if (!nonEmpty(d.contact)) {
      // 45 CFR 46.116(b)(7): whom to contact about the research and about a
      // participant's rights. A consent form with no route back to a human is
      // missing a required element, not merely unfriendly.
      reasons.push('no disclosure.contact — required by 45 CFR 46.116(b)(7)');
    }
    if (d.irb_reference !== undefined && d.irb_reference !== null
        && !nonEmpty(d.irb_reference)) {
      reasons.push('disclosure.irb_reference is present but empty');
    }
  }

  // --- what is offered ----------------------------------------------------
  const tiers = study.consent_tiers;
  if (!Array.isArray(tiers) || tiers.length === 0) {
    reasons.push('no consent_tiers offered');
  } else {
    const known = new Set(CONSENT_TIERS.map((t) => t.id));
    for (const t of tiers) {
      if (!known.has(t)) reasons.push(`unknown consent tier: ${t}`);
    }
    if (study.default_tier !== undefined && study.default_tier !== null
        && !tiers.includes(study.default_tier)) {
      reasons.push('default_tier is not among the tiers offered');
    }
  }

  // --- what is measured ---------------------------------------------------
  const mods = study.modalities;
  if (!Array.isArray(mods) || mods.length === 0) {
    reasons.push('no modalities enabled — a study that measures nothing');
  } else {
    for (const m of mods) {
      if (!MODALITY_IDS.includes(m)) reasons.push(`unknown modality: ${m}`);
    }
  }

  // Gaze is the one modality with a hard prerequisite the protocol itself must
  // satisfy: without calibration targets there is nothing to fit an estimator
  // on, and the session would produce features that can never become gaze.
  if (Array.isArray(mods) && mods.includes('gaze')) {
    const n = study.calibration?.n_points;
    if (!Number.isInteger(n) || n < 5) {
      reasons.push('gaze needs calibration.n_points of at least 5');
    }
    if (study.calibration && study.calibration.randomise_order === false) {
      // Fixed order made target position a function of time, and LOOCV then
      // scored the worst model best because a held-out point's temporal
      // neighbours stayed in training. Allowed, but it has to be a decision.
      reasons.push(
        'calibration.randomise_order is false — fixed stimulus order '
        + 'confounds target position with time and breaks cross-validation');
    }
  }

  if (study.tasks !== undefined && !Array.isArray(study.tasks)) {
    reasons.push('tasks must be a list when present');
  }

  // A transcript tier with no microphone offers the participant a choice that
  // cannot happen, and records a consent to transcription for a session with
  // no audio. Mirrored in server/study.py.
  if (Array.isArray(tiers) && tiers.includes('media_plus_transcript')
      && Array.isArray(mods) && !mods.some((m) => AUDIO_MODALITIES.includes(m))) {
    reasons.push('media_plus_transcript is offered but no modality records audio');
  }

  return { valid: reasons.length === 0, reasons };
}

/**
 * A stable digest of everything that makes two sessions comparable.
 *
 * Deliberately excludes `name` and any `notes`: retitling a study does not
 * change what was measured, and a hash that churns on prose gets ignored.
 * Deliberately includes the disclosure, because what a participant was told is
 * part of the protocol — two sessions run under different retention promises
 * were not run under the same study.
 */
export async function contentHash(study) {
  const payload = JSON.stringify(canonicalise(study));
  const bytes = new TextEncoder().encode(payload);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, '0')).join('').slice(0, 16);
}

/** The hashed subset, sorted so key order in the source file cannot matter. */
export function canonicalise(study) {
  const d = study.disclosure ?? {};
  return [
    ['study_id', study.study_id ?? null],
    ['version', study.version ?? null],
    ['retention_days', d.retention_days ?? null],
    ['secondary_use', d.secondary_use ?? null],
    ['contact', d.contact ?? null],
    ['irb_reference', d.irb_reference ?? null],
    ['consent_tiers', [...(study.consent_tiers ?? [])].sort()],
    ['default_tier', study.default_tier ?? null],
    ['modalities', [...(study.modalities ?? [])].sort()],
    ['calibration', study.calibration ?? null],
    ['tasks', study.tasks ?? null],
  ];
}

/**
 * What travels into the session manifest.
 *
 * The hash rather than the definition, plus enough to read a session's
 * provenance without resolving the hash — the same shape `AOISet.provenance`
 * takes, for the same reason.
 */
export async function studyProvenance(study) {
  return {
    study_id: study.study_id,
    study_version: study.version,
    study_content_hash: await contentHash(study),
    modalities: [...study.modalities].sort(),
  };
}

/** Does this study need the microphone? Drives the getUserMedia constraints. */
export function needsAudio(study) {
  return (study.modalities ?? []).some((m) => AUDIO_MODALITIES.includes(m));
}

/** The consent tiers this study offers, in the canonical order. */
export function offeredTiers(study) {
  const offered = new Set(study.consent_tiers ?? []);
  const audio = needsAudio(study);
  return CONSENT_TIERS.filter((t) => offered.has(t.id)).map((t) => tierCopy(t, { audio }));
}

/**
 * The disclosure the consent flow shows, derived from the study.
 *
 * Replaces `consent.js`'s `STUDY_DISCLOSURE` constant. It throws rather than
 * returning a default, because every caller is about to put this text in front
 * of a participant.
 */
export function disclosureFor(study) {
  const { valid, reasons } = validateStudy(study);
  if (!valid) {
    throw new Error(`study definition is not usable: ${reasons.join('; ')}`);
  }
  return {
    retentionDays: study.disclosure.retention_days,
    secondaryUse: study.disclosure.secondary_use,
    contact: study.disclosure.contact,
    irbReference: study.disclosure.irb_reference ?? null,
  };
}

function isId(v) {
  return typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(v);
}

function nonEmpty(v) {
  return typeof v === 'string' && v.trim().length > 0;
}

/**
 * Fetch and validate a study definition.
 *
 * Throws on anything short of a usable study: a missing file, malformed JSON,
 * or a definition that fails validation. The capture page cannot proceed past
 * this, and should not — the alternative is a participant consenting to a
 * protocol nobody can reconstruct.
 */
/**
 * The study a URL asks for, or null when it asks for none.
 *
 * Null, not a default. The page used to fall back to `m0` here, and a session
 * meant for `au-expressions` ran the full gaze pilot instead: nothing on screen
 * named the protocol, so four minutes of calibration were recorded before
 * anyone could notice. A missing choice is shown as a choice.
 */
export function studyIdFromUrl(search) {
  const id = new URLSearchParams(search ?? '').get('study');
  return id && id.trim() ? id.trim() : null;
}

/**
 * The studies a researcher can pick from when the URL names none.
 *
 * A list, because a static host cannot enumerate a directory. A test keeps it
 * equal to `studies/*.json`, so a study cannot exist without being offered or
 * be offered without existing.
 */
export async function loadStudyIndex({ base = '/studies' } = {}) {
  const res = await fetch(`${base}/index.json`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`no study index at ${base}/index.json (HTTP ${res.status})`);
  const index = await res.json();
  if (!Array.isArray(index?.studies)) throw new Error('study index has no "studies" list');
  return index.studies;
}

/** One line naming the protocol, for the operator to check before starting. */
export function describeStudy(study) {
  const kinds = (study.tasks ?? []).map((t) => t.type).filter((t) => t !== 'chinrest');
  return `${study.name} — ${study.study_id} v${study.version}`
    + (kinds.length ? ` · ${kinds.join(', ')}` : '');
}

export async function loadStudy(studyId, { base = '/studies' } = {}) {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(studyId ?? '')) {
    throw new Error(`not a usable study id: ${studyId}`);
  }

  const url = `${base}/${studyId}.json`;
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`no study definition at ${url} (HTTP ${res.status})`);
  }

  let study;
  try {
    study = await res.json();
  } catch (err) {
    throw new Error(`${url} is not valid JSON: ${err.message}`);
  }

  // The id in the file wins over the id in the URL, and a mismatch is fatal
  // rather than silently preferring one. `?study=pilot` resolving to a file
  // that calls itself something else means the session would be labelled with
  // an id that does not describe the protocol it ran.
  if (study.study_id !== studyId) {
    throw new Error(
      `${url} declares study_id "${study.study_id}", not "${studyId}"`);
  }

  const { valid, reasons } = validateStudy(study);
  if (!valid) {
    throw new Error(`${url} is not a usable study: ${reasons.join('; ')}`);
  }
  return study;
}

/**
 * Everything the consent flow needs, resolved from a study.
 *
 * `consent.js` takes this rather than the study itself: it keeps that module a
 * renderer, and it avoids the import cycle that would otherwise exist since
 * this module imports the tier definitions from there.
 */
export function protocolFor(study) {
  const audio = needsAudio(study);
  return {
    studyId: study.study_id,
    disclosure: disclosureFor(study),
    tiers: offeredTiers(study),
    defaultTier: study.default_tier ?? null,
    // What the participant is told happens, derived from the protocol rather
    // than written beside it — see `activitiesFor`.
    activity: {
      audio,
      devices: audio ? 'camera and microphone' : 'camera',
      records: audio ? 'video and audio' : 'video (no audio)',
      doing: activitiesFor(study),
    },
  };
}

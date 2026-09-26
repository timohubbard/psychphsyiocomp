/**
 * Tiered consent.
 *
 * §6.5 recommends the shape: "raw video processed and discarded within the
 * session by default, with an explicit, separately-consented opt-in for
 * raw-video retention where research reproducibility genuinely requires it."
 * The `sessions` table has carried a `consent_tier` column since M0; this is
 * what finally sets it, and what makes it mean something.
 *
 * Two things this module refuses to do.
 *
 * It will not call anything "anonymised". §6.4: face video resists simple
 * de-identification — blurring leaves gait, body and voice cues — and voice is
 * *itself* a biometric identifier that pitch-shifting does not reliably defeat.
 * The honest default is that raw face and voice recordings are identifiable
 * data requiring the same protections as any other directly identifying record,
 * and the participant-facing text says exactly that.
 *
 * It will not bundle the tiers into one checkbox. Each is a separate decision
 * with a separate consequence, and a participant who agrees to have their brow
 * movement measured has not thereby agreed to have their voice transcribed.
 */

/**
 * Retention ceiling, in days.
 *
 * §6.4 found no published guidance reconciling BIPA's three-year outer bound
 * with GDPR's "no longer than necessary" standard. The practical synthesis: set
 * the policy to the SHORTER of the specific research justification's actual
 * need and three years, and document the justification. Three years is the hard
 * cap that satisfies BIPA; the study is expected to choose something shorter
 * and say why.
 */
export const MAX_RETENTION_DAYS = 3 * 365;

/**
 * The tiers, in increasing order of what is kept.
 *
 * `features_only` is the default because §6.5's data-minimisation argument
 * points there — but note that it is a real tradeoff and not a free win: it
 * costs the raw data that quality control, re-analysis and reproducibility all
 * depend on. This project's whole record-first architecture exists because
 * §2.2 found engine choice swinging results on identical video, and that
 * argument only works if the video is still there. A study that discards media
 * by default should know it is trading reproducibility for exposure.
 */
export const CONSENT_TIERS = [
  {
    id: 'features_only',
    label: 'Measurements only',
    summary: 'Your recording is analysed and then deleted.',
    keeps: [
      'Numbers derived from the recording — where you looked, how your face moved.',
      'No video. No audio. Nothing a person could watch or listen to.',
      // research/pass5 (ethics section): gaze traces, facial-movement and voice
      // features have each been used to re-identify people in published work.
      // "Nothing a person could watch" is true; "anonymous" would not be.
      'These numbers are still personal data. Patterns in them could, in '
      + 'principle, help identify you, so they are protected like the recording.',
    ],
    consequence:
      'The recording cannot be re-analysed later if the analysis is improved.',
  },
  {
    id: 'media_retained',
    label: 'Keep the recording',
    summary: 'Your video and audio are stored so the analysis can be re-run.',
    keeps: [
      'Everything above, plus the original video and audio.',
      'This is identifiable data. Blurring a face does not change that, and a '
      + 'voice is itself an identifier.',
    ],
    consequence:
      'Researchers can improve the analysis and re-run it on your recording.',
    // What this tier says when the study records no audio. Telling a
    // participant their audio is kept when no microphone is ever opened is a
    // disclosure of a different protocol — see `tierCopy`.
    withoutAudio: {
      summary: 'Your video is stored so the analysis can be re-run. No audio is recorded.',
      keeps: [
        'Everything above, plus the original video.',
        'This is identifiable data. Blurring a face does not change that.',
      ],
    },
  },
  {
    id: 'media_plus_transcript',
    label: 'Keep the recording and transcribe speech',
    summary: 'As above, plus a written transcript of what you said.',
    keeps: [
      'Everything above, plus the words you spoke, written down.',
      'A transcript can contain anything you happened to say.',
    ],
    consequence:
      'Analysis can use what you said, not only how you said it.',
  },
];

export const DEFAULT_TIER = 'features_only';

/** Does this tier permit keeping the raw recording? */
export function retainsMedia(tier) {
  return tier === 'media_retained' || tier === 'media_plus_transcript';
}

/** Does this tier permit producing a transcript? */
export function allowsTranscript(tier) {
  return tier === 'media_plus_transcript';
}

/**
 * Validate a consent record before a session may start.
 *
 * Returns `{ valid, reasons }`. Refuses rather than defaulting: a session that
 * starts without a recorded decision has no defensible basis, and silently
 * assuming the most restrictive tier would still be assuming.
 */
export function validateConsent(record) {
  const reasons = [];

  if (!record || typeof record !== 'object') {
    return { valid: false, reasons: ['no consent record'] };
  }
  if (!CONSENT_TIERS.some((t) => t.id === record.tier)) {
    reasons.push('no tier chosen');
  }
  if (record.understood !== true) {
    reasons.push('the disclosure was not acknowledged');
  }

  // 45 CFR 46.116 requires informed-consent elements to address retention and
  // secondary use EXPLICITLY for video/audio/biometric capture. A flow that
  // omits either is not merely thin, it is missing a required element.
  if (!Number.isFinite(record.retentionDays) || record.retentionDays <= 0) {
    reasons.push('no retention period stated');
  } else if (record.retentionDays > MAX_RETENTION_DAYS) {
    reasons.push(
      `retention ${record.retentionDays} days exceeds the ${MAX_RETENTION_DAYS}-day cap`);
  }
  if (typeof record.secondaryUse !== 'string' || !record.secondaryUse.trim()) {
    reasons.push('no secondary-use disclosure');
  }

  return { valid: reasons.length === 0, reasons };
}

/**
 * A tier's wording as shown for a study that does or does not record audio.
 *
 * The consent record stores exactly this, so what was agreed to is what was
 * on screen: recording the canonical audio wording for a participant who was
 * shown the video-only wording would misstate their consent in the other
 * direction.
 */
export function tierCopy(tier, { audio = true } = {}) {
  if (!tier) return tier;
  const { withoutAudio, ...base } = tier;
  return audio || !withoutAudio ? base : { ...base, ...withoutAudio };
}

/**
 * The automated-analysis notice, built from what this study measures.
 *
 * EU AI Act Art 50(3), applicable since 2 August 2026, requires people exposed
 * to an emotion recognition system to be told. Research use is probably outside
 * the Act (Art 2(6)), but only while it is solely scientific, and the notice
 * costs a paragraph — research/pass5-legal-gaps.md recommends it regardless
 * and the Commission's Art 50 guidelines endorse merging it with the GDPR
 * notice. It says what the software does NOT do as well, because those are
 * the things a participant is most likely to assume.
 */
export function analysisNotice(measures) {
  if (!measures?.length) return '';
  return `Software analyses the recording automatically to measure ${joinAnd(measures)}. `
    + 'It does not identify who you are, it does not label your emotions, and '
    + 'nothing is decided about you from it. The researchers may use these '
    + 'measurements to study reactions such as attention or emotion.';
}

/**
 * What a participant can do after the session, in words they can act on.
 *
 * The policy is the simplest honest one (research/pass5, ethics section):
 * on request, the recording AND every measurement from it are deleted —
 * `npm run withdraw` does exactly that. The one exception is stated rather
 * than hidden. The complaint route is UK GDPR Art 13(2)(d).
 */
export function withdrawalText(retentionDays) {
  return `If you change your mind later, contact us (above) with the session code `
    + `shown at the end, within the ${retentionDays} days. We will delete your `
    + 'recording and every measurement taken from it. The only thing we cannot '
    + 'take back is a result already combined into a published summary that does '
    + 'not identify anyone. You can also complain to a data protection authority '
    + '— in the UK, the Information Commissioner’s Office (ico.org.uk).';
}

/**
 * The record written into the session manifest.
 *
 * Carries what was disclosed, not just what was agreed. A tier alone cannot be
 * audited later — "they consented to media retention" is not answerable without
 * knowing what they were told retention meant.
 */
export function consentRecord({ tier, retentionDays, secondaryUse, contact,
                                irbReference = null, controller = null, lawfulBasis = null,
                                specialCategoryBasis = null, audience = 'developer',
                                analysis = null, withdrawal = null,
                                studyId, audio = true }) {
  const chosen = tierCopy(CONSENT_TIERS.find((t) => t.id === tier), { audio });
  return {
    tier,
    understood: true,
    retentionDays,
    secondaryUse,
    contact: contact ?? null,
    irb_reference: irbReference,
    // The UK GDPR Art 13 items, exactly as shown. Null where the study did not
    // state them, which only a developer self-test is allowed to do.
    controller,
    lawful_basis: lawfulBasis,
    special_category_basis: specialCategoryBasis,
    audience,
    study_id: studyId ?? null,
    agreed_utc: new Date().toISOString(),
    disclosed: chosen
      ? { label: chosen.label, keeps: chosen.keeps, consequence: chosen.consequence }
      : null,
    // The two paragraphs verbatim, for the same reason as `disclosed`.
    analysis_notice: analysis,
    withdrawal,
    // Recorded so a later reader knows which rules this flow was built against
    // rather than having to infer it from the date.
    basis: 'UK GDPR Art 13 notice; EU AI Act Art 50(3) automated-analysis notice; '
      + '45 CFR 46.116 elements; retention capped at 3 years',
  };
}

// ---------------------------------------------------------------------------
// consent
//
// Runs before the camera is ever requested. A permission prompt that appears
// before the participant has been told what happens to the recording asks them
// to decide with the information in the wrong order.
// ---------------------------------------------------------------------------

/** "a", "a and b", "a, b and c" — for the consent sentence. */
export function joinAnd(items) {
  if (items.length <= 1) return items.join('');
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

export function runConsent(host, protocol) {
  // Takes a resolved protocol rather than a study definition, and has no
  // fallback for a missing one. Two reasons. It keeps this module a renderer —
  // `study.js` decides what a study offers, this draws it — and it avoids an
  // import cycle, since `study.js` already imports the tiers from here. A
  // default would also mean this software stating a retention period on a
  // researcher's behalf, which is the thing study definitions exist to stop.
  const {
    disclosure, tiers: tiersOffered, defaultTier, studyId, activity,
  } = protocol ?? {};
  if (!disclosure || !Array.isArray(tiersOffered) || !tiersOffered.length || !activity) {
    throw new Error('runConsent needs a resolved protocol: see study.js');
  }
  const doing = activity.doing.length
    ? ` while you ${joinAnd(activity.doing)}` : '';
  const analysis = analysisNotice(activity.measures);
  const withdrawal = withdrawalText(disclosure.retentionDays);

  return new Promise((resolve) => {
    const root = document.createElement('div');
    root.className = 'chinrest';   // reuses the full-screen overlay styling
    host.appendChild(root);

    const tiers = tiersOffered.map((t, i) => `
      <label class="consent-tier">
        <input type="radio" name="tier" value="${t.id}"
               ${t.id === (defaultTier ?? tiersOffered[0].id) ? 'checked' : ''}>
        <span>
          <strong>${t.label}</strong>
          <span class="consent-summary">${t.summary}</span>
          <ul>${t.keeps.map((k) => `<li>${k}</li>`).join('')}</ul>
          <span class="consent-consequence">${t.consequence}</span>
        </span>
      </label>`).join('');

    root.innerHTML = `
      <div class="cr-panel consent-panel">
        <h1>Before we start</h1>
        ${disclosure.audience === 'participants' ? '' : `
        <p class="cr-error"><strong>Developer self-test.</strong> This study has
           no ethics approval recorded and is not for participants. If someone
           has asked you to take part in research through this page, stop here
           and contact them.</p>`}
        <p>This session records ${activity.records} from your
           ${activity.devices}${doing}.</p>

        ${analysis ? `<p id="analysisNotice"><strong>Automated analysis.</strong> ${analysis}</p>` : ''}

        <p><strong>Your recording is identifiable.</strong> A face is
           identifiable, and so is a voice — blurring a video or shifting a
           pitch does not reliably change that. We are not going to tell you the
           recording is anonymous, because it would not be true.</p>

        <h2>What would you like us to keep?</h2>
        ${tiers}

        <div class="note">
          <strong>How long:</strong> your data is kept for
          ${disclosure.retentionDays} days and then deleted.<br>
          <strong>Who else sees it:</strong> ${disclosure.secondaryUse}<br>
          <strong>Questions or concerns:</strong> ${disclosure.contact}<br>
          ${disclosure.controller
            ? `<strong>Responsible for your data:</strong> ${disclosure.controller}<br>` : ''}
          ${disclosure.lawfulBasis
            ? `<strong>Legal basis:</strong> ${disclosure.lawfulBasis}${
              disclosure.specialCategoryBasis ? `; ${disclosure.specialCategoryBasis}` : ''}<br>` : ''}
          ${disclosure.irbReference
            ? `Approved under ${disclosure.irbReference}.<br>` : ''}
          You can stop at any time, and nothing leaves your machine until you
          choose to finish.<br>
          <span id="withdrawalText"><strong>Changing your mind:</strong> ${withdrawal}</span>
        </div>

        <p class="consent-ack">
          <label>
            <input type="checkbox" id="consentUnderstood">
            I have read this and I agree to take part.
          </label>
        </p>
        <p class="cr-error" id="consentError"></p>
        <button id="consentGo">Continue</button>
      </div>`;

    const error = root.querySelector('#consentError');

    root.querySelector('#consentGo').addEventListener('click', () => {
      const tier = root.querySelector('input[name="tier"]:checked')?.value;
      const understood = root.querySelector('#consentUnderstood').checked;

      const record = consentRecord({
        tier,
        retentionDays: disclosure.retentionDays,
        secondaryUse: disclosure.secondaryUse,
        contact: disclosure.contact,
        irbReference: disclosure.irbReference,
        controller: disclosure.controller,
        lawfulBasis: disclosure.lawfulBasis,
        specialCategoryBasis: disclosure.specialCategoryBasis,
        audience: disclosure.audience,
        analysis: analysis || null,
        withdrawal,
        studyId,
        audio: activity.audio,
      });
      record.understood = understood;

      const check = validateConsent(record);
      if (!check.valid) {
        // Named rather than generic: a participant can only fix what they are
        // told about, and "please complete the form" tells them nothing.
        error.textContent = check.reasons.join('; ');
        return;
      }

      root.remove();
      resolve(record);
    });
  });
}

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
import { isSafeCompletionUrl } from './recruitment.js';
import { activitiesFor } from './sequence.js';

/** Every modality this platform can collect, and what it costs to say yes. */
export const MODALITIES = [
  {
    id: 'gaze',
    label: 'Screen-based eye tracking',
    needs: ['camera'],
    note: 'Requires the chinrest step and a calibration grid.',
    // What the participant is told is measured (consent.js analysisNotice).
    measures: 'where on the screen you look',
  },
  {
    id: 'face',
    label: 'Facial expression (Action Units)',
    needs: ['camera'],
    note: 'Action Units only. No emotion labels are produced.',
    measures: 'how the muscles of your face move',
  },
  {
    id: 'voice',
    label: 'Voice acoustics',
    needs: ['microphone'],
    note: 'eGeMAPS acoustic features. No valence channel exists (§2.3).',
    measures: 'the sound of your voice (pitch, loudness and timing — not your words)',
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
    measures: 'the movement of your chest and shoulders as you breathe',
  },
  {
    id: 'cardiac',
    label: 'Heart rate (pulse from the face)',
    needs: ['camera'],
    note: 'Heart rate only, per 10 s window, and only where the signal clears '
      + 'a quality gate. Unvalidated until checked against a chest strap; no '
      + 'HRV. Health data under GDPR Art. 9, like respiration. Needs good light, '
      + 'a still face and a high-bitrate recording.',
    measures: 'your pulse, from small changes in the colour of your skin',
  },
];

export const MODALITY_IDS = MODALITIES.map((m) => m.id);

/**
 * Who a study may be run on.
 *
 * Absent means `developer`: the person who built the software, testing it on
 * themselves. Every study shipped so far is that, including m0, whose contact
 * line still reads "Replace this with…". `participants` is the declaration that
 * the protocol has been through an ethics committee, and it is what unlocks
 * running it on anyone else — see the participant gate in `validateStudy`.
 */
export const AUDIENCES = ['developer', 'participants'];

export function audienceOf(study) {
  return study?.audience ?? 'developer';
}

/**
 * Modalities whose outputs are treated as special-category data by default.
 *
 * research/pass5-legal-gaps.md (GDPR section): CJEU C-21/23 and C-252/21 make
 * the controller's aim and the inference's accuracy irrelevant to whether data
 * "reveals" health, so respiration and affect-adjacent streams (facial action
 * units, vocal arousal features) default to Art 9. Gaze alone does not.
 * Heart rate is health data on its face (Art. 4(15)), whatever it is used for.
 */
export const SPECIAL_CATEGORY_MODALITIES = ['face', 'voice', 'respiration', 'cardiac'];

/**
 * A contact line that is still a template. The shipped studies' contact reads
 * "Replace this with the investigator and the route to the ethics board…", and
 * a non-empty check lets that straight through to a participant.
 */
const PLACEHOLDER = /replace (this|with)|placeholder|\btodo\b|\btbd\b|example\.[a-z]+/i;

/** An email address or a web address: a route a participant can actually use. */
const CONTACT_ROUTE = /[^\s@]+@[^\s@]+\.[a-z]{2,}|https?:\/\/\S+\.\S+/i;

/**
 * Modalities with an engine that runs in the browser. Under
 * `features_in_browser` nothing else can measure anything — the AU engines,
 * openSMILE, respiration and transcription all need the recording on a server.
 */
export const BROWSER_MODALITIES = ['gaze', 'face'];

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
    for (const field of ['irb_reference', 'controller', 'lawful_basis', 'special_category_basis']) {
      if (d[field] !== undefined && d[field] !== null && !nonEmpty(d[field])) {
        reasons.push(`disclosure.${field} is present but empty`);
      }
    }
  }

  // --- who it may be run on -------------------------------------------------
  if (study.audience !== undefined && !AUDIENCES.includes(study.audience)) {
    reasons.push(`unknown audience: ${study.audience} (expected ${AUDIENCES.join(' or ')})`);
  }
  if (audienceOf(study) === 'participants' && d && typeof d === 'object') {
    reasons.push(...participantGate(study, d));
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
  } else if (Array.isArray(study.tasks)) {
    reasons.push(...stimuliReasons(study.tasks));
  }
  reasons.push(...questionsReasons(study));
  reasons.push(...conditionReasons(study));
  reasons.push(...analysisReasons(study.analysis, study));
  const url = study.recruitment?.completion_url;
  if (study.recruitment !== undefined && url !== undefined && !isSafeCompletionUrl(url)) {
    reasons.push('recruitment.completion_url must be an https address (or localhost for testing)');
  }

  // A transcript tier with no microphone offers the participant a choice that
  // cannot happen, and records a consent to transcription for a session with
  // no audio. Mirrored in server/study.py.
  if (Array.isArray(tiers) && tiers.includes('media_plus_transcript')
      && Array.isArray(mods) && !mods.some((m) => AUDIO_MODALITIES.includes(m))) {
    reasons.push('media_plus_transcript is offered but no modality records audio');
  }

  // A tier that promises the video never leaves the device cannot be offered
  // for a modality that can only be measured from the video on a server: the
  // participant would consent to a measurement that then silently never
  // happens. Mirrored in server/study.py.
  if (Array.isArray(tiers) && tiers.includes('features_in_browser') && Array.isArray(mods)) {
    const serverOnly = mods.filter((m) => !BROWSER_MODALITIES.includes(m));
    if (serverOnly.length) {
      reasons.push(`features_in_browser is offered but ${serverOnly.join(', ')} can only `
        + 'be measured from a recording on the server');
    }
  }

  return { valid: reasons.length === 0, reasons };
}

/**
 * Between-subject conditions, and tasks limited to some of them. Mirrored in
 * server/study.py.
 *
 * A task naming an arm the study does not define would never run for anyone,
 * and a task naming arms in a study with no conditions would run for nobody
 * or everybody depending on how the question was read — both refused.
 */
function conditionReasons(study) {
  const reasons = [];
  const c = study.conditions;
  const arms = Array.isArray(c?.arms) ? c.arms : null;
  if (c !== undefined) {
    if (!arms || arms.length < 2) reasons.push('conditions.arms needs at least two arms');
    else if (!arms.every(isId)) reasons.push('conditions.arms must be slugs');
    else if (new Set(arms).size !== arms.length) reasons.push('conditions.arms repeats an arm');
  }
  for (const task of Array.isArray(study.tasks) ? study.tasks : []) {
    if (task?.arms === undefined) continue;
    if (!arms) {
      reasons.push(`task ${task.type} names arms but the study defines no conditions`);
    } else if (!Array.isArray(task.arms) || !task.arms.length
        || task.arms.some((a) => !arms.includes(a))) {
      reasons.push(`task ${task.type}: arms must be a non-empty subset of conditions.arms`);
    }
  }
  return reasons;
}

/**
 * The pre-declared analysis plan (server/cohort.py). Validated here too, so a
 * study with a broken plan is refused before anyone is recorded under it, not
 * discovered at analysis time. Not in the content hash — see server/cohort.py
 * analysis_hash. Mirrored in server/study.py.
 */
function analysisReasons(a, study) {
  if (a === undefined || a === null) return [];
  if (typeof a !== 'object' || Array.isArray(a)) return ['analysis must be an object'];
  const reasons = [];
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  for (const key of ['aoi_pad_deg', 'heatmap_sigma_deg']) {
    if (a[key] !== undefined && !(num(a[key]) && a[key] >= 0 && a[key] <= 10)) {
      reasons.push(`analysis.${key} must be a number of degrees between 0 and 10`);
    }
  }
  (a.exclusions ?? []).forEach((rule, i) => {
    const where = `analysis.exclusions[${i}]`;
    if (!rule || typeof rule !== 'object' || !nonEmpty(rule.metric)) {
      reasons.push(`${where} needs a metric`);
      return;
    }
    const lo = rule.min ?? null;
    const hi = rule.max ?? null;
    if (lo === null && hi === null) reasons.push(`${where} needs a min or a max`);
    if ((lo !== null && !num(lo)) || (hi !== null && !num(hi))) {
      reasons.push(`${where}: min and max must be numbers`);
    } else if (lo !== null && hi !== null && lo > hi) reasons.push(`${where}: min is above max`);
    // Optional: which engine's value the rule reads. Several engines write a
    // metric of the same name (face_detect_rate from the browser and the server
    // pass; mean_luminance from face and respiration), and without it the rule
    // reads the median across all of them.
    if ('source' in rule && !nonEmpty(rule.source)) reasons.push(`${where}: source must be a non-empty string`);
  });
  const names = new Set();
  (a.epochs ?? []).forEach((e, i) => {
    const where = `analysis.epochs[${i}]`;
    if (!e || typeof e !== 'object') { reasons.push(`${where} must be an object`); return; }
    if (!isId(e.name) || names.has(e.name)) reasons.push(`${where} needs a unique slug name`);
    names.add(e.name);
    if (!nonEmpty(e.event_type)) reasons.push(`${where} needs an event_type`);
    if (!Array.isArray(e.channels) || !e.channels.length || !e.channels.every(nonEmpty)) {
      reasons.push(`${where} needs a list of channels`);
    }
    const { pre_ms: pre, post_ms: post } = e;
    if (!(num(pre) && pre >= 0 && num(post) && post > 0)) {
      reasons.push(`${where}: pre_ms >= 0 and post_ms > 0 are required`);
    }
    const b = e.baseline_ms === undefined ? [-200, 0] : e.baseline_ms;
    if (b !== null && !(Array.isArray(b) && b.length === 2 && b.every(num) && b[0] < b[1]
        && num(pre) && num(post) && b[0] >= -pre && b[1] <= post)) {
      reasons.push(`${where}: baseline_ms must be [start, end] inside the window`);
    }
    const hz = e.resample_hz ?? 30;
    if (!(num(hz) && hz > 0 && hz <= 1000)) reasons.push(`${where}: resample_hz must be between 0 and 1000`);
  });
  reasons.push(...contrastReasons(a, study));
  return reasons;
}

export const QUESTION_KINDS = ['likert', 'choice', 'slider', 'text'];
export const MAX_FREE_TEXT = 1000;
const QUESTIONS_TASK_KEYS = new Set(['type', 'id', 'title', 'randomise', 'items', 'arms']);
const QUESTION_ITEM_KEYS = { likert: ['points', 'anchors'], choice: ['options'],
  slider: ['min', 'max', 'anchors'], text: ['max_chars'] };

/**
 * Questions a participant answers on screen (web/src/main.js runQuestion).
 * Mirrored in server/study.py.
 *
 * Scales, choices and sliders by default. A free-text answer is refused unless
 * the study opts in with `disclosure.free_text: true`, because typed text is
 * where people write their name, their diagnosis, anything — it bypasses the
 * pseudonymisation the rest of the data goes through, and the consent screen
 * must say so (consent.js tierCopy) before anyone types a word. The same
 * reasoning as the transcript tier: identifying words need their own consent.
 * Unknown keys are refused, so a misspelt "anchor" is never silently ignored.
 */
function questionsReasons(study) {
  const reasons = [];
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  const labels = (a) => Array.isArray(a) && a.length === 2 && a.every((s) => nonEmpty(s) && s.length <= 80);
  const freeText = study.disclosure?.free_text;
  const ids = new Set();
  let asksText = false;
  (Array.isArray(study.tasks) ? study.tasks : []).forEach((task, ti) => {
    if (task?.type !== 'questions') return;
    const where = `task ${isId(task.id) ? task.id : ti + 1} (questions)`;
    const extra = Object.keys(task).filter((k) => !QUESTIONS_TASK_KEYS.has(k)).sort();
    if (extra.length) reasons.push(`${where} has unknown keys: ${extra.join(', ')}`);
    if (!isId(task.id) || ids.has(task.id)) reasons.push(`${where} needs a unique slug id`);
    ids.add(task.id);
    if (task.title !== undefined && !(nonEmpty(task.title) && task.title.length <= 200)) {
      reasons.push(`${where}: title must be 1 to 200 characters`);
    }
    if (task.randomise !== undefined && typeof task.randomise !== 'boolean') {
      reasons.push(`${where}: randomise must be true or false`);
    }
    if (!Array.isArray(task.items) || !task.items.length || task.items.length > 50) {
      reasons.push(`${where} needs 1 to 50 items`);
      return;
    }
    const itemIds = new Set();
    task.items.forEach((it, i) => {
      const w = `${where} item ${i + 1}`;
      if (!it || typeof it !== 'object' || Array.isArray(it)) { reasons.push(`${w} must be an object`); return; }
      if (!QUESTION_KINDS.includes(it.kind)) { reasons.push(`${w}: kind must be likert, choice, slider or text`); return; }
      const allowed = new Set(['id', 'kind', 'prompt', 'allow_skip', ...QUESTION_ITEM_KEYS[it.kind]]);
      const ex = Object.keys(it).filter((k) => !allowed.has(k)).sort();
      if (ex.length) reasons.push(`${w} has unknown keys for a ${it.kind} item: ${ex.join(', ')}`);
      if (!isId(it.id) || itemIds.has(it.id)) reasons.push(`${w} needs a unique slug id`);
      itemIds.add(it.id);
      if (!(nonEmpty(it.prompt) && it.prompt.length <= 500)) reasons.push(`${w}: prompt must be 1 to 500 characters`);
      if (it.allow_skip !== undefined && typeof it.allow_skip !== 'boolean') {
        reasons.push(`${w}: allow_skip must be true or false`);
      }
      if (it.kind === 'likert') {
        if (!(Number.isInteger(it.points) && it.points >= 2 && it.points <= 11)) {
          reasons.push(`${w}: points must be a whole number from 2 to 11`);
        }
        if (!labels(it.anchors)) reasons.push(`${w}: anchors must be two labels of up to 80 characters, for the two ends`);
      } else if (it.kind === 'choice') {
        const opts = it.options;
        const seen = new Set();
        const ok = Array.isArray(opts) && opts.length >= 2 && opts.length <= 12 && opts.every((o) => {
          const good = o && typeof o === 'object' && isId(o.id) && !seen.has(o.id)
            && nonEmpty(o.label) && o.label.length <= 120;
          if (good) seen.add(o.id);
          return good;
        });
        if (!ok) reasons.push(`${w}: options must be 2 to 12 choices, each with a unique slug id and a label of 1 to 120 characters`);
      } else if (it.kind === 'slider') {
        if (!(num(it.min) && num(it.max) && it.min < it.max)) reasons.push(`${w}: a slider needs numbers min < max`);
        if (!labels(it.anchors)) reasons.push(`${w}: anchors must be two labels of up to 80 characters, for the two ends`);
      } else if (it.kind === 'text') {
        asksText = true;
        if (freeText !== true) {
          reasons.push(`${w}: a typed answer can carry names or health details, so the study must opt in `
            + 'with disclosure.free_text: true — and participants are told before they type');
        }
        if (it.max_chars !== undefined && !(Number.isInteger(it.max_chars) && it.max_chars >= 1
            && it.max_chars <= MAX_FREE_TEXT)) {
          reasons.push(`${w}: max_chars must be a whole number from 1 to ${MAX_FREE_TEXT}`);
        }
      }
    });
  });
  if (freeText !== undefined && freeText !== null && typeof freeText !== 'boolean') {
    reasons.push('disclosure.free_text must be true or false');
  } else if (freeText === true && !asksText) {
    // Declared and read by nothing: participants would be warned about typing
    // they are never asked to do.
    reasons.push('disclosure.free_text is true but no question asks for typed text');
  }
  return reasons;
}

/**
 * What the participant's answers will contain, for the consent screen:
 * 'none', 'choices' (scales, choices, sliders), or 'free_text'.
 */
export function answersKind(study) {
  const items = (study?.tasks ?? []).filter((t) => t?.type === 'questions').flatMap((t) => t.items ?? []);
  if (!items.length) return 'none';
  return items.some((it) => it.kind === 'text') ? 'free_text' : 'choices';
}

const CONTRAST_KEYS = new Set(['name', 'epochs', 'channel', 'arms', 'window_ms', 'n_permutations',
  'seed', 'alpha', 'tail', 'cluster']);

/**
 * Declared contrasts between two arms (server/inference.py). Everything the
 * test needs is fixed here — the window, the permutation budget and the seed —
 * so nothing about it is chosen after the data is seen. Unknown keys are
 * refused: a misspelt "windows_ms" silently ignored would test the wrong
 * thing. Mirrored in server/study.py.
 */
function contrastReasons(a, study) {
  if (a.contrasts === undefined) return [];
  if (!Array.isArray(a.contrasts)) return ['analysis.contrasts must be a list'];
  const num = (v) => typeof v === 'number' && Number.isFinite(v);
  const sets = new Map((Array.isArray(a.epochs) ? a.epochs : [])
    .filter((e) => e && typeof e === 'object').map((e) => [e.name, e]));
  const arms = Array.isArray(study?.conditions?.arms) ? study.conditions.arms : [];
  const reasons = [];
  const names = new Set();
  a.contrasts.forEach((c, i) => {
    const where = `analysis.contrasts[${i}]`;
    if (!c || typeof c !== 'object' || Array.isArray(c)) { reasons.push(`${where} must be an object`); return; }
    const extra = Object.keys(c).filter((k) => !CONTRAST_KEYS.has(k)).sort();
    if (extra.length) reasons.push(`${where} has unknown keys: ${extra.join(', ')}`);
    if (!isId(c.name) || names.has(c.name)) reasons.push(`${where} needs a unique slug name`);
    names.add(c.name);
    const set = sets.get(c.epochs);
    if (!set) reasons.push(`${where}: epochs must name an epoch set in analysis.epochs`);
    else if (!Array.isArray(set.channels) || !set.channels.includes(c.channel)) {
      reasons.push(`${where}: channel must be one of that epoch set's channels`);
    }
    if (!arms.length) reasons.push(`${where}: a contrast compares arms, and the study defines no conditions`);
    else if (!Array.isArray(c.arms) || c.arms.length !== 2 || c.arms[0] === c.arms[1]
        || !c.arms.every((x) => arms.includes(x))) {
      reasons.push(`${where}: arms must be two different arms from conditions.arms`);
    }
    const w = c.window_ms;
    if (!(Array.isArray(w) && w.length === 2 && w.every(num) && w[0] < w[1] && set
        && num(set.pre_ms) && num(set.post_ms) && w[0] >= -set.pre_ms && w[1] <= set.post_ms)) {
      reasons.push(`${where}: window_ms must be [start, end] inside the epoch`);
    }
    if (!(Number.isInteger(c.n_permutations) && c.n_permutations >= 1000 && c.n_permutations <= 100000)) {
      reasons.push(`${where}: n_permutations must be a whole number from 1000 to 100000`);
    }
    if (!Number.isInteger(c.seed)) {
      reasons.push(`${where}: seed must be a whole number — the test is random, and the seed makes it repeatable`);
    }
    const alpha = c.alpha ?? 0.05;
    if (!(num(alpha) && alpha > 0 && alpha <= 0.5)) reasons.push(`${where}: alpha must be above 0 and at most 0.5`);
    if (!['two', 'greater', 'less'].includes(c.tail ?? 'two')) reasons.push(`${where}: tail must be two, greater or less`);
    if (c.cluster !== undefined && c.cluster !== null) {
      const k = c.cluster;
      if (typeof k !== 'object' || Array.isArray(k)) reasons.push(`${where}.cluster must be an object`);
      else {
        const ex = Object.keys(k).filter((x) => x !== 'p_threshold').sort();
        if (ex.length) reasons.push(`${where}.cluster has unknown keys: ${ex.join(', ')}`);
        const p = k.p_threshold ?? 0.05;
        if (!(num(p) && p > 0 && p <= 0.5)) reasons.push(`${where}.cluster: p_threshold must be above 0 and at most 0.5`);
      }
    }
  });
  return reasons;
}

/** Stimuli live under studies/stimuli/, named plainly, and nowhere else. */
const STIMULUS_SRC = /^stimuli\/[A-Za-z0-9][A-Za-z0-9._-]*(\/[A-Za-z0-9][A-Za-z0-9._-]*)*$/;
const SHA256 = /^[0-9a-f]{64}$/;
const MAX_STIMULUS_MS = 10 * 60 * 1000;

/**
 * Image and video stimulus items. Mirrored in server/study.py.
 *
 * `stimulus_id` is unique across the whole study because AOIs and every
 * per-stimulus result are keyed on it. `sha256` is required, not optional: it
 * is how the study's content hash comes to cover the pixels and not just the
 * file name (web/src/stimuli.js checks it before consent). `duration_ms` is
 * required for videos too, as the most the stimulus may be shown for, because
 * the participant is told how long the task takes.
 */
function stimuliReasons(tasks) {
  const reasons = [];
  const seen = new Set();
  for (const task of tasks) {
    if (task?.type !== 'stimuli') continue;
    if (!Array.isArray(task.items) || !task.items.length) {
      reasons.push('a stimuli task has no items');
      continue;
    }
    if (task.randomise !== undefined && typeof task.randomise !== 'boolean') {
      reasons.push('stimuli.randomise must be true or false');
    }
    if (task.isi_ms !== undefined && !(Number.isFinite(task.isi_ms) && task.isi_ms >= 0)) {
      reasons.push('stimuli.isi_ms must be a non-negative number of milliseconds');
    }
    for (const it of task.items) {
      const id = it?.stimulus_id;
      const where = isId(id) ? `stimulus ${id}` : 'a stimulus';
      if (!isId(id)) reasons.push('stimulus_id must be a slug of letters, digits, dash or underscore');
      else if (seen.has(id)) reasons.push(`stimulus_id ${id} is used twice — AOIs and results are keyed on it`);
      seen.add(id);
      if (!['image', 'video'].includes(it?.kind)) reasons.push(`${where}: kind must be image or video`);
      if (typeof it?.src !== 'string' || !STIMULUS_SRC.test(it.src) || it.src.includes('..')) {
        reasons.push(`${where}: src must be a path under stimuli/`);
      }
      if (!SHA256.test(it?.sha256 ?? '')) reasons.push(`${where}: sha256 must be 64 lower-case hex digits`);
      if (!(Number.isFinite(it?.duration_ms) && it.duration_ms > 0 && it.duration_ms <= MAX_STIMULUS_MS)) {
        reasons.push(`${where}: duration_ms must be between 1 and ${MAX_STIMULUS_MS}`);
      }
      if (it?.sound !== undefined && typeof it.sound !== 'boolean') {
        reasons.push(`${where}: sound must be true or false`);
      }
    }
  }
  return reasons;
}

/**
 * What a study must carry before it may be run on anyone but the developer.
 *
 * The UK/EU route (Tim, 2026-09-26): an ethics committee reference, a contact
 * that is not a template, and the UK GDPR Art 13 items a participant must be
 * told at collection — who the controller is (13(1)(a)), the Art 6 lawful
 * basis (13(1)(c)), and, where face, voice or respiration is recorded, the
 * Art 9 condition relied on. Each is a refusal, not a warning: the page would
 * otherwise put an incomplete notice in front of a real person.
 * Mirrored in server/study.py.
 */
function participantGate(study, d) {
  const reasons = [];
  if (!nonEmpty(d.irb_reference)) {
    reasons.push('audience is participants but there is no disclosure.irb_reference '
      + '(the ethics committee approval reference, REC or IRB)');
  }
  if (nonEmpty(d.contact) && (PLACEHOLDER.test(d.contact) || !CONTACT_ROUTE.test(d.contact))) {
    reasons.push('disclosure.contact is still a placeholder or gives no email address '
      + 'or web address a participant could use');
  }
  if (!nonEmpty(d.controller)) {
    reasons.push('no disclosure.controller — UK GDPR Art 13(1)(a): who is responsible '
      + 'for the data');
  }
  if (!nonEmpty(d.lawful_basis)) {
    reasons.push('no disclosure.lawful_basis — UK GDPR Art 13(1)(c): the Art 6 basis');
  }
  const special = (study.modalities ?? []).filter((m) => SPECIAL_CATEGORY_MODALITIES.includes(m));
  if (special.length && !nonEmpty(d.special_category_basis)) {
    reasons.push(`${special.join(', ')} recorded but no disclosure.special_category_basis `
      + '— the Art 9 condition relied on for data treated as special category');
  }
  return reasons;
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

/**
 * The hashed subset, sorted so key order in the source file cannot matter.
 *
 * The first eleven entries are fixed. Fields added since are appended ONLY
 * when a study sets them, in the order below, so every study written before
 * they existed keeps the hash its sessions recorded — m0's is pinned in both
 * test suites. Adding a field here means adding it in the same position in
 * server/study.py's `_OPTIONAL_HASHED`.
 */
export function canonicalise(study) {
  const d = study.disclosure ?? {};
  const fixed = [
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
  const optional = [
    ['audience', study.audience],
    ['controller', d.controller],
    ['lawful_basis', d.lawful_basis],
    ['special_category_basis', d.special_category_basis],
    // Which arms exist is protocol. `recruitment` is not hashed: a completion
    // code changes per panel posting without the protocol changing.
    ['conditions', study.conditions],
    // Whether typed answers are collected changes what participants are told.
    ['free_text', d.free_text],
  ];
  return [...fixed, ...optional.filter(([, v]) => v !== undefined && v !== null)];
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
    // Written into every session, so a self-test can never be counted as a
    // participant later — cohort analysis leaves `developer` sessions out.
    audience: audienceOf(study),
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
  const answers = answersKind(study);
  return CONSENT_TIERS.filter((t) => offered.has(t.id)).map((t) => tierCopy(t, { audio, answers }));
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
    controller: study.disclosure.controller ?? null,
    lawfulBasis: study.disclosure.lawful_basis ?? null,
    specialCategoryBasis: study.disclosure.special_category_basis ?? null,
    audience: audienceOf(study),
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
export function protocolFor(study, { condition = null } = {}) {
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
      // What their answers will contain — the tiers' wording depends on it.
      answers: answersKind(study),
      devices: audio ? 'camera and microphone' : 'camera',
      records: audio ? 'video and audio' : 'video (no audio)',
      // This participant's arm: the consent describes what THEY will do.
      doing: activitiesFor(study, condition),
      // In MODALITIES order, whatever order the file lists them in.
      measures: MODALITIES.filter((m) => (study.modalities ?? []).includes(m.id))
        .map((m) => m.measures),
    },
  };
}

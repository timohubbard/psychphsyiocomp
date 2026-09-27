/**
 * The study builder's pure parts: editing a study object by path, the task
 * templates, and defaults. No DOM and no imports, so it runs under
 * `node --test`; builder.js renders it and validates with the capture page's
 * own web/src/study.js.
 */

/** A new study: a developer self-test, face only, one short task. Valid as is. */
export function blankStudy() {
  return {
    study_id: 'new-study',
    name: 'New study',
    version: '1.0.0',
    disclosure: {
      retention_days: 180,
      secondary_use: 'Analysed by the named research team only. Not sold, and not shared '
        + 'outside the team without a further, separate agreement.',
      contact: 'Replace this with the investigator and the route to the ethics board.',
      irb_reference: null,
    },
    consent_tiers: ['features_only', 'media_retained'],
    default_tier: 'features_only',
    modalities: ['face'],
    tasks: [{ type: 'rest_fixation', duration_ms: 20000 }],
  };
}

/**
 * Every task type the capture page knows, with a starting shape. `kind` is the
 * journey diagram's colour key (web/researcher/flow.js KINDS), so a task's
 * card and its block in the diagram match.
 */
export const TASK_TYPES = {
  chinrest: { label: 'Screen distance (bank card + blind spot)', kind: 'setup',
    hint: 'measures how far the participant sits', make: () => ({ type: 'chinrest' }) },
  calibration: { label: 'Gaze calibration dots', kind: 'gaze',
    hint: 'fits the gaze estimator', make: () => ({ type: 'calibration' }) },
  validation: { label: 'Gaze validation dots', kind: 'gaze',
    hint: 'checks it on fresh targets', make: () => ({ type: 'validation' }) },
  rest_fixation: { label: 'Rest on a cross', kind: 'rest',
    hint: 'a resting baseline', make: () => ({ type: 'rest_fixation', duration_ms: 60000 }) },
  read_aloud: { label: 'Read a passage aloud', kind: 'voice',
    hint: 'standard speech for voice features', make: () => ({ type: 'read_aloud', passage: 'default' }) },
  free_speech: { label: 'Talk freely to a prompt', kind: 'voice',
    hint: 'spontaneous speech', make: () => ({ type: 'free_speech', prompts: 'default' }) },
  expression_prompts: { label: 'Posed facial movements', kind: 'face',
    hint: 'known movements, for checking AUs', make: () => ({ type: 'expression_prompts', expressions: 'default', repeats: 2 }) },
  stimuli: { label: 'Pictures and videos', kind: 'stimuli',
    hint: 'your own stimuli, shown in order', make: () => ({ type: 'stimuli', isi_ms: 1000, items: [] }) },
};

/** The builder's sections, in the order the form shows them. */
export const SECTIONS = [
  { id: 'basics', title: 'Basics', blurb: 'What the study is called, and who it may be run on.' },
  { id: 'told', title: 'What participants are told', blurb: 'Shown on the consent screen, word for word.' },
  { id: 'measures', title: 'What is measured', blurb: 'Each measure is named to the participant before anything is recorded.' },
  { id: 'consent', title: 'Consent options', blurb: 'What the participant may choose to let you keep.' },
  { id: 'tasks', title: 'Tasks', blurb: 'What the participant does, in order, while recording.' },
  { id: 'conditions', title: 'Conditions and recruitment', blurb: 'Between-subject arms and the way back to a panel.' },
  { id: 'analysis', title: 'Analysis plan', blurb: 'Decided before the data is seen. Not part of the protocol hash.' },
];

/**
 * Which section a validation reason belongs to. The reasons are the capture
 * page's own refusal text (web/src/study.js); this only routes them, so a
 * reason nobody anticipated still shows, under Basics, rather than vanishing.
 */
export function sectionOf(reason) {
  const r = String(reason);
  if (/disclosure/.test(r)) return 'told';
  if (/^analysis/.test(r)) return 'analysis';
  if (/^task |stimul|^tasks/.test(r)) return 'tasks';
  if (/conditions|arms|recruitment/.test(r)) return 'conditions';
  if (/consent_tier|default_tier|media_plus_transcript|features_in_browser/.test(r)) return 'consent';
  if (/modalit|calibration|^gaze/.test(r)) return 'measures';
  return 'basics';
}

/**
 * The form field a reason is about, as a dotted path ('disclosure.contact'),
 * or null when it is about the study as a whole.
 */
export function fieldOf(reason) {
  const r = String(reason);
  const m = r.match(/\b(disclosure\.[a-z_]+|calibration\.n_points|recruitment\.completion_url|analysis\.(?:aoi_pad_deg|heatmap_sigma_deg))\b/);
  if (m) return m[1];
  if (/^study_id/.test(r)) return 'study_id';
  if (/^no study name/.test(r)) return 'name';
  if (/^no study version/.test(r)) return 'version';
  return null;
}

/** Common exclusion metrics, offered as suggestions — any session column or quality metric works. */
export const METRIC_SUGGESTIONS = ['achieved_fps', 'face_detect_rate', 'gaze_average_offset_deg', 'mean_luminance'];

/** Read a value at a path of keys and indices. */
export function getPath(obj, path) {
  return path.reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

/**
 * Set a value at a path, creating objects on the way. `undefined` DELETES the
 * key — an optional field left empty must be absent, not null or "", because
 * absent fields stay out of the content hash and "" is refused as present
 * but empty.
 */
export function setPath(obj, path, value) {
  let o = obj;
  for (let i = 0; i < path.length - 1; i += 1) {
    if (o[path[i]] == null) o[path[i]] = typeof path[i + 1] === 'number' ? [] : {};
    o = o[path[i]];
  }
  const last = path[path.length - 1];
  if (value === undefined) {
    if (Array.isArray(o)) o.splice(last, 1);
    else delete o[last];
  } else {
    o[last] = value;
  }
  return obj;
}

/** "a, b ,,c" → ["a", "b", "c"]. */
export function parseList(text) {
  return String(text ?? '').split(',').map((s) => s.trim()).filter(Boolean);
}

/** A stimulus id from a file name: the stem, as a slug. */
export function stimulusIdFrom(filename) {
  const stem = String(filename).replace(/\.[^.]+$/, '');
  const slug = stem.replace(/[^A-Za-z0-9_-]+/g, '_').replace(/^[^A-Za-z0-9]+/, '').slice(0, 64);
  return slug || 'stimulus';
}

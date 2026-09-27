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

/** Every task type the capture page knows, with a starting shape. */
export const TASK_TYPES = {
  chinrest: { label: 'Screen distance (bank card + blind spot)', make: () => ({ type: 'chinrest' }) },
  calibration: { label: 'Gaze calibration dots', make: () => ({ type: 'calibration' }) },
  validation: { label: 'Gaze validation dots', make: () => ({ type: 'validation' }) },
  rest_fixation: { label: 'Rest on a cross', make: () => ({ type: 'rest_fixation', duration_ms: 60000 }) },
  read_aloud: { label: 'Read a passage aloud', make: () => ({ type: 'read_aloud', passage: 'default' }) },
  free_speech: { label: 'Talk freely to a prompt', make: () => ({ type: 'free_speech', prompts: 'default' }) },
  expression_prompts: { label: 'Posed facial movements', make: () => ({ type: 'expression_prompts', expressions: 'default', repeats: 2 }) },
  stimuli: { label: 'Pictures and videos', make: () => ({ type: 'stimuli', isi_ms: 1000, items: [] }) },
};

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

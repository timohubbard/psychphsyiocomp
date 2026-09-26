/**
 * Recruitment: who the participant is on a panel, which condition they are in,
 * and where they go when they finish.
 *
 * **Raw panel identifiers never enter the session manifest.** A Prolific ID is
 * a direct identifier — the panel can name the person behind it — and
 * session.json is copied into every table the pipeline writes. So the IDs are
 * kept apart, in `identifiers.json` beside the bundle, and the server
 * replaces them with a keyed pseudonym before anything is written
 * (server/pseudonym.py). The manifest carries only `p_pending`, which says
 * "a pseudonym will be assigned" rather than pretending to be one.
 *
 * **Conditions are assigned here, randomly, and the draw is recorded.** A
 * static page cannot balance arms across participants without a server, so
 * assignment is uniform random from `crypto.getRandomValues`, and the seed and
 * method travel in a `condition_assigned` event so analysis can check the
 * split rather than assume it. A reload keeps the same arm: re-randomising on
 * refresh would let a participant who reloads land in a different condition.
 */

/** The query parameters Prolific appends to a study URL. */
export const PROLIFIC_PARAMS = ['PROLIFIC_PID', 'STUDY_ID', 'SESSION_ID'];

/** The participant_id a manifest carries when a pseudonym is still to come. */
export const PENDING_PARTICIPANT = 'p_pending';

/**
 * The panel identifiers in a URL, or null.
 *
 * Prolific's own parameters win over a generic `?pid=`. Values are kept
 * verbatim: a pseudonym computed from a trimmed or re-cased ID would not match
 * the one computed when the participant later asks to withdraw.
 */
export function panelIdentifiers(search) {
  const q = new URLSearchParams(search ?? '');
  const prolific = q.get('PROLIFIC_PID');
  if (prolific) {
    return {
      platform: 'prolific',
      participant: prolific,
      study: q.get('STUDY_ID') || null,
      session: q.get('SESSION_ID') || null,
    };
  }
  const pid = q.get('pid');
  return pid ? { platform: 'url', participant: pid, study: null, session: null } : null;
}

/** What goes in session.json's participant_id. */
export function manifestParticipantId(ids) {
  return ids ? PENDING_PARTICIPANT : 'anonymous';
}

/**
 * This participant's condition, or null for a study without conditions.
 *
 * `storage` (sessionStorage in the page) keeps the arm across a reload; an
 * arm no longer in the study — it was edited — is discarded and redrawn.
 */
export function assignCondition(study, {
  random = (n) => crypto.getRandomValues(new Uint32Array(n)),
  storage = null,
} = {}) {
  const arms = study?.conditions?.arms;
  if (!Array.isArray(arms) || !arms.length) return null;
  const key = `condition:${study.study_id}:${study.version}`;
  try {
    const kept = JSON.parse(storage?.getItem(key) ?? 'null');
    if (kept && arms.includes(kept.arm)) return { ...kept, reused: true };
  } catch { /* unreadable storage is the same as none */ }

  const seed = random(1)[0] >>> 0;
  const assigned = {
    arm: arms[seed % arms.length], seed, method: 'uniform_random', n_arms: arms.length,
    reused: false,
  };
  try { storage?.setItem(key, JSON.stringify(assigned)); } catch { /* best effort */ }
  return assigned;
}

/**
 * Where to send a participant when their data is safe, or null.
 *
 * Only https (or localhost, for testing): a completion code travels in this
 * URL, and a plain-http link would hand it to anything on the path.
 */
export function completionUrl(study) {
  const url = study?.recruitment?.completion_url;
  return typeof url === 'string' && isSafeCompletionUrl(url) ? url : null;
}

export function isSafeCompletionUrl(url) {
  try {
    const u = new URL(url);
    return u.protocol === 'https:'
      || (u.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(u.hostname));
  } catch {
    return false;
  }
}

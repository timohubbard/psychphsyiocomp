/**
 * Image and video stimuli: load them, prove they are the files the study
 * names, and place them on the stage.
 *
 * Three rules, each a refusal rather than a guess:
 *
 * **Every file is hash-checked before consent.** A study names each stimulus
 * by sha256, and the hash is inside the study's content hash. A file edited on
 * the server after the study was fixed would otherwise put a different picture
 * in front of every later participant while every session still claimed the
 * same protocol. A mismatch is a setup error, shown before anyone consents.
 *
 * **Everything is preloaded into memory.** A stimulus that is still
 * downloading when its turn comes has an onset that is really a network time.
 * Loading all of them first, into object URLs, makes onset a paint time.
 *
 * **Placement is recorded in the gaze estimator's own frame.** Calibration
 * targets are positioned as fractions of the #stage element, so predicted gaze
 * is in stage-normalised coordinates. `rect_norm` is expressed in the same
 * frame, which is what lets an AOI drawn on the image be mapped to where the
 * image actually was on this participant's screen.
 */

/** Every stimulus item a study presents, across all its `stimuli` tasks. */
export function stimulusItems(study) {
  return (study?.tasks ?? [])
    .filter((t) => t.type === 'stimuli')
    .flatMap((t) => t.items ?? []);
}

/** Lower-case hex SHA-256 of bytes. */
export async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Fetch, verify and hold every stimulus. Resolves with a Map from stimulus_id
 * to `{ url, kind, bytes }`; rejects naming the first stimulus that failed.
 */
export async function preloadStimuli(study, { base = '/studies', fetchFn = fetch,
                                              makeUrl = (b) => URL.createObjectURL(b) } = {}) {
  const out = new Map();
  for (const item of stimulusItems(study)) {
    if (out.has(item.stimulus_id)) continue;
    const res = await fetchFn(`${base}/${item.src}`, { cache: 'no-store' });
    if (!res.ok) {
      throw new Error(`stimulus ${item.stimulus_id}: ${base}/${item.src} could not be loaded (HTTP ${res.status})`);
    }
    const buf = await res.arrayBuffer();
    const got = await sha256Hex(buf);
    if (got !== item.sha256) {
      throw new Error(`stimulus ${item.stimulus_id}: ${item.src} does not match the study's sha256 `
        + `(file ${got.slice(0, 12)}…, study ${String(item.sha256).slice(0, 12)}…). The file changed `
        + 'after the study was fixed; sessions run now would not be the protocol they claim.');
    }
    const type = res.headers?.get?.('content-type') ?? '';
    out.set(item.stimulus_id, {
      url: makeUrl(new Blob([buf], { type })), kind: item.kind, bytes: buf.byteLength,
    });
  }
  return out;
}

/**
 * The largest box with the stimulus's aspect ratio that fits in `maxFrac` of
 * the stage, centred. In stage pixels.
 *
 * Never upscaled beyond natural size: a small image blown up to fill the
 * screen is a blurrier, different stimulus.
 */
export function fitRect(naturalW, naturalH, stageW, stageH, maxFrac = 0.8) {
  const scale = Math.min((stageW * maxFrac) / naturalW, (stageH * maxFrac) / naturalH, 1);
  const w = naturalW * scale;
  const h = naturalH * scale;
  return { x: (stageW - w) / 2, y: (stageH - h) / 2, w, h };
}

/** A stage-pixel rect as fractions of the stage — the frame gaze is estimated in. */
export function rectNorm(rect, stageW, stageH) {
  return {
    x0: rect.x / stageW, y0: rect.y / stageH,
    x1: (rect.x + rect.w) / stageW, y1: (rect.y + rect.h) / stageH,
  };
}

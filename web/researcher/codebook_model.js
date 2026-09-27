/**
 * The codebook builder's pure parts: turning what a researcher types or asks
 * for into moments, and the starting shape of a codebook. No DOM and no
 * imports, so it runs under `node --test`. Whether a codebook is valid is NOT
 * decided here: the page asks the server (POST /api/codebooks?check=1), so the
 * rules live once, in server/annotation_store.py.
 *
 * A moment ("item") is milliseconds into a session's recording — the coding
 * page seeks the video to item / 1000 — and the same moments are asked about in
 * every session coded with the codebook. Moments are whole milliseconds, the
 * spelling annotation_store.item_key files labels under.
 */

/** More moments than this in one add is almost certainly a typo in the step. */
export const MAX_ADD = 2000;

/** A new codebook: two categories to define, no moments yet. Not valid as is, on purpose. */
export function blankCodebook() {
  return {
    codebook_id: 'new-codebook',
    name: 'New codebook',
    categories: [
      { id: 'present', label: 'Present', description: '' },
      { id: 'absent', label: 'Absent', description: '' },
    ],
    items: [],
  };
}

/** A category id from its label: a slug, as the store requires. */
export function categoryIdFrom(label, taken = []) {
  const base = String(label ?? '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'category';
  let id = base;
  for (let n = 2; taken.includes(id); n += 1) id = `${base}-${n}`;
  return id;
}

/**
 * Times as people write them → whole milliseconds. Accepts "12" and "12.5"
 * (seconds), "12s", "1500ms", "1:05" and "1:05.5" (minutes:seconds), and
 * "1:02:03" (hours), separated by commas, spaces or new lines. Anything else is
 * returned in `bad` rather than guessed at.
 */
export function parseTimes(text) {
  const ms = [];
  const bad = [];
  for (const raw of String(text ?? '').split(/[\s,;]+/).filter(Boolean)) {
    let v = null;
    let m;
    if ((m = raw.match(/^(\d+(?:\.\d+)?)ms$/i))) v = Number(m[1]);
    else if ((m = raw.match(/^(\d+(?:\.\d+)?)s?$/i))) v = Number(m[1]) * 1000;
    else if ((m = raw.match(/^(\d+):([0-5]?\d(?:\.\d+)?)$/))) v = (Number(m[1]) * 60 + Number(m[2])) * 1000;
    else if ((m = raw.match(/^(\d+):([0-5]\d):([0-5]\d(?:\.\d+)?)$/))) {
      v = (Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3])) * 1000;
    }
    if (v === null || !Number.isFinite(v)) bad.push(raw);
    else ms.push(Math.round(v));
  }
  return { ms, bad };
}

/** Every `everyS` seconds from `fromS` to `toS`, inclusive. */
export function gridTimes(fromS, toS, everyS) {
  const [a, b, step] = [Number(fromS), Number(toS), Number(everyS)];
  if (![a, b, step].every(Number.isFinite) || a < 0 || b < a || step <= 0) {
    throw new Error('need a start, an end after it, and a step above zero');
  }
  const n = Math.floor((b - a) / step + 1e-9) + 1;
  if (n > MAX_ADD) throw new Error(`that is ${n} moments — more than ${MAX_ADD} at once`);
  return Array.from({ length: n }, (_, i) => Math.round((a + i * step) * 1000));
}

/** A small, fast, seedable PRNG (mulberry32): the same seed gives the same moments. */
export function prng(seed) {
  let s = (Number(seed) >>> 0) || 1;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * `n` moments drawn at random between `fromS` and `toS`, at least `gapS` apart,
 * in time order. Random rather than hand-picked, because moments a researcher
 * chooses by eye are the moments where something visibly happens — and a
 * reference standard built from those overstates how well anything does on
 * the rest.
 */
export function sampleTimes(fromS, toS, n, gapS, seed) {
  const [a, b, count, gap] = [Number(fromS), Number(toS), Math.floor(Number(n)), Number(gapS) || 0];
  if (![a, b].every(Number.isFinite) || a < 0 || b <= a) throw new Error('need a start and an end after it');
  if (!(count >= 1) || count > MAX_ADD) throw new Error(`ask for between 1 and ${MAX_ADD} moments`);
  if (gap < 0) throw new Error('the gap cannot be negative');
  if ((count - 1) * gap > b - a) throw new Error(`${count} moments ${gap} s apart do not fit between ${a} and ${b} s`);
  // Place count points in the span left after reserving the gaps, then add the
  // gaps back: uniform, and the spacing holds by construction.
  const rand = prng(seed);
  const free = b - a - (count - 1) * gap;
  const u = Array.from({ length: count }, () => rand() * free).sort((x, y) => x - y);
  return u.map((x, i) => Math.round((a + x + i * gap) * 1000));
}

/** A seeded shuffle (Fisher–Yates), so an order can be reproduced from its seed. */
export function shuffle(items, seed) {
  const out = [...items];
  const rand = prng(seed);
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** Append new moments, keeping the existing order and dropping repeats. */
export function mergeItems(items, add) {
  const seen = new Set(items);
  const out = [...items];
  let repeats = 0;
  for (const t of add) {
    if (seen.has(t)) { repeats += 1; continue; }
    seen.add(t);
    out.push(t);
  }
  return { items: out, repeats };
}

/** 65000 → "1:05", 65500 → "1:05.5", 3723000 → "1:02:03". */
export function fmtTime(ms) {
  const total = Math.round(Number(ms)) / 1000;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = Number((total % 60).toFixed(3));
  const sec = `${s < 10 ? '0' : ''}${s}`;
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`;
}

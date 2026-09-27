/**
 * The cohort page: who is in, why the rest are out, the mean epoch curves,
 * and heatmaps — the same numbers `npm run cohort` prints and `npm run export`
 * writes, from /api/studies/<id>/cohort. Read-only.
 */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function api(path) {
  const res = await fetch(path, { cache: 'no-store' });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ?? body.error ?? res.status);
  return body;
}

/** Each step as a bar of how many remain, with the sessions it removed and why. */
function funnelHtml(funnel) {
  const first = Math.max(funnel[0]?.remaining ?? 0, 1);
  return `<div class="funnel">${funnel.map((s) => `
    <div class="fstep${s.excluded.length ? ' cut' : ''}"><div class="n">${s.remaining}</div><div>
      <div class="lbl">${esc(s.step)}</div>
      <div class="bar"><i style="width:${(100 * s.remaining) / first}%"></i></div>
      ${s.excluded.map((e) => `<div class="out">− <a href="./index.html?session=${encodeURIComponent(e.session_id)}">${esc(e.session_id)}</a>
        <span>${esc(e.reason)}</span></div>`).join('')}
    </div></div>`).join('')}</div>`;
}

/** A tick label that never reads "-0.000". */
function tick(v) {
  if (v === 0) return '0';
  const s = Math.abs(v) >= 1 ? v.toFixed(2) : v.toPrecision(2);
  return Number(s) === 0 ? '0' : s;
}

/** One channel's mean baseline-corrected curve, as a small SVG line chart. */
function curveSvg(points, w = 320, h = 150) {
  if (!points.length) return '<div class="note">no epochs</div>';
  const xs = points.map((p) => p.t_ms);
  const ys = points.map((p) => p.mean);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const lo = Math.min(0, ...ys);
  const hi = Math.max(0, ...ys);
  // Room at the left for the value ticks and at the foot for the time ticks.
  const [L, R, T, B] = [44, 10, 8, 22];
  const sx = (x) => ((x - x0) / (x1 - x0 || 1)) * (w - L - R) + L;
  const sy = (y) => h - B - ((y - lo) / (hi - lo || 1)) * (h - T - B);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.t_ms).toFixed(1)},${sy(p.mean).toFixed(1)}`).join('');
  return `<svg width="100%" viewBox="0 0 ${w} ${h}">
    <line x1="${L}" x2="${w - R}" y1="${sy(0)}" y2="${sy(0)}" stroke="#3a404a" />
    <line x1="${sx(0)}" x2="${sx(0)}" y1="${T}" y2="${h - B}" stroke="#5a6170" stroke-dasharray="3,3" />
    <path class="curve" d="${d}" fill="none" stroke="#4c8dff" stroke-width="1.6" />
    <text x="${L - 6}" y="${T + 8}" fill="#9aa0a6" font-size="10" text-anchor="end">${tick(hi)}</text>
    <text x="${L - 6}" y="${sy(0) + 3}" fill="#9aa0a6" font-size="10" text-anchor="end">0</text>
    <text x="${L - 6}" y="${h - B}" fill="#9aa0a6" font-size="10" text-anchor="end">${tick(lo)}</text>
    <text x="${L}" y="${h - 6}" fill="#9aa0a6" font-size="10">${Math.round(x0)} ms</text>
    <text x="${sx(0) + 4}" y="${T + 8}" fill="#c7cbd1" font-size="10">event</text>
    <text x="${w - R}" y="${h - 6}" fill="#9aa0a6" font-size="10" text-anchor="end">+${Math.round(x1)} ms</text>
  </svg>`;
}

/**
 * A density grid onto a canvas, inferno-ish ramp. Transparent where nobody
 * looked, so the picture underneath shows through; the grid is in the
 * picture's own frame, so stretching it over the picture is exact.
 */
function drawHeatmap(canvas, grid) {
  const h = grid.length;
  const w = grid[0].length;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(w, h);
  const max = Math.max(...grid.flat()) || 1;
  grid.forEach((row, y) => row.forEach((v, x) => {
    const t = v / max;
    const i = (y * w + x) * 4;
    img.data[i] = Math.round(255 * Math.min(1, t * 1.8));
    img.data[i + 1] = Math.round(255 * Math.max(0, t - 0.45) * 1.6);
    img.data[i + 2] = Math.round(120 * (1 - t) * t * 4);
    img.data[i + 3] = Math.round(255 * Math.min(1, t * 1.6) * 0.85);
  }));
  ctx.putImageData(img, 0, 0);
}

async function render() {
  const id = $('study').value;
  if (!id) return;
  const q = `include_developer=${$('dev').checked ? 1 : 0}&allow_mixed=${$('mixed').checked ? 1 : 0}`;
  $('main').innerHTML = '<div class="note">computing…</div>';
  let c;
  try {
    c = await api(`/api/studies/${encodeURIComponent(id)}/cohort?${q}`);
  } catch (err) {
    $('main').innerHTML = `<div class="note bad">${esc(err.message)}</div>`;
    return;
  }
  const epochs = c.epochs.flatMap((e) => Object.entries(e.curves).map(([ch, pts]) => `
    <div class="panel"><div class="t">${esc(ch)}</div><div class="m">${esc(e.name)} · around each ${esc(e.event_type)} ·
      ${e.n_epochs} epoch${e.n_epochs === 1 ? '' : 's'}${e.refusals ? `, <span class="warn">${e.refusals} refused</span>` : ''}</div>
      ${curveSvg(pts)}</div>`));
  const heat = c.heatmaps.map((hm, i) => `
    <div class="panel"><div class="t">${esc(hm.stimulus_id)}</div><div class="m">${hm.participants} participant${
      hm.participants === 1 ? '' : 's'} · blur σ ${hm.sigma_deg}°${hm.kind === 'image' ? '' : ' · a video, drawn without its frames'}${hm.refused ? ` · <span class="warn">${hm.refused} refused</span>` : ''}</div>
      ${hm.grid ? `<div class="heat${hm.kind === 'image' ? '' : ' video'}">${hm.kind === 'image' && hm.src
        ? `<img src="/${esc(hm.src)}" alt="">` : ''}<canvas data-i="${i}"></canvas></div>`
        : '<div class="note">No gaze on this stimulus.</div>'}</div>`);
  const recorded = c.funnel[0]?.remaining ?? 0;
  const included = c.funnel.at(-1)?.remaining ?? 0;
  const stat = (k, v, cls = '') => `<div class="stat ${cls}"><div class="k">${k}</div><div class="v">${v}</div></div>`;
  $('main').innerHTML = `
    <div class="hash">protocol ${esc(c.content_hash)} · analysis ${esc(c.analysis_hash)}
      ${c.include_developer ? ' · <span class="warn">self-tests included</span>' : ''}</div>
    <div class="stats">${stat('Sessions found', recorded)}${stat('Included', included, included ? 'ok' : '')}
      ${stat('Excluded', recorded - included, recorded - included ? 'bad' : '')}
      ${stat('Epoch sets', c.epochs.length)}${stat('Stimuli', c.heatmaps.length)}</div>
    <h2>Who is in</h2><div class="sub">Each step in order, with how many remain and whom it removed.</div>${funnelHtml(c.funnel)}
    <h2>Epochs — mean change from baseline</h2>
    ${epochs.length ? `<div class="grid">${epochs.join('')}</div>` : '<div class="note">The study declares no epochs (analysis.epochs).</div>'}
    <h2>Heatmaps</h2>
    ${heat.length ? `<div class="ramp">less looking <i></i> more · each participant weighs the same</div><div class="grid">${heat.join('')}</div>`
      : '<div class="note">The study shows no stimuli.</div>'}`;
  document.querySelectorAll('canvas[data-i]').forEach((cv) => drawHeatmap(cv, c.heatmaps[cv.dataset.i].grid));
}

async function init() {
  const { studies } = await api('/api/studies');
  const valid = studies.filter((s) => s.valid);
  $('study').innerHTML = valid.map((s) => `<option value="${esc(s.study_id)}">${esc(s.study_id)}</option>`).join('');
  const wanted = new URLSearchParams(location.search).get('study');
  if (wanted) $('study').value = wanted;
  $('dev').checked = new URLSearchParams(location.search).get('dev') === '1';
  for (const el of ['study', 'dev', 'mixed']) $(el).addEventListener('change', render);
  render();
}

init();

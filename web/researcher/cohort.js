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

function funnelTable(funnel) {
  return `<table><tr><th>remaining</th><th>step</th><th>excluded here</th></tr>${funnel.map((s) => `
    <tr><td class="n">${s.remaining}</td><td>${esc(s.step)}</td>
    <td class="why">${s.excluded.map((e) => `${esc(e.session_id)} — ${esc(e.reason)}`).join('<br>')}</td></tr>`).join('')}
  </table>`;
}

/** One channel's mean baseline-corrected curve, as a small SVG line chart. */
function curveSvg(points, w = 320, h = 140) {
  if (!points.length) return '<div class="note">no epochs</div>';
  const xs = points.map((p) => p.t_ms);
  const ys = points.map((p) => p.mean);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const lo = Math.min(0, ...ys);
  const hi = Math.max(0, ...ys);
  const sx = (x) => ((x - x0) / (x1 - x0 || 1)) * (w - 20) + 10;
  const sy = (y) => h - 10 - ((y - lo) / (hi - lo || 1)) * (h - 20);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${sx(p.t_ms).toFixed(1)},${sy(p.mean).toFixed(1)}`).join('');
  return `<svg width="100%" viewBox="0 0 ${w} ${h}">
    <line x1="10" x2="${w - 10}" y1="${sy(0)}" y2="${sy(0)}" stroke="#333" />
    <line x1="${sx(0)}" x2="${sx(0)}" y1="10" y2="${h - 10}" stroke="#555" stroke-dasharray="3,3" />
    <path class="curve" d="${d}" fill="none" stroke="#4c8dff" stroke-width="1.6" />
    <text x="12" y="16" fill="#9aa0a6" font-size="10">${hi.toFixed(3)}</text>
    <text x="12" y="${h - 12}" fill="#9aa0a6" font-size="10">${lo.toFixed(3)}</text>
  </svg>`;
}

/** A density grid onto a canvas, inferno-ish ramp. */
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
    img.data[i + 3] = 255;
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
    $('main').innerHTML = `<div class="note warn">${esc(err.message)}</div>`;
    return;
  }
  const epochs = c.epochs.flatMap((e) => Object.entries(e.curves).map(([ch, pts]) => `
    <div class="panel"><div class="t">${esc(e.name)} · ${esc(ch)} · ${e.n_epochs} epoch(s)${
      e.refusals ? `, <span class="warn">${e.refusals} refused</span>` : ''}</div>${curveSvg(pts)}</div>`));
  const heat = c.heatmaps.map((hm, i) => `
    <div class="panel"><div class="t">${esc(hm.stimulus_id)} · ${hm.participants} participant(s), σ ${hm.sigma_deg}°${
      hm.refused ? `, <span class="warn">${hm.refused} refused</span>` : ''}</div>
      ${hm.grid ? `<canvas data-i="${i}"></canvas>` : '<div class="note">no gaze on this stimulus</div>'}</div>`);
  $('main').innerHTML = `
    <div class="hash">protocol ${esc(c.content_hash)} · analysis ${esc(c.analysis_hash)}
      ${c.include_developer ? ' · <span class="warn">self-tests included</span>' : ''}</div>
    <h2>Who is in</h2>${funnelTable(c.funnel)}
    <h2>Epochs — mean change from baseline</h2>
    ${epochs.length ? `<div class="grid">${epochs.join('')}</div>` : '<div class="note">The study declares no epochs (analysis.epochs).</div>'}
    <h2>Heatmaps</h2>
    ${heat.length ? `<div class="grid">${heat.join('')}</div>` : '<div class="note">The study shows no stimuli.</div>'}`;
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

/**
 * Researcher UI.
 *
 * Presentation only. Every threshold it colours by is one the evidence base
 * actually states, and where the evidence base states none — gaze accuracy, per
 * §5.3 — nothing is coloured and the number is shown beside its context instead.
 * Inventing a green/red boundary here would quietly become the project's
 * inclusion criterion without anyone preregistering it.
 */

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

/** §5.3: 5 Hz was applied as an exclusion threshold in a published study. */
const MIN_HZ = 5;
/** §2.5: the rPPG skin-tone accuracy gap largely closes above this luminance. */
const MIN_LUMA = 30;
/** §4.2: webcam AOIs need padding to a 3-4.5 degree error budget. */
const AOI_BUDGET_DEG = 4.5;

let sessions = [];
let active = null;

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${r.status} ${(await r.json()).detail ?? ''}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// session list
// ---------------------------------------------------------------------------

async function loadList() {
  const { sessions: rows } = await api('/api/sessions');
  sessions = rows;
  $('sub').textContent = `${rows.length} processed`;

  if (!rows.length) {
    $('list').innerHTML = '<div class="empty">No sessions</div>';
    $('detail').innerHTML = `<div class="note">Process a capture bundle first:<br>
      <code>npm run py -- server/process_bundle.py &lt;dir&gt; --out out/</code></div>`;
    return;
  }

  $('list').innerHTML = rows.map(sessionRow).join('');
  [...document.querySelectorAll('.sess')].forEach((el) => {
    el.addEventListener('click', () => select(el.dataset.id));
  });
  select(rows[0].session_id);
}

function sessionRow(s) {
  const pills = [];

  // Alignment first: unaligned rows cannot be compared against anything, so it
  // is the fact that decides whether the rest of the row means anything.
  if (s.aligned === 1) pills.push(pill('aligned', 'ok'));
  else if (s.aligned === null) pills.push(pill('no signals', 'bad'));
  else pills.push(pill(`${(s.aligned * 100).toFixed(0)}% aligned`, 'bad'));

  if (s.geometry_method === 'virtual_chinrest') {
    pills.push(pill(`${fmt(s.viewing_distance_mm / 10, 0)}±${fmt(s.geometry_error_mm / 10, 0)}cm`));
  } else {
    pills.push(pill(s.geometry_refusal_reason || 'no geometry', 'warn'));
  }

  if (s.gaze_average_offset_deg != null) pills.push(pill(`gaze ${fmt(s.gaze_average_offset_deg)}°`));
  else if (s.gaze_average_offset_px != null) pills.push(pill(`gaze ${fmt(s.gaze_average_offset_px, 0)}px`));

  if (s.achieved_fps != null) {
    pills.push(pill(`${fmt(s.achieved_fps, 1)} fps`, s.achieved_fps >= MIN_HZ ? '' : 'bad'));
  }

  return `<div class="sess" data-id="${s.session_id}">
    <div class="id">${s.session_id}</div>
    <div class="meta">${s.participant_id ?? '—'} · ${s.study_id ?? '—'} ·
      ${s.duration_s ? `${Math.round(s.duration_s)}s` : '—'} ·
      ${s.n_sources} source${s.n_sources === 1 ? '' : 's'}</div>
    <div class="pills">${pills.join('')}</div>
  </div>`;
}

const pill = (text, cls = '') => `<span class="pill ${cls}">${text}</span>`;

function select(id) {
  active = id;
  [...document.querySelectorAll('.sess')].forEach(
    (el) => el.classList.toggle('active', el.dataset.id === id));
  loadDetail(id);
}

// ---------------------------------------------------------------------------
// session detail
// ---------------------------------------------------------------------------

async function loadDetail(id) {
  $('detail').innerHTML = '<div class="empty">loading…</div>';
  const d = await api(`/api/sessions/${encodeURIComponent(id)}`);
  const m = d.meta ?? {};
  const sm = d.session_metrics ?? {};

  const cards = [];

  cards.push(card('Aligned', d.aligned === null ? '—' : `${(d.aligned * 100).toFixed(1)}%`,
    d.aligned === 1 ? 'every row on the master clock' : 'some rows could not be anchored',
    d.aligned === 1 ? 'ok' : 'bad'));

  cards.push(card('Duration', d.duration_s ? `${Math.round(d.duration_s)}s` : '—', ''));

  if (m.geometry_method === 'virtual_chinrest') {
    cards.push(card('Viewing distance', `${fmt(m.viewing_distance_mm / 10, 1)}cm`,
      `±${fmt(m.geometry_error_mm / 10, 1)}cm accuracy · ±${fmt(m.geometry_precision_mm, 0)}mm precision`));
  } else {
    cards.push(card('Viewing distance', 'refused',
      m.geometry_refusal_reason ?? 'not attempted', 'warn'));
  }

  cards.push(card('Capture rate', m.achieved_fps ? `${fmt(m.achieved_fps, 1)} Hz` : '—',
    `§5.3 exclusion threshold ${MIN_HZ} Hz`,
    m.achieved_fps == null ? '' : (m.achieved_fps >= MIN_HZ ? 'ok' : 'bad')));

  if (sm.gaze_average_offset_deg != null || sm.gaze_average_offset_px != null) {
    // Deliberately uncoloured. §5.3 records that jsPsych publishes no pass/fail
    // cutoff for gaze accuracy and every inclusion criterion is the
    // researcher's to preregister — so the figure is shown against §4.2's AOI
    // budget as context, not graded against a threshold invented here.
    const deg = sm.gaze_average_offset_deg;
    cards.push(card('Gaze error',
      deg != null ? `${fmt(deg)}°` : `${fmt(sm.gaze_average_offset_px, 0)}px`,
      deg != null ? `§4.2 AOI budget is 3–4.5°` : 'no geometry — px only'));
    cards.push(card('Within ROI', `${((sm.gaze_percent_in_roi ?? 0) * 100).toFixed(0)}%`,
      `${sm.gaze_validation_targets ?? 0} held-out targets`));

    // The coverage figure belongs beside the accuracy figure, because accuracy
    // is measured only where the model interpolates. Off-screen predictions are
    // it extrapolating past anything it was calibrated on, and reporting one
    // without the other overstates what the estimate covers.
    if (sm.gaze_onscreen_rate != null) {
      const pct = sm.gaze_onscreen_rate * 100;
      cards.push(card('On screen', `${pct.toFixed(0)}%`,
        'the rest is the model extrapolating',
        pct >= 90 ? 'ok' : pct >= 70 ? 'warn' : 'bad'));
    }
    if (sm.gaze_n_fixations != null) {
      cards.push(card('Fixations', `${sm.gaze_n_fixations}`,
        `median ${Math.round(sm.gaze_median_fixation_ms ?? 0)}ms · HMM, not I-VT`));
    }
  } else if (sm.gaze_fit_refused) {
    cards.push(card('Gaze', 'refused',
      `${sm.gaze_calibration_targets ?? 0} usable calibration targets`, 'warn'));
  }

  cards.push(protocolCard(d.study_check));

  const luma = lastQuality(d.quality, 'mean_luminance');
  if (luma != null) {
    cards.push(card('Luminance', fmt(luma, 0),
      `§2.5 fairness floor ${MIN_LUMA}`, luma >= MIN_LUMA ? 'ok' : 'warn'));
  }

  $('detail').innerHTML = `
    <h2>${d.session_id}</h2>
    <div class="cards">${cards.join('')}</div>

    ${sm.gaze_average_offset_deg != null ? `<div class="note">
      Gaze error is measured on validation targets the model was never fitted on,
      and those sit between the calibration points by design. There is no
      pass/fail threshold here on purpose: §5.3 records that none is published,
      so the inclusion criterion is yours to preregister.</div>` : ''}

    ${sm.gaze_onscreen_rate != null && sm.gaze_onscreen_rate < 0.9 ? `<div class="note">
      <strong>${((1 - sm.gaze_onscreen_rate) * 100).toFixed(0)}% of predicted gaze
      falls outside the screen.</strong> Those samples are the ridge model being
      asked about feature values it never saw during calibration, and quadratic
      terms diverge quickly outside their fitted range. The accuracy figure above
      does not describe them — it is measured on targets where the features are
      in range. Fixations are classified on the on-screen samples only.</div>` : ''}

    ${sm.gaze_n_fixations != null ? `<div class="note">
      Fixations come from a two-state HMM over angular velocity, not I-VT or
      I-DT. §4.1: threshold detectors reach ~90–92% on static stimuli but
      ~68–70% under real head movement at the same 30 Hz, which is the regime a
      webcam pipeline lives in. Counts and durations are algorithm-dependent, so
      the detector travels with them.</div>` : ''}

    ${protocolNote(d.study_check)}

    ${voicePanel(d.engine_quality)}
    ${transcriptPanel(d.engine_quality)}
    ${respirationPanel(d.engine_quality)}

    <h2>Engine runs</h2>
    ${runsTable(d.runs)}

    <h2>Quality over time</h2>
    ${qualityCharts(d.quality)}

    <h2>Channels <span class="pill">${d.channels.length}</span></h2>
    <div class="scroll">${channelTable(d.channels)}</div>

    <h2>Events <span class="pill">${d.events.length}</span></h2>
    <div class="scroll">${eventsTable(d.events)}</div>

    <div id="agreement"></div>
    <div id="scanpath"></div>
    <div id="aoi"></div>
    <div id="plot"></div>`;

  [...document.querySelectorAll('tr.clickable')].forEach((tr) => {
    tr.addEventListener('click', () => plotChannel(id, tr.dataset.channel, tr.dataset.source));
  });

  showAgreement(id).catch(() => {});

  if (sm.gaze_n_fixations) {
    showScanpath(id).catch(() => {});
    // Padding is specified in degrees, so the editor needs this session's own
    // geometry to draw the padded outline at the size it actually tests against.
    if (m.px_per_mm && m.viewing_distance_mm) {
      aoiState.dpp = Math.atan2(1 / m.px_per_mm, m.viewing_distance_mm) * 180 / Math.PI;
    }
    showAoi(id).catch(() => {});
  }
}

function card(k, v, note, cls = '') {
  return `<div class="card ${cls}"><div class="k">${k}</div>
    <div class="v">${v}</div>${note ? `<div class="n">${note}</div>` : ''}</div>`;
}

function lastQuality(rows, metric) {
  const hits = rows.filter((r) => r.metric === metric);
  return hits.length ? hits[hits.length - 1].value : null;
}

function runsTable(runs) {
  if (!runs.length) return '<div class="note">No engine runs recorded.</div>';
  return `<table><thead><tr>
    <th>engine</th><th>status</th><th>licence</th><th>clock ±</th><th>note</th>
  </tr></thead><tbody>${runs.map((r) => `<tr>
    <td>${r.engine_id}@${r.version}</td>
    <td class="${r.status === 'ok' ? 'tier-high' : 'tier-low'}">${r.status}</td>
    <td class="txt">${r.license_spdx ?? '—'}${
      r.license_commercial_use === 'no' ? ' <span class="pill warn">non-commercial</span>' : ''}</td>
    <td>${r.clock_uncertainty_ms != null ? `${fmt(r.clock_uncertainty_ms, 0)}ms` : '—'}</td>
    <td class="txt">${r.unaligned_reason ?? r.ineligible_reasons ?? ''}</td>
  </tr>`).join('')}</tbody></table>`;
}

function channelTable(channels) {
  return `<table><thead><tr>
    <th>channel</th><th>source</th><th>tier</th><th>n</th><th>mean</th><th>min</th><th>max</th>
  </tr></thead><tbody>${channels.map((c) => `<tr class="clickable"
      data-channel="${c.channel}" data-source="${c.source}">
    <td>${c.channel}</td>
    <td class="txt">${c.source.replace(/@.*\+/, '+')}</td>
    <td class="tier-${c.reliability_tier}">${c.reliability_tier}</td>
    <td>${c.n}</td><td>${fmt(c.mean, 3)}</td>
    <td>${fmt(c.min, 3)}</td><td>${fmt(c.max, 3)}</td>
  </tr>`).join('')}</tbody></table>`;
}

function eventsTable(events) {
  const counts = new Map();
  for (const e of events) counts.set(e.event_type, (counts.get(e.event_type) ?? 0) + 1);
  return `<table><thead><tr><th>event</th><th>count</th><th>first onset</th></tr></thead>
    <tbody>${[...counts].map(([type, n]) => {
      const first = events.find((e) => e.event_type === type);
      return `<tr><td>${type}</td><td>${n}</td>
        <td>${first?.onset != null ? `${(first.onset / 1000).toFixed(1)}s` : '—'}</td></tr>`;
    }).join('')}</tbody></table>`;
}

// ---------------------------------------------------------------------------
// charts — inline SVG, no dependencies
// ---------------------------------------------------------------------------

function qualityCharts(rows) {
  // One chart per (metric, source), not per metric. Three engines emit
  // `mean_luminance` over the same video, and grouping by name alone drew a
  // single line whose consecutive points came from different engines — a trace
  // that looks like one measurement wobbling and is actually two disagreeing.
  // They happened to agree closely here, which is exactly why it went unnoticed.
  const seen = new Map();
  for (const r of rows) {
    // Keyed on a Map rather than a joined string, so no separator has to be a
    // character a metric or source is assumed never to contain.
    const k = JSON.stringify([r.metric, r.source]);
    if (!seen.has(k)) seen.set(k, [r.metric, r.source]);
  }
  if (!seen.size) return '<div class="note">No windowed quality metrics.</div>';

  const charts = [...seen.values()].map(([metric, source]) => {
    const pts = rows.filter((r) => r.metric === metric && r.source === source && r.t != null)
      .map((r) => [r.t, r.value]).sort((a, b) => a[0] - b[0]);
    // A once-per-run metric is a number, not a trace; the modality panels and
    // the cards above already carry those.
    if (pts.length < 2) return '';
    const floor = metric === 'achieved_fps' ? MIN_HZ
      : metric === 'mean_luminance' ? MIN_LUMA : null;
    return `<div class="card" style="margin-bottom:10px">
      <div class="k">${metric} <span class="src">${source}</span></div>
      ${sparkline(pts, floor)}</div>`;
  }).filter(Boolean);

  return charts.length ? charts.join('')
    : '<div class="note">No quality metric has more than one window.</div>';
}

/**
 * A line, optionally with an evidenced threshold drawn across it.
 *
 * The threshold line is what makes the chart readable at a glance — a frame
 * rate of 12 means nothing without knowing that 5 is the documented exclusion
 * point — so it is drawn only where such a number actually exists.
 */
function sparkline(points, floor = null, w = 620, h = 70) {
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = Math.min(...ys), y1 = Math.max(...ys);
  if (floor != null) { y0 = Math.min(y0, floor); y1 = Math.max(y1, floor); }
  if (y1 - y0 < 1e-9) { y1 = y0 + 1; }

  const px = (x) => ((x - x0) / (x1 - x0 || 1)) * (w - 8) + 4;
  const py = (y) => h - 8 - ((y - y0) / (y1 - y0)) * (h - 16);
  const d = points.map((p, i) => `${i ? 'L' : 'M'}${px(p[0]).toFixed(1)},${py(p[1]).toFixed(1)}`).join('');

  const breach = floor != null && ys.some((y) => y < floor);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" style="margin-top:6px">
    ${floor != null ? `<line x1="4" x2="${w - 4}" y1="${py(floor)}" y2="${py(floor)}"
      stroke="${breach ? '#d9534f' : '#3a4048'}" stroke-dasharray="3 3" stroke-width="1"/>
      <text x="${w - 6}" y="${py(floor) - 4}" fill="#9aa0a6" font-size="10"
        text-anchor="end">${floor}</text>` : ''}
    <path d="${d}" fill="none" stroke="${breach ? '#d9534f' : '#4c8dff'}" stroke-width="1.5"/>
    <text x="4" y="12" fill="#9aa0a6" font-size="10">${ys[ys.length - 1].toFixed(1)}</text>
  </svg>`;
}

async function plotChannel(sessionId, channel, source) {
  const s = await api(`/api/sessions/${encodeURIComponent(sessionId)}/series`
    + `?channel=${encodeURIComponent(channel)}&source=${encodeURIComponent(source)}`);

  const href = `/api/sessions/${encodeURIComponent(sessionId)}/export`
    + `?channel=${encodeURIComponent(channel)}&source=${encodeURIComponent(source)}`;

  $('plot').innerHTML = `
    <h2>${channel}</h2>
    <div class="card">
      <div class="k">${source}</div>
      ${s.points.length > 1 ? sparkline(s.points, null, 900, 160)
        : '<div class="empty">not enough points</div>'}
      <div class="n">${s.n_total.toLocaleString()} samples${
        s.stride > 1 ? `, showing every ${s.stride}${ordinal(s.stride)}` : ''}</div>
      <p style="margin:12px 0 0"><a href="${href}"><button>Export CSV</button></a></p>
    </div>`;
  $('plot').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

const ordinal = (n) => (n % 10 === 1 && n % 100 !== 11 ? 'st'
  : n % 10 === 2 && n % 100 !== 12 ? 'nd'
    : n % 10 === 3 && n % 100 !== 13 ? 'rd' : 'th');

loadList().catch((e) => {
  $('detail').innerHTML = `<div class="note">Failed to load: ${e.message}</div>`;
});

// ---------------------------------------------------------------------------
// scanpath
// ---------------------------------------------------------------------------

/**
 * The canonical eye-tracking picture: fixations as circles sized by duration,
 * numbered in order, joined by saccades.
 *
 * Drawn from the recorded events rather than recomputed from samples. §4.1
 * warns fixation counts and durations are algorithm-dependent, so a viewer that
 * re-derived them would be showing a different session from the one the metrics
 * on this page describe.
 *
 * The stimulus targets are drawn underneath, because a reader should be able to
 * see for themselves whether the fixations went where the participant was told
 * to look — rather than taking the hit rate on trust.
 */
async function loadScanpath(sessionId, window = null) {
  const q = window ? `?start=${window[0]}&end=${window[1]}` : '';
  const sp = await api(`/api/sessions/${encodeURIComponent(sessionId)}/scanpath${q}`);
  return sp;
}

function scanpathSvg(sp, { w = 900, aspect = 1067 / 1707 } = {}) {
  const h = Math.round(w * aspect);
  const X = (x) => x * w;
  const Y = (y) => y * h;

  if (!sp.fixations.length) {
    return '<div class="empty">No fixations recorded</div>';
  }

  // Radius by duration, on a square-root scale so area tracks time rather than
  // radius — a 4x longer fixation should look 4x bigger, not 16x.
  const durs = sp.fixations.map((f) => f.duration_ms);
  const maxDur = Math.max(...durs);
  const r = (d) => 4 + 22 * Math.sqrt(d / maxDur);

  const targets = sp.stimuli.map((s) => `
    <circle cx="${X(s.x)}" cy="${Y(s.y)}" r="7" fill="none"
      stroke="${s.kind === 'validation_point' ? '#e0a800' : '#5cb85c'}"
      stroke-width="1.5" stroke-dasharray="2 2"/>`).join('');

  const path = sp.fixations.map((f, i) =>
    `${i ? 'L' : 'M'}${X(f.x).toFixed(1)},${Y(f.y).toFixed(1)}`).join('');

  const dots = sp.fixations.map((f, i) => `
    <circle cx="${X(f.x)}" cy="${Y(f.y)}" r="${r(f.duration_ms).toFixed(1)}"
      fill="rgba(76,141,255,.22)" stroke="#4c8dff" stroke-width="1">
      <title>#${i + 1} · ${Math.round(f.duration_ms)}ms · ${f.n_samples} samples</title>
    </circle>`).join('');

  // Only number the longer fixations; labelling all 80 is unreadable and the
  // short ones are the ones a reader is least interested in following.
  const labelled = sp.fixations
    .map((f, i) => ({ f, i }))
    .filter(({ f }) => f.duration_ms > maxDur * 0.15)
    .map(({ f, i }) => `<text x="${X(f.x)}" y="${Y(f.y) + 4}" fill="#cfd4da"
      font-size="11" text-anchor="middle">${i + 1}</text>`).join('');

  return `
    <svg viewBox="0 0 ${w} ${h}" width="100%" style="background:#7f7f7f;border-radius:8px">
      <rect x="0" y="0" width="${w}" height="${h}" fill="none" stroke="#5a5a5a"/>
      ${targets}
      <path d="${path}" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1"/>
      ${dots}${labelled}
    </svg>`;
}

async function showScanpath(sessionId, window = null, phaseKey = null) {
  const host = $('scanpath');
  if (!host) return;
  host.innerHTML = '<div class="empty">loading…</div>';

  const sp = await loadScanpath(sessionId, window);
  const durs = sp.fixations.map((f) => f.duration_ms).sort((a, b) => a - b);
  const median = durs.length ? durs[durs.length >> 1] : 0;

  // One button per contiguous viewing block. Drawing the whole session at once
  // overlays the calibration grid, the instruction screens and a minute of
  // staring at a cross — all real gaze, and together an unreadable tangle that
  // hides the structure rather than showing it.
  const tabs = [{ key: null, label: 'Whole session', duration_s: null },
                ...(sp.phases ?? [])]
    .map((p) => `<button data-phase="${p.key ?? ''}"
      data-start="${p.start ?? ''}" data-end="${p.end ?? ''}"
      style="${(p.key ?? null) === phaseKey ? 'border-color:var(--accent);color:var(--accent)' : ''}">
      ${p.label}${p.duration_s ? ` · ${p.duration_s}s` : ''}</button>`).join(' ');

  host.innerHTML = `
    <h2>Scanpath</h2>
    <p style="display:flex;gap:8px;flex-wrap:wrap;margin:0 0 12px">${tabs}</p>
    <div class="card">
      ${scanpathSvg(sp)}
      <div class="n" style="margin-top:8px">
        ${sp.fixations.length} fixations (circle area ∝ duration, median
        ${Math.round(median)}ms) · ${sp.saccades.length} saccades ·
        dashed rings are the calibration
        <span style="color:var(--ok)">■</span> and validation
        <span style="color:var(--warn)">■</span> targets that were on screen.
        Drawn from recorded events, not recomputed.
      </div>
    </div>`;

  [...host.querySelectorAll('button[data-phase]')].forEach((b) => {
    b.addEventListener('click', () => {
      const key = b.dataset.phase || null;
      const win = b.dataset.start ? [Number(b.dataset.start), Number(b.dataset.end)] : null;
      showScanpath(sessionId, win, key).catch(() => {});
    });
  });
}

// ---------------------------------------------------------------------------
// AOI editor
//
// Drawn directly on the scanpath, because an AOI is a claim about where gaze
// went and the only way to judge it is to see both at once. §4.2 found hit
// rates moving 77% -> 88% -> 93% purely from refining the same boundaries on
// the same data, so the editor shows the PADDED outline as well as the drawn
// one — the padding is what a fixation is actually tested against, and it is
// usually far larger than people expect.
// ---------------------------------------------------------------------------

const aoiState = { list: [], armed: false, setName: '', pad: 4.5, fixations: [], dpp: 0.0236 };

async function showAoi(sessionId) {
  const host = $('aoi');
  if (!host) return;

  const [{ sets }, sp] = await Promise.all([
    api('/api/aoi-sets'),
    loadScanpath(sessionId),
  ]);
  aoiState.fixations = sp.fixations;

  const options = sets.map((s) =>
    `<option value="${s.name}">${s.name} · v${s.version} · ${s.n_aois} AOIs</option>`).join('');

  host.innerHTML = `
    <h2>Areas of interest</h2>
    <p class="aoi-bar">
      <select id="aoiSet">
        <option value="">— new set —</option>${options}
      </select>
      <button id="aoiDraw">Draw rectangle</button>
      <button id="aoiClear">Clear</button>
      <label>pad <input id="aoiPad" type="number" step="0.5" min="0" max="15"
        value="${aoiState.pad}">°</label>
      <button id="aoiSave">Save set</button>
      <span id="aoiMsg"></span>
    </p>
    <div class="card">
      <div id="aoiCanvas"></div>
      <div class="n" id="aoiCaption" style="margin-top:8px"></div>
    </div>
    <div id="aoiMetrics"></div>`;

  $('aoiDraw').addEventListener('click', () => {
    aoiState.armed = true;
    $('aoiMsg').textContent = 'drag on the image to draw';
  });
  $('aoiClear').addEventListener('click', () => {
    aoiState.list = [];
    renderAoiCanvas(sessionId);
  });
  $('aoiPad').addEventListener('change', (e) => {
    aoiState.pad = Math.max(0, Number(e.target.value) || 0);
    renderAoiCanvas(sessionId);
  });
  $('aoiSet').addEventListener('change', (e) => loadAoiSet(sessionId, e.target.value));
  $('aoiSave').addEventListener('click', () => saveAoiSet(sessionId));

  if (aoiState.setName) $('aoiSet').value = aoiState.setName;
  renderAoiCanvas(sessionId);
}

function renderAoiCanvas(sessionId) {
  const w = 900;
  const h = Math.round(w * (1067 / 1707));
  const X = (v) => v * w;
  const Y = (v) => v * h;

  const dots = (aoiState.fixations || []).map((f) =>
    `<circle cx="${X(f.x)}" cy="${Y(f.y)}" r="3" fill="rgba(76,141,255,.55)"/>`).join('');

  // Anisotropic, because the screen is not square: the same angular budget is a
  // different fraction of each axis.
  const padX = (aoiState.pad / aoiState.dpp) / 1707;
  const padY = (aoiState.pad / aoiState.dpp) / 1067;

  const shapes = aoiState.list.map((a) => {
    const [x0, y0, x1, y1] = a.coords;
    const lx = Math.min(x0, x1);
    const hx = Math.max(x0, x1);
    const ly = Math.min(y0, y1);
    const hy = Math.max(y0, y1);
    return `
      <rect x="${X(lx - padX)}" y="${Y(ly - padY)}"
        width="${X(hx - lx + 2 * padX)}" height="${Y(hy - ly + 2 * padY)}"
        fill="rgba(224,168,0,.10)" stroke="#e0a800" stroke-width="1"
        stroke-dasharray="4 3"/>
      <rect x="${X(lx)}" y="${Y(ly)}" width="${X(hx - lx)}" height="${Y(hy - ly)}"
        fill="rgba(92,184,92,.14)" stroke="#5cb85c" stroke-width="1.5"/>
      <text x="${X(lx) + 6}" y="${Y(ly) + 15}" fill="#cfd4da" font-size="12">${a.aoi_id}</text>`;
  }).join('');

  $('aoiCanvas').innerHTML = `
    <svg id="aoiSvg" viewBox="0 0 ${w} ${h}" width="100%"
      style="background:#7f7f7f;border-radius:8px;cursor:crosshair">
      ${dots}${shapes}
    </svg>`;

  $('aoiCaption').innerHTML = aoiState.list.length
    ? `<span style="color:var(--ok)">■</span> drawn boundary ·
       <span style="color:var(--warn)">■</span> padded to ${aoiState.pad}°, which is what a
       fixation is actually tested against · blue dots are fixations`
    : 'Draw a rectangle to begin. Fixations are shown so you can see what you are enclosing.';

  wireAoiDrawing(sessionId);
  if (aoiState.list.length) runAoiAnalysis(sessionId);
}

function wireAoiDrawing(sessionId) {
  const svg = $('aoiSvg');
  if (!svg) return;
  let start = null;

  const at = (ev) => {
    const r = svg.getBoundingClientRect();
    return [(ev.clientX - r.left) / r.width, (ev.clientY - r.top) / r.height];
  };

  svg.addEventListener('mousedown', (ev) => {
    if (!aoiState.armed) return;
    start = at(ev);
  });

  svg.addEventListener('mouseup', (ev) => {
    if (!start) return;
    const [x0, y0] = start;
    const [x1, y1] = at(ev);
    start = null;

    // A click rather than a drag: too small to be a boundary anyone meant.
    if (Math.abs(x1 - x0) < 0.01 || Math.abs(y1 - y0) < 0.01) return;

    aoiState.list.push({
      aoi_id: `aoi_${aoiState.list.length + 1}`,
      shape: 'rect',
      coords: [x0, y0, x1, y1],
      label: null,
    });
    aoiState.armed = false;
    $('aoiMsg').textContent = '';
    renderAoiCanvas(sessionId);
  });
}

async function runAoiAnalysis(sessionId) {
  if (!aoiState.setName) {
    // Say so rather than leaving an empty panel, which looks like a zero result.
    $('aoiMetrics').innerHTML = `<div class="note">Save the set to compute dwell
      times, entry times and hit rate against this session.</div>`;
    return;
  }

  const r = await api(`/api/sessions/${encodeURIComponent(sessionId)}/aoi`
    + `?set=${encodeURIComponent(aoiState.setName)}&pad_deg=${aoiState.pad}`);

  if (r.refusal) {
    $('aoiMetrics').innerHTML = `<div class="note">AOI analysis refused:
      <strong>${r.refusal}</strong>. Without geometry a pixel tolerance is a
      different angular tolerance for every participant, so hit rates would not
      be comparable across a study.</div>`;
    return;
  }

  const rows = Object.values(r.metrics).map((m) => `<tr>
    <td>${m.aoi_id}</td>
    <td>${m.n_fixations}</td>
    <td>${m.n_dwells}</td>
    <td>${Math.round(m.total_dwell_ms)}</td>
    <td>${m.first_fixation_duration_ms == null ? '—' : Math.round(m.first_fixation_duration_ms)}</td>
    <td>${m.entry_time_ms == null ? '—' : Math.round(m.entry_time_ms)}</td>
    <td>${m.first_pass_dwell_ms == null ? '—' : Math.round(m.first_pass_dwell_ms)}</td>
    <td>${m.second_pass_dwell_ms == null ? '—' : Math.round(m.second_pass_dwell_ms)}</td>
  </tr>`).join('');

  $('aoiMetrics').innerHTML = `
    <div class="card" style="margin-top:12px">
      <div class="k">hit rate</div>
      <div class="v">${(r.hit_rate * 100).toFixed(0)}%</div>
      <div class="n">${r.n_hits} of ${r.n_fixations} fixations · padded
        ${r.pad_deg}° · set <code>${r.provenance.aoi_set}</code>
        v${r.provenance.aoi_version} · hash
        <code>${r.provenance.aoi_content_hash}</code></div>
    </div>
    <table style="margin-top:12px"><thead><tr>
      <th>AOI</th><th>fixations</th><th>dwells</th><th>total dwell ms</th>
      <th>first fix ms</th><th>entry ms</th><th>1st pass ms</th><th>2nd pass ms</th>
    </tr></thead><tbody>${rows}</tbody></table>
    <div class="note">Six separately-operationalised measures, per Holmqvist —
      §4.1 treats these as distinct constructs, not synonyms. An AOI never looked
      at reports — rather than 0, because a zero entry time would read as "looked
      at immediately". The hash above identifies the exact boundaries these
      numbers came from; §4.2 measured a 77→88→93 swing from refining the same
      definitions on the same data.</div>`;
}

async function loadAoiSet(sessionId, name) {
  aoiState.setName = name;
  if (!name) {
    aoiState.list = [];
    renderAoiCanvas(sessionId);
    return;
  }

  const r = await api(`/api/sessions/${encodeURIComponent(sessionId)}/aoi`
    + `?set=${encodeURIComponent(name)}&pad_deg=${aoiState.pad}`);
  aoiState.list = (r.aois || []).filter((a) => a.shape === 'rect');
  renderAoiCanvas(sessionId);
}

async function saveAoiSet(sessionId) {
  const name = aoiState.setName || prompt('Name for this AOI set:', 'panels');
  if (!name || !aoiState.list.length) return;

  const res = await fetch('/api/aoi-sets', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, aois: aoiState.list }),
  }).then((r) => r.json());

  aoiState.setName = name;
  await showAoi(sessionId);
  $('aoiMsg').textContent = res.written
    ? `saved as v${res.version} · ${res.content_hash}`
    : 'unchanged — nothing written';
}

// ---------------------------------------------------------------------------
// Engine agreement
//
// §2.2 is the reason this panel exists: engine choice alone swung valid-frame
// yield 43%->63% and expression counts 3-4x on IDENTICAL video, with
// between-engine agreement at r = 0.37-0.75. That spread is the free
// uncertainty estimate — the only empirical handle on how much of a result is
// the face and how much is the detector.
//
// A channel with one engine has none of that, and the panel says so rather than
// showing an empty table. "No disagreement measured" and "no disagreement" are
// different claims, and a blank space reads as the second.
// ---------------------------------------------------------------------------

async function showAgreement(sessionId) {
  const host = $('agreement');
  if (!host) return;
  host.innerHTML = '<h2>Engine agreement</h2><div class="empty">computing…</div>';

  const r = await api(`/api/sessions/${encodeURIComponent(sessionId)}/agreement`);
  const s = r.summary;
  const [lo, hi] = s.published_range;

  const cards = [];

  // Between engines first, because it is the one the evidence speaks to — and
  // the one that is usually absent.
  if (s.between_engines.n > 0) {
    const med = s.between_engines.median_r;
    cards.push(card('Between engines', fmt(med),
      `${s.between_engines.n} channels · §2.2 measured ${lo}–${hi}`,
      med >= hi ? 'ok' : med >= lo ? 'warn' : 'bad'));
  } else {
    cards.push(card('Between engines', 'none',
      'no second engine — see below', 'warn'));
  }

  if (s.between_placements.n > 0) {
    // Read differently from the above. Same model, same pixels: these SHOULD
    // agree closely, so a low value is a placement bug rather than the
    // uncertainty §2.2 describes.
    const med = s.between_placements.median_r;
    cards.push(card('Between placements', fmt(med),
      `${s.between_placements.n} channels · same engine, so expect high`,
      med >= 0.8 ? 'ok' : 'warn'));
    cards.push(card('Worst placement pair', fmt(s.between_placements.min_r),
      'same model on the same pixels', s.between_placements.min_r >= 0.5 ? '' : 'bad'));
  }

  if (s.n_single_source) {
    cards.push(card('Single-source channels', String(s.n_single_source),
      'no uncertainty estimate available'));
  }

  if (s.n_low_variance) {
    // Excluded rather than counted as disagreement. Correlating a channel that
    // never moved measures noise against noise, and folding those in drags the
    // median toward zero with channels that had nothing to say.
    cards.push(card('Barely moved', String(s.n_low_variance),
      'excluded — nothing to agree about'));
  }

  const worst = r.channels
    .filter((c) => c.verdict === 'ok')
    .sort((a, b) => a.r - b.r)
    .slice(0, 12);

  host.innerHTML = `
    <h2>Engine agreement</h2>
    <div class="cards">${cards.join('')}</div>

    ${s.between_engines.n === 0 ? `<div class="note">
      <strong>No channel here was produced by two different engines</strong>, so the
      inter-engine spread §2.2 measured at r = ${lo}–${hi} — which is the free
      uncertainty estimate for facial measurement — is unavailable for this
      session. Not measuring the disagreement does not remove it. §2.2's
      instruction is explicit: never single-engine on facial, and treat no
      engine's absolute output as ground truth.</div>` : ''}

    ${s.between_placements.n > 0 ? `<div class="note">
      The figures above are <strong>between placements</strong> — the same engine
      run in the browser and again server-side over the stored video. They are
      not comparable to §2.2's inter-engine range, and should sit much higher:
      one model, the same pixels. A low value here is a placement bug, not
      measurement uncertainty.</div>` : ''}

    ${worst.length ? `
      <table style="margin-top:12px"><thead><tr>
        <th>channel</th><th>kind</th><th>r</th><th>n</th>
      </tr></thead><tbody>${worst.map((c) => `<tr>
        <td>${c.channel}</td>
        <td class="txt">${c.kind}</td>
        <td class="${c.r < 0.5 ? 'tier-low' : ''}">${fmt(c.r, 3)}</td>
        <td>${c.n}</td>
      </tr>`).join('')}</tbody></table>
      <div class="note">Weakest agreement first — the informative end. A channel
        two sources disagree about is one no single number should be quoted for.
        ${s.n_low_variance ? `<br><br><strong>${s.n_low_variance} channels are
        excluded above</strong> because they barely moved. Measured on this
        session, <code>blendshape.jawRight</code> correlated at r = 0.065
        between two placements of the same engine on the same pixels — which
        looks alarming until you see its sd was 0.010 and the participant never
        moved their jaw sideways. Both engines correctly reported nothing.
        Correlating noise against noise is not a disagreement.` : ''}</div>` : ''}`;
}

// ---------------------------------------------------------------------------
// voice and respiration
//
// Both are summarised rather than plotted here. Their per-channel traces are
// already reachable from the Channels table; what is not reachable from a table
// is what each modality declines to tell you, and that is the part a researcher
// has to see before reading anything into the numbers.
// ---------------------------------------------------------------------------

function voicePanel(eq) {
  const v = eq?.voice;
  if (!v) return '';
  const m = v.metrics;
  const voiced = m.voiced_fraction;
  const preserved = m.speech_content_preserved;

  const cards = [
    // Deliberately uncoloured. A low voiced fraction is correct for a session
    // that was mostly a silent calibration task, and wrong for one that was
    // meant to be an interview — the UI cannot tell which, and guessing would
    // flag a healthy session red.
    card('Voiced', voiced == null ? '—' : `${(voiced * 100).toFixed(1)}%`,
      'of analysis windows carried voicing'),
    card('Windows', m.achieved_window_rate == null ? '—'
      : `${(m.achieved_window_rate * 100).toFixed(0)}%`,
      'of the expected eGeMAPS windows were produced'),
    card('Speech content', preserved ? 'preserved' : 'ALTERED',
      preserved ? 'no noise suppression was applied'
        : 'noise suppression ran — spectral features are not comparable',
      preserved ? 'ok' : 'bad'),
  ];

  return `
    <h2>Voice</h2>
    <div class="cards">${cards.join('')}</div>
    <div class="note">
      88 eGeMAPSv02 functionals, and <strong>no valence or emotion channel</strong>.
      §2.3: the acoustic features are the open part and the mapping from them to
      affect is the licensed, unpublished part. An open pipeline can compute the
      features honestly; naming one of them "valence" would be inventing the
      mapping rather than implementing it.</div>
    ${preserved === 0 || preserved === false ? `<div class="note bad">
      Browser noise suppression was applied to this recording. It is designed to
      remove exactly the spectral content eGeMAPS measures, so these features are
      not comparable with sessions captured without it.</div>` : ''}`;
}

function respirationPanel(eq) {
  const r = eq?.resp;
  if (!r) return '';
  const m = r.metrics;
  const roi = m.roi_found_rate;
  const usable = m.usable_fraction;
  const fps = m.analysis_fps;

  const cards = [
    card('ROI found', roi == null ? '—' : `${(roi * 100).toFixed(0)}%`,
      'of analysed frames had a shoulder line',
      roi == null ? '' : roi >= 0.5 ? 'ok' : 'bad'),
    card('Usable', usable == null ? '—' : `${(usable * 100).toFixed(0)}%`,
      'of segments passed every confidence check',
      usable == null ? '' : usable >= 0.3 ? 'ok' : 'bad'),
    card('Analysis rate', fps == null ? '—' : `${fmt(fps, 1)} Hz`,
      'band tops out at 0.5 Hz',
      fps == null ? '' : fps >= 2 ? 'ok' : 'bad'),
    // Not a missing feature, and not a placeholder. Shown as a card so it sits
    // where a reader looks for it rather than only in prose they may skip.
    card('Breathing rate', 'withheld',
      'no validation study exists — see below', 'warn'),
  ];

  return `
    <h2>Respiration</h2>
    <div class="cards">${cards.join('')}</div>
    <div class="note">
      <strong>This pipeline does not report breaths per minute.</strong> §2.4:
      across two dedicated research passes, no bpm accuracy figure for webcam
      chest-motion tracking against a chest belt, RIP or spirometry survived
      adversarial checking, and one specific figure was explicitly refuted. A
      breathing rate is a number a clinician recognises on sight, so one this
      project cannot defend is worse than none.
      <br><br>
      What you get instead is the waveform and its confidence channels, which is
      the more useful output anyway: inhale onsets, breath-holds and sighs are
      all events on a waveform and none of them need a calibrated rate. Plot
      <code>respiration.waveform</code> from the Channels table, and read it
      against <code>respiration.periodicity</code> and
      <code>respiration.gross_motion</code> — a segment where the participant
      shifted in their seat will look like a large clean breath otherwise.
      <br><br>
      Unblocking the rate takes a validation study: simultaneous webcam and RIP
      belt, Bland-Altman on 60s windows plus waveform cross-correlation, N≈30–40
      stratified on skin tone, clothing, distance and framing.</div>
    <div class="note">
      Respiration output is plausibly <strong>health data under GDPR Art.
      4(15)</strong> even with no identification purpose, because Art. 9's
      health limb carries no identification qualifier the way the biometric limb
      does (§6.3). Treat it as higher legal risk than gaze, face or voice.</div>`;
}

// ---------------------------------------------------------------------------
// protocol
//
// Which study definition this session ran under, and whether that definition
// still says what it said at the time. The four outcomes need different
// responses, so they are not collapsed into a single green/red.
// ---------------------------------------------------------------------------

function protocolCard(check) {
  if (!check) return '';
  const d = check.detail ?? {};

  if (check.ok) {
    return card('Protocol', `${d.study_id} v${d.version}`,
      `${d.content_hash} · matches studies/${d.study_id}.json`, 'ok');
  }

  const reason = (check.reasons ?? [])[0];
  if (reason === 'no_study_recorded') {
    // Not a fault to fix retroactively. These sessions predate study
    // definitions and there is nothing to recover — an amber note, not a red
    // one, because the data is fine and only its attributability is missing.
    return card('Protocol', 'not recorded',
      `${d.study_id ?? 'unknown'} — captured before study definitions existed`,
      'warn');
  }
  if (reason === 'study_unavailable') {
    return card('Protocol', 'unavailable',
      `${d.study_id} is not in studies/ — restore it from version control`,
      'bad');
  }
  return card('Protocol', 'EDITED', `${d.study_id} changed after this session`,
    'bad');
}

function protocolNote(check) {
  if (!check || check.ok) return '';
  const d = check.detail ?? {};
  const reason = (check.reasons ?? [])[0];

  if (reason === 'study_edited_since_session') {
    return `<div class="note bad">
      <strong>The study definition changed after this session was collected.</strong>
      It recorded <code>${d.recorded_hash}</code> and
      <code>studies/${d.study_id}.json</code> now hashes to
      <code>${d.file_hash}</code>${d.recorded_version === d.file_version
        ? `, while both still call themselves v${d.file_version}` : ''}.
      Sessions either side of that edit were not run under the same protocol,
      and pooling them is the §4.2 problem in a different costume: what changed
      might be the calibration grid, or it might be the retention period the
      participant was promised. <code>git log studies/${d.study_id}.json</code>
      will say which.</div>`;
  }
  if (reason === 'no_study_recorded') {
    return `<div class="note">
      This session carries no protocol hash, so what the participant was told
      and what they were asked to do cannot be reconstructed from the data
      alone. Sessions captured from now on record it; these cannot be
      retrofitted, because the definition they ran under was never written
      down.</div>`;
  }
  return '';
}

function transcriptPanel(eq) {
  const s = eq?.speech;
  if (!s) return '';
  const m = s.metrics;
  const rejected = m.segments_rejected ?? 0;
  const retained = m.segments_retained ?? 0;
  const langP = m.language_probability;

  const cards = [
    card('Segments kept', `${retained}`,
      'passed both confidence gates'),
    // Any non-zero value is worth a look: the conditions that produced one
    // hallucination usually produced more, including ones that squeaked
    // through. Not coloured red, because rejecting is the system working.
    card('Rejected', `${rejected}`,
      rejected ? 'dropped as probable hallucination' : 'none',
      rejected > 0 ? 'warn' : 'ok'),
    card('Coverage', m.speech_coverage == null ? '—'
      : `${(m.speech_coverage * 100).toFixed(0)}%`,
      'of the recording is retained speech'),
    card('Language', langP == null ? '—' : `p=${fmt(langP)}`,
      'model confidence in the language it detected',
      langP == null ? '' : langP >= 0.7 ? 'ok' : 'warn'),
  ];

  return `
    <h2>Transcript</h2>
    <div class="cards">${cards.join('')}</div>
    <div class="note">
      This session's participant chose the <code>media_plus_transcript</code>
      tier. No transcript exists for any other tier, and the words are stored
      as <code>speech_segment</code> events rather than as signals — a
      transcript is not a measurement of a quantity.
      <strong>No word error rate is claimed.</strong> Published Whisper figures
      come from curated corpora, not a consumer microphone in someone's home
      after the browser's DSP; read the per-segment confidences instead of
      taking the text flat.</div>
    ${rejected > 0 ? `<div class="note">
      <strong>${rejected} segment${rejected === 1 ? ' was' : 's were'} dropped
      as probable hallucination.</strong> Whisper emits fluent, confident text
      where there is no speech, so segments failing either the no-speech or the
      log-probability gate are discarded. Their timing and confidence are kept
      as <code>speech_segment_rejected</code> events; <strong>their text is
      not</strong>, because a sentence a participant never said is not made
      safer by being labelled. The conditions that produce one usually produce
      more, so it is worth listening to the recording around those
      timestamps.</div>` : ''}`;
}

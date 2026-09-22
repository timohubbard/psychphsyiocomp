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

    <h2>Engine runs</h2>
    ${runsTable(d.runs)}

    <h2>Quality over time</h2>
    ${qualityCharts(d.quality)}

    <h2>Channels <span class="pill">${d.channels.length}</span></h2>
    <div class="scroll">${channelTable(d.channels)}</div>

    <h2>Events <span class="pill">${d.events.length}</span></h2>
    <div class="scroll">${eventsTable(d.events)}</div>

    <div id="plot"></div>`;

  [...document.querySelectorAll('tr.clickable')].forEach((tr) => {
    tr.addEventListener('click', () => plotChannel(id, tr.dataset.channel, tr.dataset.source));
  });
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
  const metrics = [...new Set(rows.map((r) => r.metric))];
  if (!metrics.length) return '<div class="note">No windowed quality metrics.</div>';

  return metrics.map((metric) => {
    const pts = rows.filter((r) => r.metric === metric && r.t != null)
      .map((r) => [r.t, r.value]).sort((a, b) => a[0] - b[0]);
    if (pts.length < 2) return '';
    const floor = metric === 'achieved_fps' ? MIN_HZ
      : metric === 'mean_luminance' ? MIN_LUMA : null;
    return `<div class="card" style="margin-bottom:10px">
      <div class="k">${metric}</div>${sparkline(pts, floor)}</div>`;
  }).join('');
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

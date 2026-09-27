/**
 * The Reliability page: how far raters agreed, and how an engine does on their terms.
 *
 * Per codebook version: every session anyone has coded, with rater progress
 * (counts only — the page never sees a rater's labels), the ceiling the raters
 * set (evaluation.reference_from), and — when a scoring rule is chosen — the
 * engine's score on the moments it answered, read against that ceiling
 * (scoring_rules.engine_arm). A refusal is shown as its reason, never as a
 * dash: "too few items" and "the engine missed a quarter of the moments" are
 * different findings.
 *
 * Scoring rules are versioned records like codebooks. The editor below checks
 * a rule against the server on every edit (POST /api/scoring-rules?check=1)
 * and saves a new version; nothing here invents a mapping from an engine to a
 * category.
 */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const fmt = (v, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d));

async function api(path, opts) {
  const res = await fetch(path, { cache: 'no-store', ...opts });
  const body = await res.json();
  if (!res.ok) throw new Error(body.detail ?? body.error ?? res.status);
  return body;
}

let codebooks = [];
let sessions = [];
let rules = [];
let checkTimer = null;

const current = () => {
  const [id, hash] = ($('cb').value || '|').split('|');
  return { id, hash, cb: codebooks.find((c) => c.codebook_id === id && c.content_hash === hash) };
};

async function loadRules(select = $('rule').value) {
  const { id, hash } = current();
  rules = id ? (await api(`/api/scoring-rules?codebook=${encodeURIComponent(id)}&version=${encodeURIComponent(hash)}`)).rules : [];
  $('rule').innerHTML = `<option value="">No engine — raters only</option>${rules.map((r) =>
    `<option value="${esc(r.rule_id)}@${esc(r.content_hash)}">${esc(r.rule_id)} · ${esc(r.content_hash.slice(0, 8))} — ${esc(r.name)}</option>`).join('')}`;
  $('rule').value = rules.some((r) => `${r.rule_id}@${r.content_hash}` === select) ? select : '';
}

function engineCell(e) {
  if (!e) return '<span class="why">choose a scoring rule</span>';
  if (e.refusal) return `<span class="refused">refused — ${esc(e.refusal.reason)}</span><div class="why">${esc(e.refusal.detail)}</div>`;
  const ev = e.evaluation;
  const frac = ev.fraction_of_ceiling;
  return `<b>${fmt(ev.engine_score)}</b> <span class="why">${esc(ev.ceiling_kind)}</span>
    ${frac === null ? '' : `<div class="bar" title="${fmt(frac * 100, 0)}% of the raters' ceiling"><i style="width:${Math.min(100, frac * 100)}%"></i></div>
    <div class="why">${fmt(frac * 100, 0)}% of the ceiling · answered ${e.n_answered} of ${e.n_items} (${fmt(e.coverage * 100, 0)}%)</div>`}
    ${(ev.notes ?? []).map((n) => `<div class="why">${esc(n)}</div>`).join('')}`;
}

async function render() {
  const { id, hash, cb } = current();
  if (!id) { $('main').innerHTML = '<div class="note">No codebooks yet — build one on the <a href="./codebook.html">Codebooks</a> page.</div>'; return; }
  $('main').innerHTML = '<div class="note">computing…</div>';
  const rule = $('rule').value;
  const use = $('use').value;
  const rows = [];
  for (const s of sessions) {
    const { raters } = await api(`/api/annotation-progress/${encodeURIComponent(s.session_id)}?codebook=${encodeURIComponent(id)}&version=${encodeURIComponent(hash)}`);
    if (!raters.length) continue;
    let rel;
    try {
      rel = await api(`/api/reliability/${encodeURIComponent(s.session_id)}?codebook=${encodeURIComponent(id)}&version=${encodeURIComponent(hash)}&use=${use}${rule ? `&rule=${encodeURIComponent(rule)}` : ''}`);
    } catch (err) {
      rel = { refusal: { reason: 'error', detail: err.message } };
    }
    rows.push({ s, raters, rel });
  }
  const table = rows.length ? `<table><thead><tr><th>Session</th><th>Raters</th><th>Moments</th><th>Raters agree (ceiling)</th><th>Engine</th></tr></thead><tbody>
    ${rows.map(({ s, raters, rel }) => `<tr>
      <td><a href="./index.html?session=${encodeURIComponent(s.session_id)}" class="mono">${esc(s.session_id)}</a></td>
      <td class="num">${raters.length}<div class="why">${raters.map((r) => `${esc(r.rater_id)} ${r.n_labelled}/${r.n_items}${r.complete ? ' ✓' : ''}`).join(' · ')}</div></td>
      <td class="num">${rel.matrix ? `${rel.matrix.items.length}${rel.matrix.n_dropped ? `<div class="why">${rel.matrix.n_dropped} dropped: not every rater answered</div>` : ''}` : '—'}</td>
      <td>${rel.refusal ? `<span class="refused">refused — ${esc(rel.refusal.reason)}</span><div class="why">${esc(rel.refusal.detail ?? '')}</div>`
        : `<b>${fmt(rel.reference.ceiling)}</b> <span class="why">${esc(rel.reference.ceiling_kind)}, ${rel.reference.n_raters} raters, ${fmt(rel.reference.unanimous_fraction * 100, 0)}% unanimous</span>`}</td>
      <td>${rel.refusal ? '<span class="why">needs a reference first</span>' : engineCell(rel.engine)}</td>
    </tr>`).join('')}</tbody></table>`
    : '<div class="note">Nobody has coded this codebook version yet. Raters code on the <a href="./annotate.html">Annotate</a> page, each with their own rater ID.</div>';

  const cats = cb ? (await api(`/api/codebooks/${encodeURIComponent(id)}?version=${encodeURIComponent(hash)}`)).categories : [];
  const template = {
    rule_id: 'my-rule', name: 'Describe the mapping in words', codebook_id: id, codebook_version: hash,
    source: 'face.opengraphau_aus@0.1.0+server-batch', channel: 'au.AU12', window_ms: [-250, 250],
    statistic: 'median', min_samples: 3,
    bins: [{ below: 0.5, category: cats[1]?.id ?? 'category-a' }, { below: null, category: cats[0]?.id ?? 'category-b' }],
  };
  $('main').innerHTML = `
    <h2>Per session</h2>
    <div class="sub">The ceiling is how far the raters agreed with each other; an engine is read against it, on the same moments.
      Items any rater skipped are dropped, never filled in. Codebook <span class="mono">${esc(id)}</span> version <span class="mono">${esc(hash)}</span>.</div>
    ${table}
    <h2>Scoring rules for this version</h2>
    <div class="sub">How an engine's output becomes a category — fixed and hashed before anyone sees a score.</div>
    ${rules.length ? `<table><thead><tr><th>Rule</th><th>Reads</th><th>Window</th><th>Bins</th><th>Notes</th></tr></thead><tbody>${rules.map((r) => `<tr>
      <td><b>${esc(r.rule_id)}</b> <span class="mono why">${esc(r.content_hash)}</span><div class="why">${esc(r.name)}</div></td>
      <td class="mono">${esc(r.source)}<div class="why">${esc(r.channel ?? `derived: ${r.derived?.kind}`)} · ${esc(r.statistic)}, ≥ ${r.min_samples} samples</div></td>
      <td class="num">${r.window_ms[0]}..${r.window_ms[1]} ms</td>
      <td>${r.bins.map((b, k) => `${b.below === null ? `≥ ${r.bins[k - 1]?.below ?? '—'}` : `&lt; ${b.below}`} → <b>${esc(b.category)}</b>`).join('<br>')}</td>
      <td class="why">${(r.notes ?? []).map(esc).join('<br>') || '—'}</td></tr>`).join('')}</tbody></table>`
      : '<div class="note">No scoring rules for this version yet.</div>'}
    <h2>New scoring rule</h2>
    <div class="sub">One source, one channel (or <code>derived: {"kind": "gaze_onscreen", "margin": 0.1}</code> on gaze), a window around each moment,
      a statistic, and ordered bins. Checked by the server as you type; saving makes an immutable version.</div>
    <div class="editor">
      <textarea id="ruleJson" spellcheck="false">${esc(JSON.stringify(template, null, 2))}</textarea>
      <div><div class="panel" id="ruleCheck">checking…</div>
        <div class="row"><button class="primary" id="saveRule" disabled>Save rule</button><span id="saved" class="why"></span></div></div>
    </div>`;
  $('ruleJson').addEventListener('input', scheduleCheck);
  $('saveRule').addEventListener('click', saveRule);
  scheduleCheck();
}

function scheduleCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(checkRule, 200);
}

async function checkRule() {
  let body;
  try { body = JSON.parse($('ruleJson').value); } catch (err) {
    $('ruleCheck').innerHTML = `<span class="bad">Not JSON: ${esc(err.message)}</span>`;
    $('saveRule').disabled = true;
    return;
  }
  const r = await api('/api/scoring-rules?check=1', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  $('ruleCheck').innerHTML = r.valid
    ? `<span class="ok"><b>Valid</b></span> — would be saved as version <span class="mono">${esc(r.content_hash)}</span>
       ${r.notes.length ? `<ul>${r.notes.map((n) => `<li class="warn">${esc(n)}</li>`).join('')}</ul>` : ''}`
    : `<span class="bad"><b>${r.reasons.length} problem${r.reasons.length === 1 ? '' : 's'}</b></span><ul>${r.reasons.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>`;
  $('saveRule').disabled = !r.valid;
}

async function saveRule() {
  try {
    const rec = await api('/api/scoring-rules', { method: 'POST', headers: { 'content-type': 'application/json' }, body: $('ruleJson').value });
    await loadRules(`${rec.rule_id}@${rec.content_hash}`);
    await render();
    $('saved').textContent = `Saved ${rec.rule_id} version ${rec.content_hash}.`;
  } catch (err) {
    $('saved').textContent = err.message;
  }
}

async function init() {
  [codebooks, sessions] = await Promise.all([
    api('/api/codebooks').then((b) => b.codebooks), api('/api/sessions').then((b) => b.sessions)]);
  $('cb').innerHTML = codebooks.map((c) => `<option value="${esc(c.codebook_id)}|${esc(c.content_hash)}">${esc(c.codebook_id)} · ${esc(c.content_hash.slice(0, 8))}${
    c.n_label_sets ? ` · ${c.n_label_sets} coded` : ''}</option>`).join('');
  const want = new URLSearchParams(location.search).get('codebook');
  const pick = codebooks.find((c) => c.codebook_id === want) ?? codebooks.find((c) => c.n_label_sets) ?? codebooks[0];
  if (pick) $('cb').value = `${pick.codebook_id}|${pick.content_hash}`;
  $('cb').addEventListener('change', async () => { await loadRules(''); render(); });
  $('rule').addEventListener('change', render);
  $('use').addEventListener('change', render);
  await loadRules();
  render();
}

init().catch((err) => { $('main').innerHTML = `<div class="note bad">${esc(err.message)}</div>`; });

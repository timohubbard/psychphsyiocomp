/**
 * The codebook builder.
 *
 * A codebook is what raters code against: the categories they choose between,
 * each defined, and the moments they are asked about. Whether it is valid, and
 * the hash it will be filed under, come from the server on every edit
 * (POST /api/codebooks?check=1 → server/annotation_store.py), so this page never
 * holds a second copy of the rules. The category buttons in the preview are
 * annotate_view.js — the coding page's own.
 *
 * A codebook is never edited in place. Saving different content makes a new
 * version with a new hash, and labels stay with the version they were made
 * under: raters who coded different moments or different definitions are
 * never pooled. The page says so before you save, with how much coding the
 * earlier versions hold.
 */

import { NO_DEFAULT_NOTE, categoriesHtml } from './annotate_view.js';
import { blankCodebook, categoryIdFrom, fmtTime, gridTimes, mergeItems, parseTimes,
  sampleTimes, shuffle } from './codebook_model.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

let cb = blankCodebook();
let savedAs = null;          // JSON of the version on disk this was opened from or saved as
let versions = [];           // /api/codebooks
let sessions = [];           // /api/sessions — for the recording picker and lengths
let check = { valid: false, reasons: [], content_hash: null };
let sideTab = 'rater';
let addTab = 'type';
let previewAt = 0;
let pickSession = '';
let checkTimer = null;
let checkSeq = 0;

const strip = (c) => {
  const { content_hash: _h, created_utc: _c, ...rest } = c;
  return rest;
};

// ---------------------------------------------------------------------------
// the form
// ---------------------------------------------------------------------------

function field(label, key, value, { help = '', placeholder = '', rows = 0, mono = false } = {}) {
  const attrs = `data-k="${esc(key)}"${placeholder ? ` placeholder="${esc(placeholder)}"` : ''}${mono ? ' class="mono"' : ''}`;
  const control = rows ? `<textarea ${attrs} rows="${rows}">${esc(value)}</textarea>`
    : `<input ${attrs} value="${esc(value)}">`;
  return `<div class="field" data-field="${esc(key)}"><label><span class="lbl">${label}</span>${control}</label>
    ${help ? `<div class="help">${help}</div>` : ''}<div class="err"></div></div>`;
}

function section(n, id, title, blurb, body) {
  return `<section class="card" id="sec-${id}"><header><span class="n">${n}</span>
    <div class="grow"><h3>${title}</h3><p>${blurb}</p></div><span class="badge" data-badge="${id}"></span></header>
    <div class="body">${body}</div><div class="secprob" data-problems="${id}"></div></section>`;
}

function render() {
  const cats = cb.categories ?? [];
  $('form').innerHTML = `<div class="formwrap">
    ${section(1, 'basics', 'Basics', 'Raters see the name. The id is part of the path every label file is filed under.', `
      <div class="grid2">
        ${field('Codebook id', 'codebook_id', cb.codebook_id, { mono: true, help: 'Letters, digits, - and _.' })}
        ${field('Name', 'name', cb.name, { help: 'What raters are answering, e.g. “Where is the participant looking?”' })}
      </div>`)}

    ${section(2, 'categories', 'Categories', 'What a rater chooses between. Each needs a definition: an undefined category is where raters silently disagree.', `
      <div class="cats-edit">${cats.map((c, i) => `
        <div class="catc" data-cat="${esc(c.id)}">
          <span class="k" title="Raters press ${i + 1} for this">${i + 1}</span>
          <div>
            <div class="row2">
              ${field('Label', `cat.${i}.label`, c.label, { placeholder: 'e.g. At the screen' })}
              ${field('Id', `cat.${i}.id`, c.id, { mono: true })}
            </div>
            ${field('Definition', `cat.${i}.description`, c.description, { rows: 2,
              placeholder: 'What counts, and where the boundary is — e.g. “Eyes directed at the monitor, including a glance at its edge.”' })}
            <div class="cerr"></div>
          </div>
          <div class="tools">
            <button class="icon" data-cmove="${i}" data-dir="-1" title="Move up" aria-label="Move up" ${i === 0 ? 'disabled' : ''}>↑</button>
            <button class="icon" data-cmove="${i}" data-dir="1" title="Move down" aria-label="Move down" ${i === cats.length - 1 ? 'disabled' : ''}>↓</button>
            <button class="icon rm" data-cremove="${i}" title="Remove" aria-label="Remove category">✕</button>
          </div>
        </div>`).join('')}</div>
      <div class="mtools"><button class="add" id="btnAddCat">+ Add category</button>
        <span class="muted">Order sets the number key a rater presses. At least two: one category is not a decision.</span></div>`)}

    ${section(3, 'moments', 'Moments', 'Times into each session’s recording. Every session coded with this codebook is asked about the same moments, in this order.', momentsHtml())}
  </div>`;
  renderSide();
  scheduleCheck();
}

function momentsHtml() {
  return `<div id="mlistHost">${momentsListHtml()}</div>${adderHtml()}`;
}

function shortestMs() {
  const lengths = sessions.map((s) => s.duration_s).filter((d) => d > 0);
  return lengths.length ? Math.min(...lengths) * 1000 : null;
}

/** The moments so far: redrawn on its own when moments change, so the adder (and a playing video) stays put. */
function momentsListHtml() {
  const items = cb.items ?? [];
  const sorted = [...items].sort((a, b) => a - b);
  const chrono = items.every((t, i) => i === 0 || items[i - 1] <= t);
  const shortest = shortestMs();
  const late = shortest === null ? 0 : items.filter((t) => t > shortest).length;
  return `
    <div class="msum"><span><b>${items.length}</b> moment${items.length === 1 ? '' : 's'}</span>
      ${items.length ? `<span class="muted">from ${fmtTime(sorted[0])} to ${fmtTime(sorted.at(-1))} · ${chrono ? 'in time order' : 'in a shuffled order'}</span>` : ''}</div>
    ${late ? `<div class="note warn">${late} moment${late === 1 ? ' is' : 's are'} later than the shortest processed session
      (${fmtTime(shortest)}). A session shorter than a moment cannot be coded at it.</div>` : ''}
    <div class="mlist">${items.map((t, i) => `<span class="mchip"><i>${i + 1}</i>${fmtTime(t)}<button data-mremove="${i}"
      title="Remove" aria-label="Remove ${fmtTime(t)}">✕</button></span>`).join('') || '<span class="muted">None yet — add some below.</span>'}</div>
    ${items.length ? `<div class="mtools">
      <button id="btnSort" ${chrono ? 'disabled' : ''}>Put in time order</button>
      <button id="btnShuffle">Shuffle</button><label class="muted">seed <input id="shuffleSeed" type="number" value="1"></label>
      <button id="btnClear">Remove all</button>
      <span class="muted">Shuffled, raters cannot follow a session’s story from one moment to the next.</span></div>` : ''}`;
}

function adderHtml() {
  const shortest = shortestMs();
  return `<div class="adder">
      <div class="tabs" role="tablist">
        ${[['type', 'Type times'], ['grid', 'Every few seconds'], ['random', 'At random'], ['video', 'From a recording']]
          .map(([k, l]) => `<button class="tab${addTab === k ? ' on' : ''}" data-addtab="${k}">${l}</button>`).join('')}
      </div>
      <div class="pane" ${addTab === 'type' ? '' : 'hidden'}>
        <p class="why">Seconds (12.5), minutes:seconds (1:05), or milliseconds (1500ms), separated by commas or new lines.</p>
        <div class="inline"><div class="field wide"><textarea id="typeTimes" rows="2" placeholder="0:10, 0:25, 1:05.5"></textarea></div>
          <button id="btnAddTyped">Add</button></div>
      </div>
      <div class="pane" ${addTab === 'grid' ? '' : 'hidden'}>
        <p class="why">An even grid: every moment in a span gets the same chance of being coded.</p>
        <div class="inline">
          <div class="field"><label><span class="lbl">Every (s)</span><input id="gEvery" type="number" value="5" min="0.1" step="any"></label></div>
          <div class="field"><label><span class="lbl">From (s)</span><input id="gFrom" type="number" value="10" min="0" step="any"></label></div>
          <div class="field"><label><span class="lbl">To (s)</span><input id="gTo" type="number" value="${shortest ? Math.floor(shortest / 1000) : 120}" min="0" step="any"></label></div>
          <button id="btnAddGrid">Add</button></div>
      </div>
      <div class="pane" ${addTab === 'random' ? '' : 'hidden'}>
        <p class="why">Chosen by the computer, not by eye. Moments picked by hand are the ones where something visibly
          happens, and a reference standard built from those flatters every engine measured against it.
          The same seed gives the same moments.</p>
        <div class="inline">
          <div class="field"><label><span class="lbl">How many</span><input id="rN" type="number" value="20" min="1"></label></div>
          <div class="field"><label><span class="lbl">From (s)</span><input id="rFrom" type="number" value="10" min="0" step="any"></label></div>
          <div class="field"><label><span class="lbl">To (s)</span><input id="rTo" type="number" value="${shortest ? Math.floor(shortest / 1000) : 120}" min="0" step="any"></label></div>
          <div class="field"><label><span class="lbl">At least apart (s)</span><input id="rGap" type="number" value="2" min="0" step="any"></label></div>
          <div class="field"><label><span class="lbl">Seed</span><input id="rSeed" type="number" value="${Math.floor(Math.random() * 1e6)}"></label></div>
          <button id="btnAddRandom">Add</button></div>
      </div>
      <div class="pane player" ${addTab === 'video' ? '' : 'hidden'}>
        <p class="why">Play a session and add the moment you are on. Only sessions whose participants chose to keep
          their recording can be played, and only when the app was started with <code>--media &lt;dir&gt;</code>.</p>
        <div class="inline" style="margin-bottom:10px"><div class="field wide"><select id="pickSession">
          <option value="">Choose a session…</option>${sessions.map((s) => `<option value="${esc(s.session_id)}" ${s.session_id === pickSession ? 'selected' : ''}>
            ${esc(s.session_id)} · ${esc(s.study_id ?? '—')} · ${s.duration_s ? fmtTime(s.duration_s * 1000) : '—'}</option>`).join('')}</select></div></div>
        <div id="pickHost"></div>
      </div>
      <div class="said" id="addSaid" style="padding:0 14px 14px"></div>
    </div>`;
}

// ---------------------------------------------------------------------------
// the side: problems, version status, the rater's view, versions, JSON
// ---------------------------------------------------------------------------

function renderSide() {
  const mine = versions.filter((v) => v.codebook_id === cb.codebook_id);
  const cats = cb.categories ?? [];
  const items = cb.items ?? [];
  previewAt = Math.min(previewAt, Math.max(items.length - 1, 0));
  $('side').innerHTML = `
    <div id="problemsHost"></div>
    <div class="hashline" id="versionLine"></div>
    <div class="tabs" role="tablist">
      <button class="tab" data-tab="rater">Rater’s view</button>
      <button class="tab" data-tab="versions">Versions${mine.length ? ` (${mine.length})` : ''}</button>
      <button class="tab" data-tab="json">JSON</button>
    </div>
    <div class="pane" data-pane="rater">
      <div class="caption">What a rater sees for each moment on the Annotate page — the same buttons, in this order.</div>
      <div class="rater">
        <div class="row"><span>item ${items.length ? previewAt + 1 : 0} of ${items.length} · 0 labelled</span><span class="mono" id="raterHash"></span></div>
        <div class="shot">${items.length ? `<span>the session’s recording, at<b>${fmtTime(items[previewAt])}</b></span>` : '<span>no moments yet</span>'}</div>
        <div class="cats">${categoriesHtml(cats.map((c, i) => ({ ...c, label: c.label || `(category ${i + 1} has no label)`,
          description: c.description || '(no definition yet)' })))}</div>
        <div class="note">${NO_DEFAULT_NOTE}</div>
        ${items.length > 1 ? `<div class="step-row"><button data-preview="-1" ${previewAt === 0 ? 'disabled' : ''}>← Previous moment</button>
          <button data-preview="1" ${previewAt >= items.length - 1 ? 'disabled' : ''}>Next moment →</button></div>` : ''}
      </div>
    </div>
    <div class="pane" data-pane="versions">
      ${mine.length ? `<table class="versions"><thead><tr><th>Version</th><th>Saved</th><th>Categories</th><th>Moments</th><th>Coded</th><th></th></tr></thead><tbody>
        ${mine.map((v) => `<tr class="${v.content_hash === check.content_hash ? 'cur' : ''}">
          <td class="mono">${esc(v.content_hash)}</td><td>${esc((v.created_utc ?? '').slice(0, 16).replace('T', ' '))}</td>
          <td>${v.n_categories}</td><td>${v.n_items}</td>
          <td>${v.n_label_sets ? `${v.n_label_sets} label set${v.n_label_sets === 1 ? '' : 's'}, ${v.n_sessions_coded} session${v.n_sessions_coded === 1 ? '' : 's'}` : '—'}</td>
          <td><button data-open="${esc(v.codebook_id)}|${esc(v.content_hash)}">Open</button></td></tr>`).join('')}</tbody></table>
        <p class="note">Each version keeps its own labels. Labels made under different versions are never pooled, because
          raters who coded different moments or different definitions did not code the same thing.</p>`
        : `<div class="note">No saved versions of <code>${esc(cb.codebook_id)}</code> yet.</div>`}
    </div>
    <div class="pane" data-pane="json">
      <div class="caption">The codebook as it will be saved.</div>
      <textarea id="json" spellcheck="false">${esc(JSON.stringify(cb, null, 2))}</textarea>
      <div class="row" style="margin-top:8px;display:flex;gap:8px;align-items:center"><button id="btnApplyJson">Apply edited JSON</button><span class="bad" id="jsonError"></span></div>
    </div>`;
  showTab();
  paintCheck();
}

function showTab() {
  for (const t of document.querySelectorAll('[data-tab]')) t.classList.toggle('on', t.dataset.tab === sideTab);
  for (const p of document.querySelectorAll('[data-pane]')) p.hidden = p.dataset.pane !== sideTab;
}

// ---------------------------------------------------------------------------
// the server's verdict
// ---------------------------------------------------------------------------

function scheduleCheck() {
  clearTimeout(checkTimer);
  checkTimer = setTimeout(runCheck, 150);
}

async function runCheck() {
  const seq = ++checkSeq;
  const res = await fetch('/api/codebooks?check=1', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(cb),
  });
  const body = await res.json();
  if (seq !== checkSeq) return;   // a later edit's check is already on its way
  check = res.ok ? body : { valid: false, reasons: [body.detail ?? body.error ?? 'the server refused the check'], content_hash: null };
  paintCheck();
}

/** Where a reason is fixed: a field, a category card, or a section. */
function placeOf(reason) {
  if (/^codebook_id/.test(reason)) return { section: 'basics', field: 'codebook_id' };
  if (/^no codebook name/.test(reason)) return { section: 'basics', field: 'name' };
  const m = reason.match(/^category (\S+) has/);
  if (m) return { section: 'categories', cat: m[1] };
  if (/categor/.test(reason)) return { section: 'categories' };
  if (/item|moment/.test(reason)) return { section: 'moments' };
  return { section: 'basics' };
}

function paintCheck() {
  const { valid, reasons } = check;
  const placed = reasons.map((r) => ({ r, ...placeOf(r) }));
  for (const el of document.querySelectorAll('.field[data-field]')) {
    const mine = placed.filter((p) => p.field === el.dataset.field).map((p) => p.r);
    el.classList.toggle('invalid', mine.length > 0);
    const err = el.querySelector('.err');
    if (err) err.textContent = mine.join(' · ');
  }
  for (const el of document.querySelectorAll('.catc')) {
    const mine = placed.filter((p) => p.cat === el.dataset.cat).map((p) => p.r.replace(/^category \S+ /, ''));
    el.classList.toggle('invalid', mine.length > 0);
    el.querySelector('.cerr').textContent = mine.join(' · ');
  }
  for (const s of ['basics', 'categories', 'moments']) {
    const list = placed.filter((p) => p.section === s);
    const loose = list.filter((p) => !p.field && !p.cat);
    const box = document.querySelector(`[data-problems="${s}"]`);
    if (box) box.innerHTML = loose.length ? `<div class="problems" style="margin:0"><ul class="reasons">${loose.map((p) => `<li>${esc(p.r)}</li>`).join('')}</ul></div>` : '';
    const badge = document.querySelector(`[data-badge="${s}"]`);
    if (badge) { badge.className = `badge ${list.length ? 'has' : 'good'}`; badge.textContent = list.length ? `${list.length} to fix` : '✓'; }
  }

  $('statusSlot').innerHTML = valid
    ? '<button class="status ok" id="validity">Valid — ready to save</button>'
    : `<button class="status bad" id="validity">${reasons.length} problem${reasons.length === 1 ? '' : 's'}</button>`;
  $('btnSave').disabled = !valid;
  $('btnSave').innerHTML = `Save <span class="mono">${esc(cb.codebook_id)}</span>`;
  const problems = $('problemsHost');
  if (problems) {
    problems.innerHTML = valid ? '' : `<div class="problems"><div class="ph">Fix ${reasons.length === 1 ? 'this' : `these ${reasons.length}`} before saving</div>
      <ul class="reasons">${placed.map((p) => `<li data-jump="${p.section}"><span>${p.section}</span>${esc(p.r)}</li>`).join('')}</ul></div>`;
  }

  // Which version this is, and what saving would leave behind.
  const mine = versions.filter((v) => v.codebook_id === cb.codebook_id);
  const same = mine.find((v) => v.content_hash === check.content_hash);
  const coded = mine.filter((v) => v !== same).reduce((n, v) => n + (v.n_label_sets ?? 0), 0);
  const line = $('versionLine');
  if (line) {
    line.innerHTML = !check.content_hash ? 'Version hash appears once the codebook can be read.'
      : same ? `This is saved version <span class="mono">${esc(same.content_hash)}</span>${same.n_label_sets
        ? ` · ${same.n_label_sets} label set${same.n_label_sets === 1 ? '' : 's'} filed under it` : ''}.`
      : `Would be saved as version <span class="mono">${esc(check.content_hash)}</span>${mine.length
        ? ` — a new version of <code>${esc(cb.codebook_id)}</code>. ${coded
          ? `The ${coded} label set${coded === 1 ? '' : 's'} under earlier versions stay with them and are never pooled with this one; raters start this version afresh.`
          : 'Nobody has coded the earlier versions yet.'}` : '.'}`;
  }
  const rh = $('raterHash');
  if (rh) rh.textContent = check.content_hash ?? '';
  $('dirty').hidden = savedAs !== null && JSON.stringify(cb) === savedAs;
  if (savedAs === null) $('dirty').hidden = !(cb.items?.length || cb.categories?.some((c) => c.description));
}

// ---------------------------------------------------------------------------
// edits
// ---------------------------------------------------------------------------

function edited() { setBanner(''); }

document.addEventListener('input', (ev) => {
  const k = ev.target.dataset?.k;
  if (!k) return;
  const v = ev.target.value;
  const m = k.match(/^cat\.(\d+)\.(label|id|description)$/);
  if (m) {
    const c = cb.categories[Number(m[1])];
    if (m[2] === 'label' && c.id === categoryIdFrom(c.label, cb.categories.filter((x) => x !== c).map((x) => x.id))) {
      // The id follows the label until someone edits the id itself.
      c.id = categoryIdFrom(v, cb.categories.filter((x) => x !== c).map((x) => x.id));
      const idInput = document.querySelector(`[data-k="cat.${m[1]}.id"]`);
      if (idInput) idInput.value = c.id;
      ev.target.closest('.catc').dataset.cat = c.id;
    }
    c[m[2]] = v;
    if (m[2] === 'id') ev.target.closest('.catc').dataset.cat = v;
  } else {
    cb[k] = v;
  }
  edited();
  refreshSideSoon();
  scheduleCheck();
});

let sideTimer = null;
function refreshSideSoon() {
  clearTimeout(sideTimer);
  sideTimer = setTimeout(renderSide, 120);
}

function said(html) { const el = $('addSaid'); if (el) el.innerHTML = html; }

let paintLine = () => {};

/** After the moments change: the list, the side and the check — not the whole form. */
function momentsChanged() {
  edited();
  $('mlistHost').innerHTML = momentsListHtml();
  renderSide();
  scheduleCheck();
  paintLine();
}

function addMoments(add, what) {
  const { items, repeats } = mergeItems(cb.items ?? [], add);
  const n = items.length - (cb.items ?? []).length;
  cb.items = items;
  momentsChanged();
  said(`<span class="ok">Added ${n} moment${n === 1 ? '' : 's'}${what ? ` ${what}` : ''}.</span>${repeats ? ` <span class="muted">${repeats} already there, skipped.</span>` : ''}`);
}

document.addEventListener('click', (ev) => {
  const el = ev.target.closest('button, [data-jump]');
  if (!el) return;
  const d = el.dataset;
  const num = (id) => Number($(id).value);
  try {
    if (d.tab) { sideTab = d.tab; showTab(); }
    else if (d.addtab) { addTab = d.addtab; render(); if (addTab === 'video' && pickSession) loadPlayer(); }
    else if (d.jump) $(`sec-${d.jump}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    else if (d.preview) { previewAt += Number(d.preview); renderSide(); }
    else if (d.open) openVersion(...d.open.split('|'));
    else if (d.cmove !== undefined) {
      const i = Number(d.cmove); const j = i + Number(d.dir);
      [cb.categories[i], cb.categories[j]] = [cb.categories[j], cb.categories[i]];
      edited(); render();
    } else if (d.cremove !== undefined) { cb.categories.splice(Number(d.cremove), 1); edited(); render(); }
    else if (d.mremove !== undefined) { cb.items.splice(Number(d.mremove), 1); momentsChanged(); }
    else if (el.id === 'btnAddCat') {
      cb.categories.push({ id: categoryIdFrom('category', cb.categories.map((c) => c.id)), label: '', description: '' });
      edited(); render();
      document.querySelector(`[data-k="cat.${cb.categories.length - 1}.label"]`)?.focus();
    } else if (el.id === 'btnSort') { cb.items = [...cb.items].sort((a, b) => a - b); momentsChanged(); }
    else if (el.id === 'btnShuffle') { cb.items = shuffle(cb.items, num('shuffleSeed')); momentsChanged(); }
    else if (el.id === 'btnClear') { cb.items = []; momentsChanged(); }
    else if (el.id === 'btnAddTyped') {
      const { ms, bad } = parseTimes($('typeTimes').value);
      if (bad.length) { said(`<span class="bad">Could not read: ${bad.map(esc).join(', ')}.</span> Nothing was added.`); return; }
      if (!ms.length) { said('<span class="muted">Type some times first.</span>'); return; }
      addMoments(ms, 'as typed');
    } else if (el.id === 'btnAddGrid') addMoments(gridTimes(num('gFrom'), num('gTo'), num('gEvery')), `every ${num('gEvery')} s`);
    else if (el.id === 'btnAddRandom') {
      addMoments(sampleTimes(num('rFrom'), num('rTo'), num('rN'), num('rGap'), num('rSeed')), `at random (seed ${num('rSeed')})`);
    } else if (el.id === 'btnAddHere') {
      const v = $('pickVideo');
      addMoments([Math.round(v.currentTime * 1000)], `at ${fmtTime(Math.round(v.currentTime * 1000))}`);
    } else if (el.id === 'btnApplyJson') {
      try { cb = strip(JSON.parse($('json').value)); edited(); render(); } catch (err) { $('jsonError').textContent = `not JSON: ${err.message}`; }
    } else if (el.id === 'btnSave') save();
    else if (el.id === 'btnDismiss') setBanner('');
    else if (el.id === 'validity' && check.reasons.length) {
      $(`sec-${placeOf(check.reasons[0]).section}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (err) {
    said(`<span class="bad">${esc(err.message)}</span>`);
  }
});

document.addEventListener('change', (ev) => {
  if (ev.target.id === 'pickSession') { pickSession = ev.target.value; loadPlayer(); }
});

// ---------------------------------------------------------------------------
// picking moments from a recording
// ---------------------------------------------------------------------------

async function loadPlayer(at = 0) {
  const host = $('pickHost');
  if (!host) return;
  if (!pickSession) { host.innerHTML = ''; return; }
  const url = `/api/sessions/${encodeURIComponent(pickSession)}/media`;
  // Ask first, so a refusal is shown as what it is — the participant did not
  // keep the recording, or the app has no media folder — not as a black box.
  const probe = await fetch(url, { headers: { Range: 'bytes=0-0' } });
  if (!probe.ok) {
    let detail = `${probe.status}`;
    try { detail = (await probe.json()).detail ?? detail; } catch { /* not JSON */ }
    host.innerHTML = `<div class="note bad">This recording cannot be played: ${esc(detail)}.</div>`;
    return;
  }
  host.innerHTML = `<video id="pickVideo" controls preload="metadata" src="${url}"></video>
    <div class="timeline" id="pickLine" title="Your moments; click to jump"></div>
    <div class="inline"><button class="primary" id="btnAddHere">Add this moment</button>
      <span class="muted" id="pickAt"></span></div>`;
  const v = $('pickVideo');
  const line = $('pickLine');
  const paint = () => {
    if (!v.isConnected) return;
    const dur = v.duration;
    if (!Number.isFinite(dur) || dur <= 0) return;
    line.innerHTML = (cb.items ?? []).map((t) => `<i style="left:${Math.min(100, (t / 1000 / dur) * 100)}%"></i>`).join('')
      + `<b style="left:${(v.currentTime / dur) * 100}%"></b>`;
    $('pickAt').textContent = `at ${fmtTime(Math.round(v.currentTime * 1000))} of ${fmtTime(Math.round(dur * 1000))}`;
  };
  paintLine = paint;
  v.addEventListener('loadedmetadata', () => { if (at) v.currentTime = at; paint(); });
  v.addEventListener('timeupdate', paint);
  line.addEventListener('click', (e) => {
    const r = line.getBoundingClientRect();
    if (Number.isFinite(v.duration)) v.currentTime = ((e.clientX - r.left) / r.width) * v.duration;
  });
}

// ---------------------------------------------------------------------------
// opening and saving
// ---------------------------------------------------------------------------

function setBanner(html, tone = '') {
  const el = $('saveResult');
  el.className = `banner ${tone}`;
  el.innerHTML = html ? `${html}<button class="icon x" id="btnDismiss" title="Dismiss" aria-label="Dismiss">✕</button>` : '';
  el.hidden = !html;
}

async function save() {
  const before = versions.some((v) => v.codebook_id === cb.codebook_id && v.content_hash === check.content_hash);
  const res = await fetch('/api/codebooks', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(cb) });
  const body = await res.json();
  if (!res.ok) { setBanner(`<p class="bad">${esc(body.detail ?? body.error)}</p>`, 'bad'); return; }
  cb = strip(body);
  savedAs = JSON.stringify(cb);
  await loadVersions(`${body.codebook_id}|${body.content_hash}`);
  render();
  setBanner(`<p>${before ? `<b>Unchanged</b> — this is already version <span class="mono">${esc(body.content_hash)}</span>.`
    : `<span class="ok"><b>Saved ${esc(body.codebook_id)}</b></span>, version <span class="mono">${esc(body.content_hash)}</span>.`}
    Raters choose it on the <a href="./annotate.html?codebook=${encodeURIComponent(body.codebook_id)}">Annotate page</a>.</p>`, before ? '' : 'ok');
}

async function openVersion(id, hash) {
  setBanner('');
  if (!id) { cb = blankCodebook(); savedAs = null; }
  else {
    const res = await fetch(`/api/codebooks/${encodeURIComponent(id)}?version=${encodeURIComponent(hash)}`, { cache: 'no-store' });
    cb = strip(await res.json());
    savedAs = JSON.stringify(cb);
  }
  $('openCb').value = id ? `${id}|${hash}` : '';
  previewAt = 0;
  $('form').scrollTop = 0;
  render();
}

async function loadVersions(selected = $('openCb').value) {
  versions = (await (await fetch('/api/codebooks', { cache: 'no-store' })).json()).codebooks ?? [];
  $('openCb').innerHTML = `<option value="">New codebook</option>${versions.map((v) => `<option value="${esc(v.codebook_id)}|${esc(v.content_hash)}">
    ${esc(v.codebook_id)} · ${esc(v.content_hash.slice(0, 8))} · ${esc((v.created_utc ?? '').slice(0, 10))}${v.n_label_sets ? ` · ${v.n_label_sets} coded` : ''}</option>`).join('')}`;
  $('openCb').value = versions.some((v) => `${v.codebook_id}|${v.content_hash}` === selected) ? selected : '';
}

$('openCb').addEventListener('change', (ev) => openVersion(...(ev.target.value ? ev.target.value.split('|') : [''])));
window.addEventListener('beforeunload', (ev) => { if (!$('dirty').hidden) ev.preventDefault(); });

async function start() {
  const [, s] = await Promise.all([loadVersions(), fetch('/api/sessions', { cache: 'no-store' }).then((r) => r.json())]);
  sessions = s.sessions ?? [];
  const want = new URLSearchParams(location.search).get('codebook');
  const latest = want && versions.find((v) => v.codebook_id === want);
  if (latest) await openVersion(latest.codebook_id, latest.content_hash);
  else render();
}

start();

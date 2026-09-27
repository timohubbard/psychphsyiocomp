/**
 * The study builder.
 *
 * Validation, the content hash, the task sequence and the consent text come
 * from the capture page's own modules (served read-only at /src/), so what
 * this page calls valid is exactly what a participant's page will accept, and
 * the consent preview is the text they will read. Saving goes through
 * server/study_store.py, which re-validates in Python and refuses to edit a
 * study anyone has already been recorded under.
 */

import { MODALITIES, SPECIAL_CATEGORY_MODALITIES, BROWSER_MODALITIES, contentHash,
  protocolFor, validateStudy } from '/src/study.js';
import { CONSENT_TIERS, analysisNotice, joinAnd, withdrawalText } from '/src/consent.js';
import { buildSequence, estimateDurationMs } from '/src/sequence.js';
import { TASK_TYPES, blankStudy, getPath, parseList, setPath, stimulusIdFrom,
  summarise } from './builder_model.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const has = (arr, v) => Array.isArray(arr) && arr.includes(v);

let study = blankStudy();

// ---------------------------------------------------------------------------
// form controls — each carries its path; see onInput
// ---------------------------------------------------------------------------

function field(label, path, { type = 'text', required = false, help = '', rows = 0 } = {}) {
  const v = getPath(study, path);
  const p = esc(JSON.stringify(path));
  const control = rows
    ? `<textarea data-path="${p}" data-type="${type}" rows="${rows}">${esc(v ?? '')}</textarea>`
    : `<input data-path="${p}" data-type="${type}" type="${type === 'number' ? 'number' : 'text'}"
         value="${esc(v ?? '')}">`;
  return `<label class="f"><span class="${required ? 'req' : ''}">${label}</span>
    <div>${control}${help ? `<div class="muted">${help}</div>` : ''}</div></label>`;
}

function check(label, path, value, note = '') {
  const arr = getPath(study, path) ?? [];
  return `<label class="check"><input type="checkbox" data-list="${esc(JSON.stringify(path))}"
    data-value="${esc(value)}" ${has(arr, value) ? 'checked' : ''}>
    <span>${label}${note ? `<small>${note}</small>` : ''}</span></label>`;
}

function render() {
  const d = study.disclosure ?? {};
  const participants = study.audience === 'participants';
  const special = (study.modalities ?? []).some((m) => SPECIAL_CATEGORY_MODALITIES.includes(m));
  const arms = study.conditions?.arms ?? [];
  const gaze = has(study.modalities, 'gaze');

  $('form').innerHTML = `
    <fieldset><legend>Identity</legend>
      ${field('Study id', ['study_id'], { required: true, help: 'letters, digits, - and _ — the ?study= in the link' })}
      ${field('Name', ['name'], { required: true })}
      ${field('Version', ['version'], { required: true })}
      <label class="f"><span>Who it may be run on</span><div>
        <select id="audience">
          <option value="" ${participants ? '' : 'selected'}>Developer self-test (no ethics approval)</option>
          <option value="participants" ${participants ? 'selected' : ''}>Participants (ethics approved)</option>
        </select>
        <div class="muted">Participants need the starred fields below; the capture page refuses the study without them.</div>
      </div></label>
    </fieldset>

    <fieldset><legend>What participants are told</legend>
      ${field('Retention (days)', ['disclosure', 'retention_days'], { type: 'number', required: true, help: 'at most 1095; deleted by the scheduled sweep' })}
      ${field('Who sees the data', ['disclosure', 'secondary_use'], { required: true, rows: 2 })}
      ${field('Contact', ['disclosure', 'contact'], { required: true, rows: 2, help: participants ? 'must contain an email or web address' : '' })}
      ${field('Ethics reference (REC/IRB)', ['disclosure', 'irb_reference'], { required: participants })}
      ${field('Data controller', ['disclosure', 'controller'], { required: participants })}
      ${field('Lawful basis (Art 6)', ['disclosure', 'lawful_basis'], { required: participants })}
      ${field('Special category basis (Art 9)', ['disclosure', 'special_category_basis'], { required: participants && special,
        help: special ? 'face, voice and respiration are treated as special-category data' : '' })}
    </fieldset>

    <fieldset><legend>What is measured</legend>
      ${MODALITIES.map((m) => check(m.label, ['modalities'], m.id, m.note)).join('')}
      ${gaze ? `${field('Calibration points', ['calibration', 'n_points'], { type: 'number', help: '5–13' })}
        <label class="check"><input type="checkbox" id="randomise" ${study.calibration?.randomise_order === false ? '' : 'checked'}>
        <span>Randomise calibration order <small>fixed order confounds target with time</small></span></label>` : ''}
    </fieldset>

    <fieldset><legend>Consent tiers offered</legend>
      ${CONSENT_TIERS.map((t) => check(t.label, ['consent_tiers'], t.id,
        t.id === 'features_in_browser' ? `only with ${joinAnd(BROWSER_MODALITIES)}` : t.summary)).join('')}
      <label class="f"><span>Pre-selected tier</span><div><select id="defaultTier">
        ${(study.consent_tiers ?? []).map((t) => `<option ${study.default_tier === t ? 'selected' : ''}>${esc(t)}</option>`).join('')}
      </select></div></label>
    </fieldset>

    <fieldset><legend>Tasks, in order</legend>
      ${(study.tasks ?? []).map((t, i) => taskCard(t, i, arms)).join('') || '<div class="muted">No tasks yet.</div>'}
      <div class="row"><select id="addTask">${Object.entries(TASK_TYPES)
        .map(([k, v]) => `<option value="${k}">${esc(v.label)}</option>`).join('')}</select>
        <button id="btnAddTask">Add task</button></div>
    </fieldset>

    <fieldset><legend>Conditions and recruitment</legend>
      <label class="f"><span>Between-subject arms</span><div>
        <input id="arms" value="${esc(arms.join(', '))}" placeholder="e.g. A, B — leave empty for none">
        <div class="muted">Each participant is assigned one at random; tasks can be limited to arms.</div></div></label>
      ${field('Completion link', ['recruitment', 'completion_url'], { help: 'e.g. Prolific’s …/submissions/complete?cc=CODE (https)' })}
    </fieldset>

    <fieldset><legend>Analysis plan</legend>
      ${field('AOI padding (degrees)', ['analysis', 'aoi_pad_deg'], { type: 'number', help: 'required for AOI metrics — there is no default' })}
      ${field('Heatmap blur (degrees)', ['analysis', 'heatmap_sigma_deg'], { type: 'number', help: 'default 1' })}
      <div class="muted" style="margin:8px 0 4px">Exclusions — a session must meet each, or is excluded</div>
      ${(study.analysis?.exclusions ?? []).map((e, i) => `<div class="row">
        <input data-path='${esc(JSON.stringify(['analysis', 'exclusions', i, 'metric']))}' value="${esc(e.metric)}" placeholder="metric, e.g. achieved_fps">
        <input data-path='${esc(JSON.stringify(['analysis', 'exclusions', i, 'min']))}' data-type="number" type="number" value="${esc(e.min ?? '')}" placeholder="min">
        <input data-path='${esc(JSON.stringify(['analysis', 'exclusions', i, 'max']))}' data-type="number" type="number" value="${esc(e.max ?? '')}" placeholder="max">
        <button data-remove='${esc(JSON.stringify(['analysis', 'exclusions', i]))}'>✕</button></div>`).join('')}
      <button id="btnAddExclusion">Add exclusion</button>
      <div class="muted" style="margin:10px 0 4px">Epochs — cut around each event, baseline-corrected</div>
      ${(study.analysis?.epochs ?? []).map((e, i) => epochRow(e, i)).join('')}
      <button id="btnAddEpoch">Add epoch set</button>
    </fieldset>`;
  return refresh();
}

function taskCard(t, i, arms) {
  const at = (...rest) => ['tasks', i, ...rest];
  let body = '';
  if (t.type === 'rest_fixation') body = field('Duration (ms)', at('duration_ms'), { type: 'number' });
  if (t.type === 'free_speech') body = field('Duration (ms)', at('duration_ms'), { type: 'number' });
  if (t.type === 'expression_prompts') {
    body = field('Repeats', at('repeats'), { type: 'number' }) + field('Hold (ms)', at('hold_ms'), { type: 'number' });
  }
  if (t.type === 'stimuli') body = stimuliBody(t, i);
  const armBoxes = arms.length ? `<div class="muted">Only for arms:
    ${arms.map((a) => check(a, at('arms'), a)).join('')}</div>` : '';
  return `<div class="task"><div class="head"><b>${i + 1}. ${esc(TASK_TYPES[t.type]?.label ?? t.type)}</b>
      <button data-move="${i}" data-dir="-1">↑</button><button data-move="${i}" data-dir="1">↓</button>
      <button data-remove='${esc(JSON.stringify(['tasks', i]))}'>✕</button></div>${body}${armBoxes}</div>`;
}

function stimuliBody(t, i) {
  const at = (...rest) => ['tasks', i, ...rest];
  const items = (t.items ?? []).map((it, j) => `<div class="row">
      <input data-path='${esc(JSON.stringify(at('items', j, 'stimulus_id')))}' value="${esc(it.stimulus_id)}" title="stimulus id">
      <span class="mono" title="${esc(it.sha256)}">${esc(it.kind)} · ${esc(it.src)}</span>
      <input data-path='${esc(JSON.stringify(at('items', j, 'duration_ms')))}' data-type="number" type="number" value="${esc(it.duration_ms)}" title="duration (ms)">
      <button data-remove='${esc(JSON.stringify(at('items', j)))}'>✕</button></div>`).join('');
  return `${field('Gap between (ms)', at('isi_ms'), { type: 'number' })}
    <label class="check"><input type="checkbox" data-bool='${esc(JSON.stringify(at('randomise')))}' ${t.randomise === false ? '' : 'checked'}>
      <span>Shuffle order per participant</span></label>
    ${items || '<div class="muted">No pictures or videos yet.</div>'}
    <div class="row"><input type="file" data-upload="${i}" accept=".png,.jpg,.jpeg,.webp,.webm,.mp4">
      <span class="muted" id="upload-${i}"></span></div>`;
}

function epochRow(e, i) {
  const at = (k) => esc(JSON.stringify(['analysis', 'epochs', i, k]));
  return `<div class="task">
    <div class="row"><input data-path='${at('name')}' value="${esc(e.name)}" placeholder="name">
      <input data-path='${at('event_type')}' value="${esc(e.event_type)}" placeholder="event type, e.g. stimulus">
      <button data-remove='${esc(JSON.stringify(['analysis', 'epochs', i]))}'>✕</button></div>
    <div class="row"><input data-csv='${at('channels')}' value="${esc((e.channels ?? []).join(', '))}" placeholder="channels, comma-separated">
      <input data-path='${at('source')}' value="${esc(e.source ?? '')}" placeholder="source (if a channel has several)"></div>
    <div class="row"><input data-path='${at('pre_ms')}' data-type="number" type="number" value="${esc(e.pre_ms)}" placeholder="pre ms">
      <input data-path='${at('post_ms')}' data-type="number" type="number" value="${esc(e.post_ms)}" placeholder="post ms">
      <input data-path='${at('resample_hz')}' data-type="number" type="number" value="${esc(e.resample_hz ?? '')}" placeholder="Hz (30)"></div>
    <div class="row"><span class="muted">baseline from / to (ms)</span>
      <input data-path='${esc(JSON.stringify(['analysis', 'epochs', i, 'baseline_ms', 0]))}' data-type="number" type="number" value="${esc(e.baseline_ms?.[0] ?? '')}">
      <input data-path='${esc(JSON.stringify(['analysis', 'epochs', i, 'baseline_ms', 1]))}' data-type="number" type="number" value="${esc(e.baseline_ms?.[1] ?? '')}"></div></div>`;
}

// ---------------------------------------------------------------------------
// edits
// ---------------------------------------------------------------------------

function onInput(ev) {
  const el = ev.target;
  if (el.dataset.path) {
    const path = JSON.parse(el.dataset.path);
    const raw = el.value;
    const value = raw.trim() === '' ? undefined
      : el.dataset.type === 'number' ? Number(raw) : raw;
    setPath(study, path, value);
    tidy();
    refresh();
  } else if (el.dataset.csv) {
    const list = parseList(el.value);
    setPath(study, JSON.parse(el.dataset.csv), list.length ? list : undefined);
    refresh();
  }
}

function onChange(ev) {
  const el = ev.target;
  if (el.dataset.list) {
    const path = JSON.parse(el.dataset.list);
    const arr = [...(getPath(study, path) ?? [])];
    const v = el.dataset.value;
    const next = el.checked ? [...new Set([...arr, v])] : arr.filter((x) => x !== v);
    setPath(study, path, next.length || path[0] !== 'tasks' ? next : undefined);
    if (path[0] === 'consent_tiers' && !next.includes(study.default_tier)) study.default_tier = next[0];
    if (path[0] === 'modalities' && next.includes('gaze') && !study.calibration) {
      study.calibration = { n_points: 13, randomise_order: true };
    }
    return render();
  }
  if (el.dataset.bool) {
    setPath(study, JSON.parse(el.dataset.bool), el.checked ? undefined : false);
    return refresh();
  }
  if (el.dataset.upload !== undefined) return upload(el, Number(el.dataset.upload));
  if (el.id === 'audience') {
    setPath(study, ['audience'], el.value || undefined);
    return render();
  }
  if (el.id === 'defaultTier') { study.default_tier = el.value; return refresh(); }
  if (el.id === 'randomise') { setPath(study, ['calibration', 'randomise_order'], el.checked); return refresh(); }
  if (el.id === 'arms') {
    const arms = parseList(el.value);
    setPath(study, ['conditions'], arms.length ? { arms } : undefined);
    for (const t of study.tasks ?? []) if (!arms.length) delete t.arms;
    return render();
  }
  return undefined;
}

function onClick(ev) {
  const el = ev.target.closest('button');
  if (!el) return;
  if (el.dataset.remove) {
    setPath(study, JSON.parse(el.dataset.remove), undefined);
    tidy();
    render();
  } else if (el.dataset.move !== undefined) {
    const i = Number(el.dataset.move);
    const j = i + Number(el.dataset.dir);
    if (j < 0 || j >= study.tasks.length) return;
    [study.tasks[i], study.tasks[j]] = [study.tasks[j], study.tasks[i]];
    render();
  } else if (el.id === 'btnAddTask') {
    study.tasks = [...(study.tasks ?? []), TASK_TYPES[$('addTask').value].make()];
    render();
  } else if (el.id === 'btnAddExclusion') {
    setPath(study, ['analysis', 'exclusions'], [...(study.analysis?.exclusions ?? []), { metric: 'achieved_fps', min: 5 }]);
    render();
  } else if (el.id === 'btnAddEpoch') {
    setPath(study, ['analysis', 'epochs'], [...(study.analysis?.epochs ?? []),
      { name: `epochs_${(study.analysis?.epochs ?? []).length + 1}`, event_type: 'stimulus',
        channels: ['blendshape.mouthSmileLeft'], pre_ms: 500, post_ms: 3000, baseline_ms: [-500, 0] }]);
    render();
  } else if (el.id === 'btnApplyJson') {
    try {
      study = JSON.parse($('json').value);
      render();
    } catch (err) {
      $('jsonError').textContent = `not JSON: ${err.message}`;
    }
  } else if (el.id === 'btnSave') {
    save(false);
  } else if (el.id === 'btnOverwrite') {
    save(true);
  } else if (el.id === 'btnSaveAs') {
    study.study_id = el.dataset.id;
    // The re-render rebuilds the side panel after an await (the hash); saving
    // before it lands would have the panel wipe the save result it just wrote.
    render().then(() => save(false));
  }
}

/** Drop containers an edit left empty, so they do not reach the file. */
function tidy() {
  if (study.recruitment && !Object.keys(study.recruitment).length) delete study.recruitment;
  if (study.analysis) {
    for (const k of ['exclusions', 'epochs']) if (study.analysis[k]?.length === 0) delete study.analysis[k];
    if (!Object.keys(study.analysis).length) delete study.analysis;
  }
  if (study.disclosure && study.disclosure.irb_reference === undefined) study.disclosure.irb_reference = null;
}

async function upload(input, taskIndex) {
  const file = input.files?.[0];
  const status = $(`upload-${taskIndex}`);
  if (!file) return;
  status.textContent = `uploading ${file.name}…`;
  const res = await fetch(`/api/stimuli?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
  const body = await res.json();
  if (!res.ok) { status.innerHTML = `<span class="bad">${esc(body.detail ?? body.error)}</span>`; return; }
  const task = study.tasks[taskIndex];
  task.items = [...(task.items ?? []), {
    stimulus_id: stimulusIdFrom(file.name), kind: body.kind, src: body.src, sha256: body.sha256,
    duration_ms: 4000,
  }];
  render();
}

// ---------------------------------------------------------------------------
// the live side panel
// ---------------------------------------------------------------------------

async function refresh() {
  const { valid, reasons } = validateStudy(study);
  let hash = '';
  try { hash = await contentHash(study); } catch { /* shown as blank */ }

  let seqHtml = '';
  const arms = study.conditions?.arms?.length ? study.conditions.arms : [null];
  for (const arm of arms) {
    try {
      const seq = buildSequence(study, 1, { condition: arm });
      seqHtml += `<div class="muted">${arm ? `arm ${esc(arm)} · ` : ''}about ${Math.round(estimateDurationMs(seq) / 60000 * 10) / 10} min</div>
        <table class="seq">${summarise(seq).map((r) => `<tr><td>${esc(r.type)}</td><td class="mono">${r.n}</td></tr>`).join('')}</table>`;
    } catch (err) {
      seqHtml += `<div class="bad">${esc(err.message)}</div>`;
    }
  }

  let consentHtml = '<div class="muted">Shown once the study is valid.</div>';
  if (valid) {
    try {
      const p = protocolFor(study, { condition: arms[0] });
      const d = p.disclosure;
      const doing = p.activity.doing.length ? ` while you ${joinAnd(p.activity.doing)}` : '';
      consentHtml = `<div class="preview">
        ${d.audience === 'participants' ? '' : '<p class="bad"><b>Developer self-test.</b> Not for participants.</p>'}
        <p>This session records ${esc(p.activity.records)} from your ${esc(p.activity.devices)}${esc(doing)}.</p>
        ${p.activity.measures.length ? `<p><b>Automated analysis.</b> ${esc(analysisNotice(p.activity.measures))}</p>` : ''}
        ${p.tiers.map((t) => `<div class="tier"><b>${esc(t.label)}</b> — ${esc(t.summary)}
          <ul>${t.keeps.map((k) => `<li>${esc(k)}</li>`).join('')}</ul></div>`).join('')}
        <p class="muted">Kept for ${esc(d.retentionDays)} days. Who else sees it: ${esc(d.secondaryUse)}<br>
          Contact: ${esc(d.contact)}${d.controller ? `<br>Responsible for your data: ${esc(d.controller)}` : ''}
          ${d.lawfulBasis ? `<br>Legal basis: ${esc(d.lawfulBasis)}${d.specialCategoryBasis ? `; ${esc(d.specialCategoryBasis)}` : ''}` : ''}
          ${d.irbReference ? `<br>Approved under ${esc(d.irbReference)}.` : ''}</p>
        <p class="muted">${esc(withdrawalText(d.retentionDays))}</p></div>`;
    } catch (err) {
      consentHtml = `<div class="bad">${esc(err.message)}</div>`;
    }
  }

  $('side').innerHTML = `
    <h2>Check</h2>
    ${valid ? `<div class="ok" id="validity">Valid — the capture page will accept this study.</div>`
      : `<div class="bad" id="validity">${reasons.length} problem(s):</div><ul class="reasons">${reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`}
    <div class="muted">content hash <span class="mono" id="hash">${esc(hash)}</span></div>
    <p><button class="primary" id="btnSave" ${valid ? '' : 'disabled'}>Save studies/${esc(study.study_id)}.json</button></p>
    <div id="saveResult"></div>
    <h2>What participants do</h2>${seqHtml}
    <h2>What participants are told</h2>${consentHtml}
    <h2>JSON</h2>
    <textarea id="json">${esc(JSON.stringify(study, null, 2))}</textarea>
    <div class="row"><button id="btnApplyJson">Apply edited JSON</button><span class="bad" id="jsonError"></span></div>`;
}

async function save(overwrite) {
  const out = $('saveResult');
  out.textContent = 'saving…';
  const res = await fetch('/api/studies', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ study, overwrite }),
  });
  const body = await res.json();
  if (res.ok) {
    out.innerHTML = `<span class="ok">Saved ${esc(body.saved)}</span> · hash <span class="mono">${esc(body.content_hash)}</span><br>
      <span class="muted">Participant link (with <code>npm run serve</code>):
      <code>http://localhost:5173/?study=${esc(body.study_id)}</code> · records of processing:
      <code>npm run ropa -- ${esc(body.study_id)}</code> · commit the file to version it.</span>`;
    loadList();
    return;
  }
  if (body.sessions) {
    out.innerHTML = `<span class="bad">${esc(body.detail)}</span><br>
      <button id="btnSaveAs" data-id="${esc(body.suggestion)}">Save as ${esc(body.suggestion)} instead</button>`;
  } else if (body.can_overwrite) {
    out.innerHTML = `<span class="warn">${esc(body.detail)}</span><br>
      <button id="btnOverwrite">Overwrite the draft</button>`;
  } else {
    out.innerHTML = `<span class="bad">${esc(body.detail ?? body.error)}</span>
      ${body.reasons ? `<ul class="reasons">${body.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}`;
  }
}

// ---------------------------------------------------------------------------
// start
// ---------------------------------------------------------------------------

async function loadList() {
  const { studies } = await (await fetch('/api/studies', { cache: 'no-store' })).json();
  $('startFrom').innerHTML = `<option value="">— blank study —</option>${studies
    .map((s) => `<option value="${esc(s.study_id)}">${esc(s.study_id)}${s.valid ? '' : ' (invalid)'}</option>`).join('')}`;
}

$('startFrom').addEventListener('change', async (ev) => {
  const id = ev.target.value;
  if (!id) { study = blankStudy(); return render(); }
  const res = await fetch(`/api/studies/${encodeURIComponent(id)}`, { cache: 'no-store' });
  const body = await res.json();
  study = body.study ?? blankStudy();
  return render();
});

for (const el of [$('form'), $('side')]) {
  el.addEventListener('input', onInput);
  el.addEventListener('change', onChange);
  el.addEventListener('click', onClick);
}

loadList();
render();

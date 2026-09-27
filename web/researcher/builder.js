/**
 * The study builder.
 *
 * Validation, the content hash, the task sequence and the consent text come
 * from the capture page's own modules (served read-only at /src/), so what
 * this page calls valid is exactly what a participant's page will accept, and
 * the consent preview is the text they will read. Saving goes through
 * server/study_store.py, which re-validates in Python and refuses to edit a
 * study anyone has already been recorded under.
 *
 * Layout: sections down the middle, a rail of them on the left with each
 * one's problem count, and on the right what the study adds up to — the
 * problems in full, the participant's journey, the consent screen, the JSON.
 * A problem is shown where it is fixed: under its field when it names one,
 * otherwise at the foot of its section (builder_model.sectionOf / fieldOf).
 */

import { MODALITIES, SPECIAL_CATEGORY_MODALITIES, BROWSER_MODALITIES, contentHash,
  protocolFor, validateStudy } from '/src/study.js';
import { CONSENT_TIERS, analysisNotice, joinAnd, withdrawalText } from '/src/consent.js';
import { buildSequence, estimateDurationMs, wantsChinrest } from '/src/sequence.js';
import { METRIC_SUGGESTIONS, SECTIONS, TASK_TYPES, blankStudy, fieldOf, getPath, parseList,
  sectionOf, setPath, stimulusIdFrom } from './builder_model.js';
import { KINDS, flowModels } from './flow.js';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const has = (arr, v) => Array.isArray(arr) && arr.includes(v);
const pathAttr = (path) => esc(JSON.stringify(path));

/** A measure's colour: the journey's colour for what it produces. */
const MODALITY_COLOR = { gaze: KINDS.gaze.color, face: KINDS.face.color, voice: KINDS.voice.color, respiration: '#2bb3c0' };

let study = blankStudy();
let savedAs = JSON.stringify(study);   // what is on disk, to tell "unsaved changes"
let sideTab = 'journey';
let reasonsNow = [];

// ---------------------------------------------------------------------------
// controls — each carries its path; see onInput / onChange
// ---------------------------------------------------------------------------

function field(label, path, { type = 'text', required = false, help = '', rows = 0, placeholder = '', suffix = '', cls = '' } = {}) {
  const v = getPath(study, path);
  const attrs = `data-path="${pathAttr(path)}" data-type="${type}"${placeholder ? ` placeholder="${esc(placeholder)}"` : ''}`;
  const control = rows
    ? `<textarea ${attrs} rows="${rows}">${esc(v ?? '')}</textarea>`
    : `<input ${attrs} type="${type === 'number' ? 'number' : 'text'}" value="${esc(v ?? '')}">`;
  return `<div class="field ${cls}" data-field="${esc(path.join('.'))}"><label>
      <span class="lbl">${label}${required ? '<em class="req">required</em>' : ''}</span>
      ${suffix ? `<span class="suffix">${control}<i>${suffix}</i></span>` : control}</label>
    ${help ? `<div class="help">${help}</div>` : ''}<div class="err"></div></div>`;
}

/** A card that adds or removes `value` in the list at `path`. */
function optCard(path, value, title, note, { color = '', tag = '' } = {}) {
  const on = has(getPath(study, path), value);
  return `<label class="opt${on ? ' on' : ''}"${color ? ` style="--c:${color}"` : ''}>
    <input type="checkbox" data-list="${pathAttr(path)}" data-value="${esc(value)}" ${on ? 'checked' : ''}>
    <span class="otxt"><b>${color ? '<span class="swatch"></span>' : ''}${esc(title)}${tag}</b>
      ${note ? `<small>${esc(note)}</small>` : ''}</span></label>`;
}

/** A small toggle chip for a value in a list — used for a task's arms. */
function chip(path, value) {
  const on = has(getPath(study, path), value);
  return `<label class="chip${on ? ' on' : ''}"><input type="checkbox" data-list="${pathAttr(path)}"
    data-value="${esc(value)}" ${on ? 'checked' : ''}>${esc(value)}</label>`;
}

function section(id, body) {
  const i = SECTIONS.findIndex((s) => s.id === id);
  const s = SECTIONS[i];
  return `<section class="card" id="sec-${id}" data-section="${id}">
    <header><span class="n">${i + 1}</span><div class="grow"><h3>${esc(s.title)}</h3><p>${esc(s.blurb)}</p></div>
      <span class="badge" data-badge="${id}"></span></header>
    <div class="body">${body}</div>
    <div class="secprob" data-problems="${id}"></div></section>`;
}

// ---------------------------------------------------------------------------
// the form
// ---------------------------------------------------------------------------

function render() {
  const participants = study.audience === 'participants';
  const special = (study.modalities ?? []).filter((m) => SPECIAL_CATEGORY_MODALITIES.includes(m));
  const arms = study.conditions?.arms ?? [];
  const gaze = has(study.modalities, 'gaze');

  const audience = (value, title, text) => {
    const on = (study.audience ?? '') === value;
    return `<label class="opt${on ? ' on' : ''}"><input type="radio" name="audience" value="${value}" ${on ? 'checked' : ''}>
      <span class="otxt"><b>${title}</b><small>${text}</small></span></label>`;
  };

  const tierCard = (t) => {
    const on = has(study.consent_tiers, t.id);
    const def = on && study.default_tier === t.id;
    const note = t.id === 'features_in_browser' ? `${t.summary} Only with ${joinAnd(BROWSER_MODALITIES)}.` : t.summary;
    return `<div class="opt tier${on ? ' on' : ''}">
      <label class="omain"><input type="checkbox" data-list='${pathAttr(['consent_tiers'])}' data-value="${esc(t.id)}" ${on ? 'checked' : ''}>
        <span class="otxt"><b>${esc(t.label)}</b><small>${esc(note)}</small></span></label>
      ${on ? `<label class="def${def ? ' is' : ''}" title="The option already chosen when the consent screen opens">
        <input type="radio" name="defaultTier" data-default="${esc(t.id)}" ${def ? 'checked' : ''}>${def ? 'Pre-selected' : 'Pre-select'}</label>` : ''}
    </div>`;
  };

  $('form').innerHTML = `<div class="formwrap">
    ${section('basics', `
      <div class="grid2">
        ${field('Study id', ['study_id'], { required: true, help: 'Letters, digits, - and _. It is the <code>?study=</code> in the participant link.' })}
        ${field('Version', ['version'], { required: true })}
      </div>
      ${field('Name', ['name'], { required: true })}
      <div class="lbl" style="margin-top:4px">Who it may be run on</div>
      <div class="opts two">
        ${audience('', 'Developer self-test', 'Only you. The capture page shows a “not for participants” banner, and cohort analysis leaves these sessions out.')}
        ${audience('participants', 'Participants', 'Real people, under an ethics approval. The capture page refuses the study until the ethics and data-protection fields are filled in.')}
      </div>`)}

    ${section('told', `
      ${field('How long the data is kept', ['disclosure', 'retention_days'], { type: 'number', required: true, suffix: 'days',
        help: 'At most 1095. Deleted by the scheduled retention sweep when it runs out.' })}
      ${field('Who sees the data', ['disclosure', 'secondary_use'], { required: true, rows: 2 })}
      ${field('Contact', ['disclosure', 'contact'], { required: true, rows: 2,
        help: 'The investigator, and the route to the ethics board. Must include an email or web address for participants.' })}
      <div class="sub${participants ? ' need' : ''}">
        <h4>Ethics and data protection</h4>
        <div class="muted">${participants ? 'Required: this study is for participants.'
          : 'Needed before this study can be run on participants. Optional for a self-test.'}</div>
        <div class="grid2">
          ${field('Ethics approval reference', ['disclosure', 'irb_reference'], { required: participants, placeholder: 'e.g. REC-2026-0099' })}
          ${field('Data controller', ['disclosure', 'controller'], { required: participants, placeholder: 'e.g. University of …' })}
        </div>
        ${field('Lawful basis (UK GDPR Art 6)', ['disclosure', 'lawful_basis'], { required: participants,
          placeholder: 'e.g. Art 6(1)(e) — a task in the public interest' })}
        ${field('Special category condition (Art 9)', ['disclosure', 'special_category_basis'], { required: participants && special.length > 0,
          placeholder: 'e.g. Art 9(2)(j) — scientific research',
          help: special.length ? `Needed because ${joinAnd(special)} ${special.length === 1 ? 'is' : 'are'} treated as special-category data.`
            : 'Needed when face, voice or respiration is measured.' })}
      </div>`)}

    ${section('measures', `
      <div class="opts two">
        ${MODALITIES.map((m) => optCard(['modalities'], m.id, m.label, m.note, { color: MODALITY_COLOR[m.id] ?? '',
          tag: SPECIAL_CATEGORY_MODALITIES.includes(m.id) ? '<span class="tag">special category</span>' : '' })).join('')}
      </div>
      ${gaze ? `<div class="inline">
        ${field('Calibration points', ['calibration', 'n_points'], { type: 'number', help: '5 to 13' })}
        <label class="toggle"><input type="checkbox" id="randomise" ${study.calibration?.randomise_order === false ? '' : 'checked'}>
          Randomise their order <small>— a fixed order confounds target with time</small></label>
      </div>` : ''}`)}

    ${section('consent', `<div class="opts">${CONSENT_TIERS.map(tierCard).join('')}</div>`)}

    ${section('tasks', `
      <div class="tasks">
        ${(study.tasks ?? []).map((t, i) => taskCard(t, i, arms)).join('')
          || '<div class="empty">No tasks yet — the capture page will run its default set for the measures chosen. Add one below.</div>'}
      </div>
      <div class="palette-h">Add a task</div>
      <div class="palette">${Object.entries(TASK_TYPES).map(([k, v]) => `<button class="pal" data-add-task="${k}"
        style="--c:${KINDS[v.kind].color}"><i></i><span>${esc(v.label)}<small>${esc(v.hint)}</small></span></button>`).join('')}</div>`)}

    ${section('conditions', `
      <div class="field"><label><span class="lbl">Between-subject arms</span>
        <input id="arms" value="${esc(arms.join(', '))}" placeholder="e.g. A, B — leave empty for none"></label>
        <div class="help">Each participant is assigned one arm at random. A task can then be limited to some arms.</div>
        ${arms.length ? `<div class="arms">${arms.length} arms: ${arms.map((a) => `<span class="chip on">${esc(a)}</span>`).join('')}</div>` : ''}
      </div>
      ${field('Completion link', ['recruitment', 'completion_url'], { placeholder: 'https://app.prolific.com/submissions/complete?cc=CODE',
        help: 'Where the participant is sent once their data is saved, e.g. back to Prolific. https only.' })}`)}

    ${section('analysis', `
      <div class="grid2">
        ${field('AOI padding', ['analysis', 'aoi_pad_deg'], { type: 'number', suffix: 'degrees', help: 'Required for AOI metrics — there is no default.' })}
        ${field('Heatmap blur', ['analysis', 'heatmap_sigma_deg'], { type: 'number', suffix: 'degrees', help: 'Default 1.' })}
      </div>
      <div class="rulesh">Exclusions</div>
      <div class="muted">A session must meet every rule, or it is excluded, with the reason, in the attrition table.</div>
      ${(study.analysis?.exclusions ?? []).length ? `<table class="rules"><thead><tr><th>Metric</th><th>Min</th><th>Max</th><th></th></tr></thead><tbody>
        ${study.analysis.exclusions.map((e, i) => exclusionRow(e, i)).join('')}</tbody></table>` : ''}
      <datalist id="metrics">${METRIC_SUGGESTIONS.map((m) => `<option value="${m}">`).join('')}</datalist>
      <button class="add" id="btnAddExclusion">+ Add exclusion</button>
      <div class="rulesh">Epochs</div>
      <div class="muted">Signals cut around each event, baseline-corrected, for the cohort analysis.</div>
      ${(study.analysis?.epochs ?? []).map((e, i) => epochCard(e, i)).join('')}
      <button class="add" id="btnAddEpoch">+ Add epoch set</button>`)}
  </div>`;

  $('rail').innerHTML = `<div class="rail-h">Sections</div>
    ${SECTIONS.map((s, i) => `<button class="step" data-jump="${s.id}" data-step="${s.id}">
      <span class="n">${i + 1}</span><span>${esc(s.title)}</span></button>`).join('')}
    <div class="rail-foot" id="railFoot"></div>`;
  spy();
  return refresh();
}

function taskCard(t, i, arms) {
  const at = (...rest) => ['tasks', i, ...rest];
  const type = TASK_TYPES[t.type];
  let body = '';
  if (t.type === 'rest_fixation' || t.type === 'free_speech') {
    body = `<div class="grid3">${field('Duration', at('duration_ms'), { type: 'number', suffix: 'ms' })}</div>`;
  }
  if (t.type === 'expression_prompts') {
    body = `<div class="grid3">${field('Repeats', at('repeats'), { type: 'number' })}
      ${field('Hold', at('hold_ms'), { type: 'number', suffix: 'ms' })}</div>`;
  }
  if (t.type === 'stimuli') body = stimuliBody(t, i);
  if (arms.length) body += `<div class="arms">Only for arms ${arms.map((a) => chip(at('arms'), a)).join('')}
    <span>${t.arms?.length ? '' : '— none ticked: every participant'}</span></div>`;
  const last = (study.tasks?.length ?? 0) - 1;
  return `<div class="task" data-task="${i}" style="--c:${KINDS[type?.kind]?.color ?? '#555'}">
    <div class="thead"><span class="tnum">${i + 1}</span>
      <div class="ttl"><b>${esc(type?.label ?? t.type)}</b><span>${esc(type?.hint ?? '')}</span></div>
      <span class="tdur" data-task-ms="${i}"></span>
      <div class="tools">
        <button class="icon" data-move="${i}" data-dir="-1" title="Move up" aria-label="Move up" ${i === 0 ? 'disabled' : ''}>↑</button>
        <button class="icon" data-move="${i}" data-dir="1" title="Move down" aria-label="Move down" ${i === last ? 'disabled' : ''}>↓</button>
        <button class="icon rm" data-remove='${pathAttr(at())}' title="Remove task" aria-label="Remove task">✕</button>
      </div></div>
    <div class="tbody">${body}</div></div>`;
}

function stimuliBody(t, i) {
  const at = (...rest) => ['tasks', i, ...rest];
  const tiles = (t.items ?? []).map((it, j) => `<div class="tile">
      <div class="thumb">${it.kind === 'image' ? `<img src="/${esc(it.src)}" alt="">` : '<span class="play">▶</span>'}</div>
      <div class="meta">
        <input data-path='${pathAttr(at('items', j, 'stimulus_id'))}' value="${esc(it.stimulus_id)}" title="Stimulus id — AOIs and results are keyed on it" aria-label="Stimulus id">
        <label class="mini">shown for <input data-path='${pathAttr(at('items', j, 'duration_ms'))}' data-type="number" type="number" value="${esc(it.duration_ms)}">ms</label>
        <span class="kind" title="${esc(it.sha256)}">${esc(it.kind)} · ${esc(String(it.src).replace(/^stimuli\//, ''))}</span>
      </div>
      <button class="icon rm" data-remove='${pathAttr(at('items', j))}' title="Remove" aria-label="Remove ${esc(it.stimulus_id)}">✕</button>
    </div>`).join('');
  return `<div class="inline" style="margin-top:0">
      ${field('Gap between', at('isi_ms'), { type: 'number', suffix: 'ms' })}
      <label class="toggle"><input type="checkbox" data-bool='${pathAttr(at('randomise'))}' ${t.randomise === false ? '' : 'checked'}>
        Shuffle the order for each participant</label></div>
    <div class="tiles">${tiles}
      <label class="drop" data-drop="${i}"><input type="file" data-upload="${i}" multiple accept=".png,.jpg,.jpeg,.webp,.webm,.mp4">
        <b>+</b><span>Add pictures or videos</span><span class="up muted">drop files here, or click</span>
        <span class="up" id="upload-${i}"></span></label></div>`;
}

function exclusionRow(e, i) {
  const at = (k) => pathAttr(['analysis', 'exclusions', i, k]);
  return `<tr>
    <td><input data-path='${at('metric')}' list="metrics" value="${esc(e.metric)}" placeholder="e.g. achieved_fps" aria-label="Metric"></td>
    <td><input data-path='${at('min')}' data-type="number" type="number" value="${esc(e.min ?? '')}" placeholder="—" aria-label="Minimum"></td>
    <td><input data-path='${at('max')}' data-type="number" type="number" value="${esc(e.max ?? '')}" placeholder="—" aria-label="Maximum"></td>
    <td><button class="icon rm" data-remove='${pathAttr(['analysis', 'exclusions', i])}' title="Remove" aria-label="Remove rule">✕</button></td></tr>`;
}

function epochCard(e, i) {
  const at = (...k) => ['analysis', 'epochs', i, ...k];
  const small = (label, path, opts = {}) => field(label, path, opts);
  return `<div class="epoch">
    <button class="icon rm" data-remove='${pathAttr(['analysis', 'epochs', i])}' title="Remove" aria-label="Remove epoch set">✕</button>
    <div class="grid4">
      ${small('Name', at('name'), { cls: 'span2' })}
      ${small('Cut around event', at('event_type'), { cls: 'span2', placeholder: 'e.g. stimulus' })}
      <div class="field span2"><label><span class="lbl">Channels</span>
        <input data-csv='${pathAttr(at('channels'))}' value="${esc((e.channels ?? []).join(', '))}" placeholder="comma-separated"></label></div>
      ${small('Source', at('source'), { cls: 'span2', placeholder: 'only if a channel has several' })}
      ${small('Before (ms)', at('pre_ms'), { type: 'number' })}
      ${small('After (ms)', at('post_ms'), { type: 'number' })}
      ${small('Baseline from (ms)', at('baseline_ms', 0), { type: 'number' })}
      ${small('Baseline to (ms)', at('baseline_ms', 1), { type: 'number' })}
      ${small('Resample (Hz)', at('resample_hz'), { type: 'number', placeholder: '30' })}
    </div></div>`;
}

// ---------------------------------------------------------------------------
// edits
// ---------------------------------------------------------------------------

function edited() { setSaveResult(''); }

function onInput(ev) {
  const el = ev.target;
  if (el.dataset.path) {
    const path = JSON.parse(el.dataset.path);
    const raw = el.value;
    const value = raw.trim() === '' ? undefined
      : el.dataset.type === 'number' ? Number(raw) : raw;
    setPath(study, path, value);
    tidy();
    edited();
    refresh();
  } else if (el.dataset.csv) {
    const list = parseList(el.value);
    setPath(study, JSON.parse(el.dataset.csv), list.length ? list : undefined);
    edited();
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
    edited();
    return render();
  }
  if (el.dataset.bool) {
    setPath(study, JSON.parse(el.dataset.bool), el.checked ? undefined : false);
    edited();
    return refresh();
  }
  if (el.dataset.default) { study.default_tier = el.dataset.default; edited(); return render(); }
  if (el.dataset.upload !== undefined) return upload([...el.files], Number(el.dataset.upload));
  if (el.name === 'audience') {
    setPath(study, ['audience'], el.value || undefined);
    edited();
    return render();
  }
  if (el.id === 'randomise') { setPath(study, ['calibration', 'randomise_order'], el.checked); edited(); return render(); }
  if (el.id === 'arms') {
    const arms = parseList(el.value);
    setPath(study, ['conditions'], arms.length ? { arms } : undefined);
    for (const t of study.tasks ?? []) if (!arms.length) delete t.arms;
    edited();
    return render();
  }
  return undefined;
}

/** Bring a card into view and flash it, so the eye lands on it. */
function flashInto(el) {
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1200);
}

function jumpTo(sectionId, fieldKey) {
  const f = fieldKey && document.querySelector(`.field[data-field="${CSS.escape(fieldKey)}"]`);
  if (f) {
    f.scrollIntoView({ behavior: 'smooth', block: 'center' });
    f.querySelector('input, textarea, select')?.focus({ preventScroll: true });
    return;
  }
  $(`sec-${sectionId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function onClick(ev) {
  const block = ev.target.closest('[data-goto]');
  if (block) {
    // From the diagram to the task it came from.
    flashInto(document.querySelector(`.task[data-task="${block.dataset.goto}"]`));
    return;
  }
  const jump = ev.target.closest('[data-jump]');
  if (jump) { jumpTo(jump.dataset.jump, jump.dataset.focus); return; }
  const tab = ev.target.closest('[data-tab]');
  if (tab) { sideTab = tab.dataset.tab; showTab(); return; }
  const el = ev.target.closest('button');
  if (!el) return;
  if (el.id === 'validity') {
    if (reasonsNow.length) jumpTo(sectionOf(reasonsNow[0]), fieldOf(reasonsNow[0]));
  } else if (el.dataset.remove) {
    setPath(study, JSON.parse(el.dataset.remove), undefined);
    tidy();
    edited();
    render();
  } else if (el.dataset.move !== undefined) {
    const i = Number(el.dataset.move);
    const j = i + Number(el.dataset.dir);
    if (j < 0 || j >= study.tasks.length) return;
    [study.tasks[i], study.tasks[j]] = [study.tasks[j], study.tasks[i]];
    edited();
    render();
    flashInto(document.querySelector(`.task[data-task="${j}"]`));
  } else if (el.dataset.addTask) {
    study.tasks = [...(study.tasks ?? []), TASK_TYPES[el.dataset.addTask].make()];
    edited();
    render();
    flashInto(document.querySelector(`.task[data-task="${study.tasks.length - 1}"]`));
  } else if (el.id === 'btnAddExclusion') {
    setPath(study, ['analysis', 'exclusions'], [...(study.analysis?.exclusions ?? []), { metric: 'achieved_fps', min: 5 }]);
    edited();
    render();
  } else if (el.id === 'btnAddEpoch') {
    setPath(study, ['analysis', 'epochs'], [...(study.analysis?.epochs ?? []),
      { name: `epochs_${(study.analysis?.epochs ?? []).length + 1}`, event_type: 'stimulus',
        channels: ['blendshape.mouthSmileLeft'], pre_ms: 500, post_ms: 3000, baseline_ms: [-500, 0] }]);
    edited();
    render();
  } else if (el.id === 'btnApplyJson') {
    try {
      study = JSON.parse($('json').value);
      edited();
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
    render().then(() => save(false));
  } else if (el.id === 'btnDismiss') {
    setSaveResult('');
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

/** Upload files into a stimuli task, one by one; a refused file is named, the rest still land. */
async function upload(files, taskIndex) {
  if (!files.length) return;
  const task = study.tasks[taskIndex];
  const refused = [];
  for (const file of files) {
    const status = $(`upload-${taskIndex}`);
    if (status) status.textContent = `uploading ${file.name}…`;
    const res = await fetch(`/api/stimuli?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
    const body = await res.json();
    if (!res.ok) { refused.push(`${file.name}: ${body.detail ?? body.error}`); continue; }
    task.items = [...(task.items ?? []), {
      stimulus_id: stimulusIdFrom(file.name), kind: body.kind, src: body.src, sha256: body.sha256,
      duration_ms: 4000,
    }];
  }
  edited();
  await render();
  if (refused.length) $(`upload-${taskIndex}`).innerHTML = refused.map((r) => `<span class="bad">${esc(r)}</span>`).join('<br>');
}

// ---------------------------------------------------------------------------
// what the study adds up to — refreshed on every keystroke
// ---------------------------------------------------------------------------

async function refresh() {
  const { valid, reasons } = validateStudy(study);
  reasonsNow = reasons;
  let hash = '';
  try { hash = await contentHash(study); } catch { /* shown as blank */ }

  markProblems(reasons);

  // Header: status, unsaved changes, Save.
  $('statusSlot').innerHTML = valid
    ? '<button class="status ok" id="validity" title="The capture page will accept this study">Valid — ready to save</button>'
    : `<button class="status bad" id="validity" title="Go to the first problem">${reasons.length} problem${reasons.length === 1 ? '' : 's'}</button>`;
  $('btnSave').disabled = !valid;
  $('btnSave').innerHTML = `Save <span class="mono">studies/${esc(study.study_id)}.json</span>`;
  $('dirty').hidden = JSON.stringify(study) === savedAs;

  const arms = study.conditions?.arms?.length ? study.conditions.arms : [null];
  let lanes = [];
  let journey;
  try {
    lanes = flowModels(study, { buildSequence, estimateDurationMs, wantsChinrest });
    journey = flowHtml(lanes);
  } catch (err) {
    journey = `<div class="bad">${esc(err.message)}</div>`;
  }
  taskDurations(lanes);
  const longest = Math.max(0, ...lanes.map((l) => l.totalMs));
  $('railFoot').innerHTML = lanes.length ? `<b>about ${fmtMs(longest)}</b>per participant, once set up${lanes.length > 1 ? ` · ${lanes.length} arms` : ''}` : '';

  let consentHtml = '<div class="empty">The consent screen is shown once the study is valid.</div>';
  if (valid) {
    try {
      const p = protocolFor(study, { condition: arms[0] });
      const d = p.disclosure;
      const doing = p.activity.doing.length ? ` while you ${joinAnd(p.activity.doing)}` : '';
      consentHtml = `${arms[0] ? `<div class="caption">As shown to arm ${esc(arms[0])}.</div>` : ''}<div class="preview">
        ${d.audience === 'participants' ? '' : '<p class="selftest"><b>Developer self-test.</b> Not for participants.</p>'}
        <p>This session records ${esc(p.activity.records)} from your ${esc(p.activity.devices)}${esc(doing)}.</p>
        ${p.activity.measures.length ? `<p><b>Automated analysis.</b> ${esc(analysisNotice(p.activity.measures))}</p>` : ''}
        ${p.tiers.map((t) => `<div class="tier"><b>${esc(t.label)}</b> — ${esc(t.summary)}
          <ul>${t.keeps.map((k) => `<li>${esc(k)}</li>`).join('')}</ul></div>`).join('')}
        <p class="small">Kept for ${esc(d.retentionDays)} days. Who else sees it: ${esc(d.secondaryUse)}<br>
          Contact: ${esc(d.contact)}${d.controller ? `<br>Responsible for your data: ${esc(d.controller)}` : ''}
          ${d.lawfulBasis ? `<br>Legal basis: ${esc(d.lawfulBasis)}${d.specialCategoryBasis ? `; ${esc(d.specialCategoryBasis)}` : ''}` : ''}
          ${d.irbReference ? `<br>Approved under ${esc(d.irbReference)}.` : ''}</p>
        <p class="small">${esc(withdrawalText(d.retentionDays))}</p></div>`;
    } catch (err) {
      consentHtml = `<div class="bad">${esc(err.message)}</div>`;
    }
  }

  $('side').innerHTML = `
    ${valid ? '' : `<div class="problems"><div class="ph">Fix ${reasons.length === 1 ? 'this' : `these ${reasons.length}`} before saving</div>
      <ul class="reasons">${reasons.map((r) => `<li data-jump="${sectionOf(r)}" data-focus="${esc(fieldOf(r) ?? '')}">
        <span>${esc(SECTIONS.find((s) => s.id === sectionOf(r)).title)}</span>${esc(r)}</li>`).join('')}</ul></div>`}
    <div class="hashline" title="Covers the protocol: anything that changes what a participant is told or does changes it. The analysis plan is not part of it.">
      Protocol hash <span class="mono" id="hash">${esc(hash)}</span></div>
    <div class="tabs" role="tablist">
      <button class="tab" data-tab="journey" role="tab">Participant’s journey</button>
      <button class="tab" data-tab="consent" role="tab">Consent screen</button>
      <button class="tab" data-tab="json" role="tab">JSON</button>
    </div>
    <div class="pane" data-pane="journey">${journey}</div>
    <div class="pane" data-pane="consent">${consentHtml}</div>
    <div class="pane" data-pane="json">
      <div class="caption">The file as it will be saved. Edit it here for anything the form does not cover.</div>
      <textarea id="json" spellcheck="false">${esc(JSON.stringify(study, null, 2))}</textarea>
      <div class="row"><button id="btnApplyJson">Apply edited JSON</button><span class="bad" id="jsonError"></span></div></div>`;
  showTab();
}

function showTab() {
  for (const t of document.querySelectorAll('[data-tab]')) {
    t.classList.toggle('on', t.dataset.tab === sideTab);
    t.setAttribute('aria-selected', String(t.dataset.tab === sideTab));
  }
  for (const p of document.querySelectorAll('[data-pane]')) p.hidden = p.dataset.pane !== sideTab;
}

/** Each problem where it is fixed: under its field, or at the foot of its section. */
function markProblems(reasons) {
  const bySection = Object.fromEntries(SECTIONS.map((s) => [s.id, []]));
  const byField = {};
  for (const r of reasons) {
    const f = fieldOf(r);
    if (f && document.querySelector(`.field[data-field="${CSS.escape(f)}"]`)) (byField[f] ??= []).push(r);
    bySection[sectionOf(r)].push({ r, placed: Boolean(f && byField[f]) });
  }
  for (const el of document.querySelectorAll('.field[data-field]')) {
    const mine = byField[el.dataset.field] ?? [];
    el.classList.toggle('invalid', mine.length > 0);
    const err = el.querySelector('.err');
    if (err) err.textContent = mine.join(' · ');
  }
  for (const s of SECTIONS) {
    const list = bySection[s.id];
    const loose = list.filter((x) => !x.placed).map((x) => x.r);
    const box = document.querySelector(`[data-problems="${s.id}"]`);
    if (box) box.innerHTML = loose.length ? `<div class="problems" style="margin:0"><ul class="reasons sreasons">${loose.map((r) => `<li>${esc(r)}</li>`).join('')}</ul></div>` : '';
    const badge = document.querySelector(`[data-badge="${s.id}"]`);
    if (badge) {
      badge.className = `badge ${list.length ? 'has' : 'good'}`;
      badge.textContent = list.length ? `${list.length} to fix` : '✓';
    }
    const step = document.querySelector(`[data-step="${s.id}"]`);
    if (step) {
      step.classList.toggle('has', list.length > 0);
      step.classList.toggle('good', list.length === 0);
      step.querySelector('.n').textContent = list.length ? String(list.length) : '✓';
    }
  }
}

/** Each task card's length, from the journey (the longest arm it appears in). */
function taskDurations(lanes) {
  const ms = {};
  for (const l of lanes) for (const b of l.blocks) {
    if (b.taskIndex !== null && b.taskIndex !== undefined) ms[b.taskIndex] = Math.max(ms[b.taskIndex] ?? 0, b.ms);
  }
  for (const el of document.querySelectorAll('[data-task-ms]')) {
    const v = ms[el.dataset.taskMs];
    const before = study.tasks?.[el.dataset.taskMs]?.type === 'chinrest';
    el.textContent = v ? `≈ ${fmtMs(v)}` : before ? 'before recording' : study.conditions ? 'not in any arm' : '';
  }
}

/** Which section the form is scrolled to, lit in the rail. */
function spy() {
  const top = $('form').getBoundingClientRect().top + 120;
  let cur = SECTIONS[0].id;
  for (const s of document.querySelectorAll('section[data-section]')) {
    if (s.getBoundingClientRect().top <= top) cur = s.dataset.section;
  }
  for (const b of document.querySelectorAll('[data-step]')) b.classList.toggle('cur', b.dataset.step === cur);
}

/**
 * The flow diagram: one lane per arm. A to-scale strip of the recording, then
 * the journey top to bottom — before, during, after — each recording block
 * coloured by what it measures, taller for longer, and clickable to its task.
 */
function flowHtml(lanes) {
  const used = new Set(lanes.flatMap((l) => l.blocks.map((b) => b.kind)));
  const legend = Object.entries(KINDS).filter(([k]) => used.has(k))
    .map(([, v]) => `<span class="chip"><i style="background:${v.color}"></i>${esc(v.label)}</span>`).join('');
  const card = (b, total) => {
    const clickable = b.taskIndex !== null && b.taskIndex !== undefined;
    const h = Math.round(30 + Math.min(1, b.ms / Math.max(total, 1)) * 170);
    const thumbs = (b.items ?? []).map((it) => (it.kind === 'image'
      ? `<img src="/${esc(it.src)}" alt="${esc(it.id)}" title="${esc(it.id)}">`
      : `<span class="vid" title="${esc(it.id)}">▶</span>`)).join('');
    return `<div class="fb${clickable ? ' click' : ''}" ${clickable ? `data-goto="${b.taskIndex}" title="Go to this task"` : ''}
        style="border-left-color:${KINDS[b.kind]?.color ?? '#555'}; min-height:${h}px">
      <div class="fh"><b>${esc(b.title)}</b><span class="mono">${b.ms ? esc(fmtMs(b.ms)) : ''}</span></div>
      ${b.detail ? `<div class="muted">${esc(b.detail)}</div>` : ''}
      ${thumbs ? `<div class="thumbs">${thumbs}</div>` : ''}</div>`;
  };
  const small = (b) => `<div class="fs" style="border-left-color:${KINDS[b.kind].color}">
      <b>${esc(b.title)}</b> <span>${esc(b.detail)}</span></div>`;
  return `<div class="legend">${legend}</div>
    <div class="lanes" style="grid-template-columns: repeat(${lanes.length}, minmax(0, 1fr))">
    ${lanes.map((l) => `<div class="lane">
      <div class="lh"><span>${l.arm ? `Arm <b>${esc(l.arm)}</b>` : '<b>Every participant</b>'}</span><span>about ${fmtMs(l.totalMs)}</span></div>
      <div class="strip">${l.blocks.map((b) => `<i style="flex:${Math.max(b.ms, 1)};background:${KINDS[b.kind]?.color}"
        title="${esc(b.title)}"></i>`).join('')}</div>
      <div class="phase">Before recording</div>${l.before.map(small).join('')}
      <div class="phase">Recording · ${esc(l.records)}</div>${l.blocks.map((b) => card(b, l.totalMs)).join('')}
      <div class="phase">After</div>${l.after.map(small).join('')}
    </div>`).join('')}</div>`;
}

function fmtMs(ms) {
  const s = Math.round(ms / 1000);
  return s < 90 ? `${s} s` : `${Math.round(s / 6) / 10} min`;
}

// ---------------------------------------------------------------------------
// saving
// ---------------------------------------------------------------------------

function setSaveResult(html, tone = '') {
  const el = $('saveResult');
  el.className = `banner ${tone}`;
  el.innerHTML = html ? `${html}<button class="icon x" id="btnDismiss" title="Dismiss" aria-label="Dismiss">✕</button>` : '';
  el.hidden = !html;
}

async function save(overwrite) {
  setSaveResult('<span class="muted">saving…</span>');
  const res = await fetch('/api/studies', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ study, overwrite }),
  });
  const body = await res.json();
  if (res.ok) {
    savedAs = JSON.stringify(study);
    $('dirty').hidden = true;
    setSaveResult(`<p><span class="ok"><b>Saved ${esc(body.saved)}</b></span> · hash <span class="mono">${esc(body.content_hash)}</span></p>
      <p class="muted">Participant link (with <code>npm run serve</code>):
      <code>http://localhost:5173/?study=${esc(body.study_id)}</code> · records of processing:
      <code>npm run ropa -- ${esc(body.study_id)}</code> · commit the file to version it.</p>`, 'ok');
    loadList(body.study_id);
    return;
  }
  if (body.sessions) {
    setSaveResult(`<p class="warn">${esc(body.detail)}</p>
      <button id="btnSaveAs" data-id="${esc(body.suggestion)}">Save as ${esc(body.suggestion)} instead</button>`, 'warn');
  } else if (body.can_overwrite) {
    setSaveResult(`<p class="warn">${esc(body.detail)}</p><button id="btnOverwrite">Overwrite the draft</button>`, 'warn');
  } else {
    setSaveResult(`<p class="bad">${esc(body.detail ?? body.error)}</p>
      ${body.reasons ? `<ul class="reasons">${body.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}`, 'bad');
  }
}

// ---------------------------------------------------------------------------
// start
// ---------------------------------------------------------------------------

async function loadList(selected = $('startFrom').value) {
  const { studies } = await (await fetch('/api/studies', { cache: 'no-store' })).json();
  $('startFrom').innerHTML = `<option value="">New blank study</option>${studies
    .map((s) => `<option value="${esc(s.study_id)}">${esc(s.study_id)}${s.valid ? '' : ' (invalid)'}</option>`).join('')}`;
  $('startFrom').value = studies.some((s) => s.study_id === selected) ? selected : '';
}

$('startFrom').addEventListener('change', async (ev) => {
  const id = ev.target.value;
  setSaveResult('');
  if (!id) {
    study = blankStudy();
  } else {
    const res = await fetch(`/api/studies/${encodeURIComponent(id)}`, { cache: 'no-store' });
    study = (await res.json()).study ?? blankStudy();
  }
  savedAs = JSON.stringify(study);
  $('form').scrollTop = 0;
  return render();
});

document.addEventListener('input', onInput);
document.addEventListener('change', onChange);
document.addEventListener('click', onClick);
$('form').addEventListener('scroll', spy, { passive: true });

// Files dropped anywhere but a drop zone would open in the tab and lose the study.
document.addEventListener('dragover', (ev) => {
  ev.preventDefault();
  for (const z of document.querySelectorAll('.drop.over')) z.classList.remove('over');
  ev.target.closest?.('.drop')?.classList.add('over');
});
document.addEventListener('drop', (ev) => {
  ev.preventDefault();
  const zone = ev.target.closest?.('.drop');
  zone?.classList.remove('over');
  if (zone && ev.dataTransfer?.files?.length) upload([...ev.dataTransfer.files], Number(zone.dataset.drop));
});
window.addEventListener('beforeunload', (ev) => {
  if (JSON.stringify(study) !== savedAs) ev.preventDefault();
});

loadList();
render();

/**
 * Human annotation arm.
 *
 * A coder watches a moment from a session's video and picks one category. That
 * is the whole interaction, and keeping it that small is deliberate — this is
 * the reference standard everything else is measured against, so anything that
 * biases a coder biases every accuracy figure downstream.
 *
 * Four things this page does NOT do, each because doing it would quietly
 * inflate the human ceiling:
 *
 * - **It never shows another rater's labels.** Independence is the assumption
 *   every agreement coefficient rests on. The API has no route that would
 *   serve them, so this is enforced rather than merely observed.
 * - **It never shows the engine's prediction.** A coder who can see what the
 *   model said is scoring the model's confidence, not the behaviour, and the
 *   resulting agreement is circular.
 * - **It offers no "unsure" default and preselects nothing.** A default is the
 *   answer a tired coder gives, and a default that happens to match the
 *   majority manufactures agreement.
 * - **It does not let a coder skip forward through unlabelled items.** They
 *   can stop, and resume later; what they cannot do is cherry-pick the easy
 *   ones, because a ceiling measured on the easy half is not the ceiling.
 */

const $ = (id) => document.getElementById(id);

const state = {
  codebook: null,
  sessionId: null,
  raterId: null,
  labels: {},           // item timestamp (string) -> category id
  index: 0,
  video: null,
};

const params = new URLSearchParams(location.search);

async function api(path, options) {
  const r = await fetch(path, options);
  const body = await r.json();
  if (!r.ok) throw new Error(body.detail ?? `${r.status}`);
  return body;
}

// ---------------------------------------------------------------------------
// setup
// ---------------------------------------------------------------------------

async function start() {
  const [{ codebooks }, { sessions }] = await Promise.all([
    api('/api/codebooks'), api('/api/sessions'),
  ]);

  if (!codebooks.length) {
    $('main').innerHTML = `<div class="note">
      No codebooks yet. A codebook is the list of categories a coder chooses
      between and the moments they are asked about; it is versioned and hashed
      like an AOI set, because a category means something different once its
      description changes.
      <br><br>Create one by POSTing to <code>/api/codebooks</code>.</div>`;
    $('sub').textContent = '';
    return;
  }

  const preCb = params.get('codebook');
  const preSess = params.get('session');

  $('sub').textContent = 'set up';
  $('main').innerHTML = `
    <div class="setup">
      <label class="field">Codebook
        <select id="cb">${codebooks.map((c) => `
          <option value="${c.codebook_id}|${c.content_hash}"
            ${c.codebook_id === preCb ? 'selected' : ''}>
            ${c.name} — ${c.n_categories} categories, ${c.n_items} items
            (${c.content_hash})
          </option>`).join('')}</select>
      </label>

      <label class="field">Session
        <select id="sess">${sessions.map((s) => `
          <option value="${s.session_id}" ${s.session_id === preSess ? 'selected' : ''}>
            ${s.session_id} — ${s.participant_id ?? '—'}, ${s.study_id ?? '—'}
          </option>`).join('')}</select>
      </label>

      <label class="field">Your rater ID
        <input id="rater" placeholder="e.g. r1" autocomplete="off"
               value="${params.get('rater') ?? ''}">
      </label>

      <div class="note">
        A rater ID is a slug you assign, never a name or an email. Coders are
        people too, and a study's data files are not the place to record who
        coded what under their own name.
        <br><br>
        Use a <strong>different ID for each coder</strong>. Two people sharing
        one ID overwrite each other, and the second set of labels is the only
        thing that survives — which looks identical to having had one coder all
        along, except the file says there were two.
      </div>

      <div><button class="primary" id="go">Begin coding</button></div>
      <p class="note bad" id="err" style="display:none"></p>
    </div>`;

  $('go').addEventListener('click', begin);
}

async function begin() {
  const [codebookId, version] = $('cb').value.split('|');
  const sessionId = $('sess').value;
  const raterId = $('rater').value.trim();

  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(raterId)) {
    return fail('A rater ID must be letters, digits, dash or underscore — and '
      + 'must not be anyone’s name.');
  }

  try {
    state.codebook = await api(
      `/api/codebooks/${encodeURIComponent(codebookId)}`
      + `?version=${encodeURIComponent(version)}`);
    state.sessionId = sessionId;
    state.raterId = raterId;

    // Resume this coder's own work, and nobody else's. The API has no route
    // that would return another rater's labels.
    const { annotation } = await api(
      `/api/annotations/${encodeURIComponent(codebookId)}`
      + `/${encodeURIComponent(sessionId)}/${encodeURIComponent(raterId)}`
      + `?version=${encodeURIComponent(version)}`);
    state.labels = annotation?.labels ?? {};
  } catch (err) {
    return fail(String(err.message ?? err));
  }

  // Resume at the first unlabelled item rather than at the start, but never
  // past one: a coder who skipped an item left it unanswered on purpose or by
  // accident, and either way the next thing they should see is that item.
  const items = state.codebook.items;
  state.index = items.findIndex((t) => !(String(t) in state.labels));
  if (state.index < 0) state.index = items.length - 1;

  render();
}

function fail(message) {
  const el = $('err');
  if (el) { el.textContent = message; el.style.display = ''; }
}

// ---------------------------------------------------------------------------
// coding
// ---------------------------------------------------------------------------

function render() {
  const cb = state.codebook;
  const items = cb.items;
  const done = Object.keys(state.labels).length;

  $('sub').textContent =
    `${cb.name} · ${state.sessionId} · rater ${state.raterId}`;

  $('main').innerHTML = `
    <div class="row" style="margin-bottom:10px">
      <span class="sub">item ${state.index + 1} of ${items.length}
        · ${done} labelled</span>
      <span class="sub">${cb.content_hash}</span>
    </div>
    <div class="bar"><div style="width:${(done / items.length) * 100}%"></div></div>

    <div class="media" style="margin:14px 0">
      <video id="vid" playsinline preload="metadata"></video>
    </div>

    <div class="row">
      <button id="replay">Replay this moment</button>
      <span class="sub" id="tstamp"></span>
    </div>

    <div class="cats" id="cats">${cb.categories.map((c, i) => `
      <button class="cat" data-id="${c.id}">
        <span class="key">${i + 1}</span>
        <span>
          <span class="lbl">${c.label}</span><br>
          <span class="desc">${c.description}</span>
        </span>
      </button>`).join('')}</div>

    <div class="row">
      <button id="back" ${state.index === 0 ? 'disabled' : ''}>Back</button>
      <button class="primary" id="save">Save and stop</button>
    </div>

    <div class="note">
      Nothing is preselected, and there is no "unsure" option. A default is the
      answer a tired coder gives, and one that happens to match the majority
      manufactures agreement that was never there. If a moment genuinely does
      not fit any category, that is a finding about the codebook — stop and
      say so, rather than picking the nearest.
    </div>
    <p class="note bad" id="err" style="display:none"></p>`;

  state.video = $('vid');
  state.video.src = `/api/sessions/${encodeURIComponent(state.sessionId)}/media`;

  $('replay').addEventListener('click', seek);
  $('back').addEventListener('click', () => { state.index -= 1; render(); });
  $('save').addEventListener('click', save);

  [...document.querySelectorAll('.cat')].forEach((el) => {
    el.classList.toggle('chosen',
      state.labels[String(items[state.index])] === el.dataset.id);
    el.addEventListener('click', () => choose(el.dataset.id));
  });

  state.video.addEventListener('loadedmetadata', seek, { once: true });
  state.video.addEventListener('error', () => {
    $('main').insertAdjacentHTML('afterbegin', `<div class="note bad">
      This session's video is not available, so there is nothing to code.
      Media only exists for sessions whose consent tier retained it — for a
      <code>features_only</code> session the recording was deleted after
      processing, on purpose, and no annotation of it is possible.</div>`);
  });
}

function seek() {
  const t = state.codebook.items[state.index];
  $('tstamp').textContent = `${(t / 1000).toFixed(1)}s into the recording`;
  try {
    state.video.currentTime = t / 1000;
    state.video.play().catch(() => {});
  } catch { /* metadata not ready yet; loadedmetadata will retry */ }
}

function choose(categoryId) {
  const items = state.codebook.items;
  state.labels[String(items[state.index])] = categoryId;

  if (state.index < items.length - 1) {
    state.index += 1;
    render();
  } else {
    save();
  }
}

async function save() {
  if (!Object.keys(state.labels).length) {
    return fail('Nothing to save yet.');
  }
  try {
    const rec = await api('/api/annotations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        codebook_id: state.codebook.codebook_id,
        content_hash: state.codebook.content_hash,
        session_id: state.sessionId,
        rater_id: state.raterId,
        labels: state.labels,
      }),
    });
    done(rec);
  } catch (err) {
    fail(String(err.message ?? err));
  }
}

function done(rec) {
  $('main').innerHTML = `
    <h2 style="font-size:15px">Saved</h2>
    <div class="note">
      ${rec.n_labelled} of ${rec.n_items} items labelled${rec.complete
        ? '.' : ' — you can come back with the same rater ID and continue.'}
    </div>
    ${rec.complete ? `<div class="note">
      A reference standard needs <strong>at least two coders</strong>, and
      three before you can tell "the task is hard" from "one coder read the
      instructions differently". One person's labels are one person's labels;
      the evaluation will refuse to treat them as ground truth, which is the
      intended behaviour and not a bug to work around.</div>` : ''}
    <div><button class="primary" onclick="location.reload()">Code another</button></div>`;
  $('sub').textContent = 'saved';
}

// Number keys pick a category. Coding is long work and reaching for a mouse
// several hundred times is its own source of drift.
document.addEventListener('keydown', (e) => {
  if (!state.codebook || !document.querySelector('.cat')) return;
  const n = Number(e.key);
  if (Number.isInteger(n) && n >= 1 && n <= state.codebook.categories.length) {
    choose(state.codebook.categories[n - 1].id);
  } else if (e.key === 'r') {
    seek();
  }
});

start().catch((err) => {
  $('main').innerHTML = `<div class="note bad">${String(err.message ?? err)}</div>`;
  $('sub').textContent = 'failed';
});

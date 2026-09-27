/**
 * The participant's journey through a study, as blocks the builder can draw.
 *
 * Built from the capture page's own buildSequence (passed in, so this module
 * stays importable under node --test), so the diagram is the sequence a
 * participant will actually get — not a second description of it that could
 * drift. Every recording-phase block carries the study task it came from
 * (stage.taskIndex), which is how clicking a block finds its card in the form.
 */

/** What a block measures, for its colour and legend. */
export const KINDS = {
  setup: { label: 'Before recording', color: '#5f6b7a' },
  instruction: { label: 'Instructions', color: '#3a404a' },
  sync: { label: 'Sync flash', color: '#c9a227' },
  gaze: { label: 'Gaze', color: '#4c8dff' },
  face: { label: 'Face', color: '#b36ae2' },
  voice: { label: 'Voice', color: '#3fb27f' },
  rest: { label: 'Rest', color: '#7c8591' },
  stimuli: { label: 'Pictures and videos', color: '#e08a3c' },
  questions: { label: 'Questions', color: '#d4608a' },
  finish: { label: 'After recording', color: '#5f6b7a' },
};

const STAGE_KIND = {
  calibration_point: 'gaze', validation_point: 'gaze', fixation: 'rest',
  speech_read: 'voice', speech_free: 'voice', expression: 'face', stimulus: 'stimuli',
  question: 'questions',
};

function fmt(ms) {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = Math.round(ms / 1000);
  return s < 90 ? `${s} s` : `${Math.round(s / 6) / 10} min`;
}

function blockFor(stages, estimate) {
  const work = stages.filter((s) => s.type !== 'instruction');
  const first = work[0] ?? stages[0];
  const ms = estimate(stages);
  const n = work.length;
  const base = { ms, taskIndex: first.taskIndex ?? null, n };
  switch (first.type) {
    case 'calibration_point':
      return { ...base, kind: 'gaze', title: `${n} calibration dots`, detail: 'look at each dot' };
    case 'validation_point':
      return { ...base, kind: 'gaze', title: `${n} validation dots`, detail: 'checks the calibration' };
    case 'fixation':
      return { ...base, kind: 'rest', title: 'Rest on a cross', detail: fmt(first.durationMs ?? ms) };
    case 'speech_read':
      return { ...base, kind: 'voice', title: 'Read a passage aloud', detail: fmt(first.durationMs ?? ms) };
    case 'speech_free':
      return { ...base, kind: 'voice', title: 'Talk freely', detail: first.prompt ?? '' };
    case 'expression':
      return { ...base, kind: 'face', title: `${n} facial movements`, detail: 'ready → hold → relax' };
    case 'stimulus':
      return { ...base, kind: 'stimuli', title: `${n} picture${n === 1 ? '' : 's'} or video${n === 1 ? '' : 's'}`,
        detail: 'order shuffled per participant',
        items: work.map((s) => ({ id: s.stimulusId, kind: s.kind, src: s.src, ms: s.durationMs })) };
    case 'question':
      return { ...base, kind: 'questions', title: `${n} question${n === 1 ? '' : 's'}`,
        detail: work.map((s) => s.kind).join(', ') };
    default:
      return { ...base, kind: STAGE_KIND[first.type] ?? 'instruction', title: first.title ?? first.type, detail: '' };
  }
}

/**
 * The journey for one arm (or the only one). `deps` are the capture page's
 * buildSequence, estimateDurationMs and wantsChinrest.
 */
export function flowModel(study, { buildSequence, estimateDurationMs, wantsChinrest }, arm = null) {
  const seq = buildSequence(study, 1, { condition: arm });
  const tiers = study.consent_tiers ?? [];
  const audio = (study.modalities ?? []).includes('voice');

  const before = [
    { kind: 'setup', title: 'Consent', detail: `${tiers.length} option${tiers.length === 1 ? '' : 's'}: ${tiers.join(', ')}` },
    { kind: 'setup', title: audio ? 'Camera and microphone' : 'Camera', detail: 'permission asked after consent' },
  ];
  if (wantsChinrest(study)) {
    before.push({ kind: 'setup', title: 'Screen distance check', detail: 'bank card, then blind spot — about 2 min' });
  }

  // Group the recording phase: a block per task (consecutive stages sharing a
  // taskIndex); the overview and each sync flash, which belong to no task,
  // are blocks of their own.
  const blocks = [];
  let run = [];
  const flush = () => { if (run.length) blocks.push(blockFor(run, estimateDurationMs)); run = []; };
  for (const s of seq) {
    if (s.taskIndex === undefined) {
      flush();
      if (s.type === 'sync_clapper') {
        blocks.push({ kind: 'sync', title: 'Screen flash', detail: 'lines the recording up with the screen',
          ms: estimateDurationMs([s]), taskIndex: null });
      } else if (s.type === 'instruction' && s.id === 'intro') {
        blocks.push({ kind: 'instruction', title: 'Overview', detail: s.title ?? '', ms: estimateDurationMs([s]), taskIndex: null });
      }
      continue;
    }
    if (run.length && run[0].taskIndex !== s.taskIndex) flush();
    run.push(s);
  }
  flush();

  const records = study.consent_tiers?.length === 1 && tiers[0] === 'features_in_browser'
    ? 'nothing recorded — measured in the browser'
    : `camera${audio ? ' and microphone' : ''} recording`;
  const after = [
    { kind: 'finish', title: 'Send or download', detail: 'bundle leaves the device only now' },
  ];
  if (study.recruitment?.completion_url) {
    after.push({ kind: 'finish', title: 'Back to the panel', detail: 'completion link, after the data is saved' });
  }
  return { arm, before, blocks, after, records, totalMs: estimateDurationMs(seq) };
}

/** One model per arm, or a single one for a study without conditions. */
export function flowModels(study, deps) {
  const arms = study.conditions?.arms?.length ? study.conditions.arms : [null];
  return arms.map((a) => flowModel(study, deps, a));
}

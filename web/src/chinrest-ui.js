/**
 * Virtual chinrest — the interactive half.
 *
 * Deliberately thin. Every number this file produces is a raw measurement in
 * CSS pixels; all arithmetic, all gating and all refusal logic lives in
 * `chinrest.js`, which is pure and tested. The split is the point: the parts
 * that can be wrong in a way that silently corrupts dva figures are the parts
 * that run in `node --test`, not the parts that need a participant and a
 * webcam to exercise.
 *
 * The DOM here is created rather than declared in index.html because these two
 * tasks are self-contained and temporary — they run once, before capture, and
 * leave nothing behind.
 */

import {
  CARD_WIDTH_MM,
  CARD_HEIGHT_MM,
  EDGE_SATURATION_FRACTION,
  VIEWING_DISTANCE_BOUNDS_MM,
  pxPerMmFromCard,
  checkCardPlausible,
  viewingDistanceMmFromBlindSpot,
  deriveGeometry,
} from './chinrest.js';

/** jsPsych's default repetition count. Five is enough for a median to mean something. */
const BLIND_SPOT_REPS = 5;

/** Dot travel speed, px per animation frame. Slow enough to mark accurately. */
const BALL_SPEED_PX = 2;

/**
 * Run both tasks and return a geometry record.
 *
 * Resolves with whatever `deriveGeometry` decided, including a refusal. The
 * caller must handle `ok: false` — a refusal is a legitimate outcome of a
 * correctly-run chinrest, not an exception.
 *
 * @param {HTMLElement} host element to mount into
 * @param {{onRetry?: (reason: string) => void}} [hooks]
 */
export async function runVirtualChinrest(host, hooks = {}) {
  const root = document.createElement('div');
  root.className = 'chinrest';
  host.appendChild(root);

  try {
    const cardWidthPx = await runCardTask(root, hooks);
    const blind = await runBlindSpotTask(root, pxPerMmFromCard(cardWidthPx));
    return deriveGeometry({
      cardWidthPx,
      blindSpotDistancesPx: blind.distancesPx,
      // How far the dot COULD have travelled. Without this the geometry cannot
      // tell a blind spot from the left edge of the screen.
      blindSpotMaxTravelPx: blind.maxTravelPx,
    });
  } finally {
    root.remove();
  }
}

// ---------------------------------------------------------------------------
// task 1 — card
// ---------------------------------------------------------------------------

/**
 * Resize an outline to match a real card.
 *
 * The aspect ratio is locked to the real card's. Letting the participant
 * distort it would give them a way to produce a "matching" rectangle that
 * matches nothing, and would make the width measurement meaningless.
 *
 * Retries in place on an implausible result rather than accepting and flagging:
 * §5.1 attributes roughly half of a documented 46-66% attrition to avoidable
 * validation failures, and the only moment at which one is cheaply fixable is
 * while the participant is still holding the card.
 */
function runCardTask(root, hooks) {
  return new Promise((resolve) => {
    root.innerHTML = `
      <div class="cr-panel">
        <h1>Screen size check</h1>
        <p>We need to know how big your screen actually is. Screens report their
           size in pixels, and pixels are different physical sizes on different
           displays — so the only reliable way is to compare against something
           of a known size. Bank cards are identical worldwide.</p>
        <ol class="cr-steps">
          <li>Find a <strong>bank card, library card or driving licence</strong>.</li>
          <li><strong>Hold it flat against the screen</strong>, over the outline below.</li>
          <li>Drag the blue corner until the outline is <strong>exactly</strong> the
              same size as your card. Use the arrow keys for fine adjustment.</li>
        </ol>
        <div class="cr-cardwrap">
          <div class="cr-card" id="crCard"><div class="cr-grip" id="crGrip"></div></div>
        </div>
        <p class="cr-error" id="crError"></p>
        <button id="crCardDone">That matches</button>
      </div>`;

    const card = root.querySelector('#crCard');
    const grip = root.querySelector('#crGrip');
    const error = root.querySelector('#crError');
    const done = root.querySelector('#crCardDone');

    // Start near CSS-reference density so a correct display needs little
    // adjustment, but not exactly — an already-correct default invites
    // click-through without measuring.
    let widthPx = 300;
    const aspect = CARD_HEIGHT_MM / CARD_WIDTH_MM;

    const draw = () => {
      card.style.width = `${widthPx}px`;
      card.style.height = `${widthPx * aspect}px`;
    };
    draw();

    let dragging = false;
    let dragStartX = 0;
    let dragStartWidth = 0;

    const onDown = (ev) => {
      dragging = true;
      dragStartX = ev.clientX ?? ev.touches[0].clientX;
      dragStartWidth = widthPx;
      ev.preventDefault();
    };
    const onMove = (ev) => {
      if (!dragging) return;
      const x = ev.clientX ?? ev.touches?.[0]?.clientX;
      if (x === undefined) return;
      widthPx = Math.max(40, dragStartWidth + (x - dragStartX));
      draw();
    };
    const onUp = () => { dragging = false; };

    grip.addEventListener('mousedown', onDown);
    grip.addEventListener('touchstart', onDown, { passive: false });
    window.addEventListener('mousemove', onMove);
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('mouseup', onUp);
    window.addEventListener('touchend', onUp);

    // Keyboard adjustment, because a trackpad drag is imprecise at the
    // last few pixels and those pixels are the measurement.
    const onKey = (ev) => {
      const step = ev.shiftKey ? 10 : 1;
      if (ev.key === 'ArrowRight') { widthPx += step; draw(); ev.preventDefault(); }
      if (ev.key === 'ArrowLeft') { widthPx = Math.max(40, widthPx - step); draw(); ev.preventDefault(); }
    };
    window.addEventListener('keydown', onKey);

    const cleanup = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('mouseup', onUp);
      window.removeEventListener('touchend', onUp);
      window.removeEventListener('keydown', onKey);
    };

    done.addEventListener('click', () => {
      // Measure what is actually ON SCREEN, not the value we intended to draw.
      //
      // These differ if anything in the layout clamps the element — a flex
      // parent shrinking it, a max-width, a zoomed page. The participant matched
      // their real card against the rendered outline, so the rendered width is
      // the measurement by definition; the internal value is only a request.
      // Trusting the request is how this task silently returns a px/mm for a
      // rectangle nobody ever saw. (Observed: an internal 2780px rendering at
      // 535px inside the panel's flex container.)
      const renderedWidthPx = card.getBoundingClientRect().width;
      const check = checkCardPlausible(pxPerMmFromCard(renderedWidthPx));
      if (!check.plausible) {
        error.textContent = check.detail;
        hooks.onRetry?.(check.reason);
        return;
      }
      cleanup();
      resolve(renderedWidthPx);
    });
  });
}

// ---------------------------------------------------------------------------
// task 2 — blind spot
// ---------------------------------------------------------------------------

/**
 * Map the blind spot, `BLIND_SPOT_REPS` times, after one practice round.
 *
 * The participant covers their right eye, fixates the cross with the left, and
 * presses space when the moving dot disappears. The dot travels left from the
 * cross, into the temporal field of the open eye, which is where the optic disc
 * projects.
 *
 * The practice round is not politeness. This is the least intuitive thing the
 * whole session asks of anyone — it requires trusting that a dot in plain view
 * will vanish — and the first real participant, who had built the software,
 * still got it wrong: every mark landed at the end of the dot's travel, meaning
 * the dot never entered the blind spot at all. That failure is invisible to the
 * participant and produces a confident, wrong measurement.
 *
 * One practice repetition with honest feedback catches it while it is still
 * fixable, which is the same argument §5.1 makes for validating the card task at
 * entry rather than counting the loss at analysis.
 */
async function runBlindSpotTask(root, pxPerMm) {
  await showBlindSpotIntro(root);

  // Practice until it works, or until they choose to move on regardless.
  for (;;) {
    const practice = await runBlindSpotRep(root, { practice: true });
    const verdict = judgePractice(practice, pxPerMm);
    const choice = await showPracticeResult(root, verdict);
    if (choice === 'continue') break;
  }

  const distancesPx = [];
  let maxTravelPx = null;
  for (let i = 0; i < BLIND_SPOT_REPS; i += 1) {
    const rep = await runBlindSpotRep(root, {
      practice: false, index: i + 1, total: BLIND_SPOT_REPS,
    });
    distancesPx.push(rep.offsetPx);
    maxTravelPx = rep.maxTravelPx;
  }
  return { distancesPx, maxTravelPx };
}

function showBlindSpotIntro(root) {
  return new Promise((resolve) => {
    root.innerHTML = `
      <div class="cr-panel">
        <h1>Finding your blind spot</h1>
        <p>Everyone has a small gap in their vision where the optic nerve leaves
           the eye. You never notice it, because the other eye covers it and your
           brain fills in the rest. Finding it tells us how far you are sitting
           from the screen, which we need in order to interpret everything else.</p>
        <ol class="cr-steps">
          <li><strong>Cup your right hand over your right eye.</strong> Not fingers
              across it — properly covered, so it sees nothing at all.</li>
          <li><strong>Look straight at the black cross</strong> with your left eye,
              and keep looking at it.</li>
          <li>A dot will move slowly left. <strong>Do not follow it</strong> — keep
              staring at the cross and watch the dot out of the corner of your eye.</li>
          <li>At some point the dot will <strong>completely disappear</strong>.
              That is your blind spot.
              <strong>Press space the moment it vanishes.</strong></li>
        </ol>
        <p class="cr-hint">It really does disappear, and it is sudden and obvious
           when it happens. If it never disappears, your right eye is probably not
           fully covered, or your gaze is drifting to follow the dot.</p>
        <p>We will do one practice first. That one does not count.</p>
        <button id="crBsStart">Start practice</button>
      </div>`;
    root.querySelector('#crBsStart').addEventListener('click', resolve, { once: true });
  });
}

/** One repetition. Resolves with the offset in px, or NaN if the dot ran off. */
function runBlindSpotRep(root, { practice, index, total }) {
  return new Promise((resolve) => {
    const label = practice ? 'practice' : `${index} of ${total}`;
    root.innerHTML = `
      <div class="cr-field" id="crField">
        <div class="cr-cross" id="crCross">+</div>
        <div class="cr-ball" id="crBall"></div>
        <div class="cr-count" id="crCount">${label}</div>
        <div class="cr-remind" id="crRemind">
          right eye covered &middot; look at the cross &middot; space when the dot vanishes
        </div>
      </div>`;

    const field = root.querySelector('#crField');
    const cross = root.querySelector('#crCross');
    const ball = root.querySelector('#crBall');

    const rect = field.getBoundingClientRect();
    // The cross sits far right so the dot has as much room as possible to
    // travel left. Travel is the binding constraint on what this task can
    // measure at all: the blind spot sits at d*tan(13.5deg) from fixation, so
    // the furthest measurable distance is (travel / pxPerMm) / tan(13.5deg).
    //
    // At 0.75 on a 1707px screen at 5.48 px/mm that ceiling was 97cm — and a
    // real participant hit it, producing four agreeing marks nine pixels from
    // the edge and a confident, meaningless 96.6cm. 0.9 lifts the ceiling to
    // ~116cm and costs nothing; the dot only ever needs room on its left.
    const crossX = rect.width * 0.9;
    const crossY = rect.height * 0.5;
    cross.style.left = `${crossX}px`;
    cross.style.top = `${crossY}px`;

    let ballX = crossX - 20;
    ball.style.top = `${crossY}px`;
    ball.style.left = `${ballX}px`;
    ball.style.display = 'block';

    let raf = null;
    const finish = (offsetPx) => {
      cancelAnimationFrame(raf);
      window.removeEventListener('keydown', onKey);
      ball.style.display = 'none';
      resolve({ offsetPx, maxTravelPx: crossX });
    };

    const step = () => {
      ballX -= BALL_SPEED_PX;
      ball.style.left = `${ballX}px`;
      if (ballX < 0) {
        // Ran the full width without being marked: the dot never vanished.
        finish(NaN);
        return;
      }
      raf = requestAnimationFrame(step);
    };

    const onKey = (ev) => {
      if (ev.code !== 'Space') return;
      ev.preventDefault();
      finish(crossX - ballX);
    };

    window.addEventListener('keydown', onKey);
    raf = requestAnimationFrame(step);
  });
}

/**
 * What the practice repetition tells us, in participant terms.
 *
 * Each failure mode gets its own wording, because they need different fixes and
 * a generic "try again" tells the participant nothing they can act on.
 */
function judgePractice({ offsetPx, maxTravelPx }, pxPerMm) {
  if (!Number.isFinite(offsetPx)) {
    return {
      ok: false,
      title: 'The dot never disappeared',
      detail: 'It ran all the way off the edge of the screen without being marked.',
    };
  }
  if (offsetPx >= maxTravelPx * EDGE_SATURATION_FRACTION) {
    return {
      ok: false,
      title: 'That was right at the edge',
      detail: 'You marked the dot just as it was about to leave the screen, which '
        + 'usually means it never actually vanished into your blind spot.',
    };
  }

  const mm = viewingDistanceMmFromBlindSpot(offsetPx, pxPerMm);
  if (mm < VIEWING_DISTANCE_BOUNDS_MM.min) {
    return {
      ok: false,
      title: 'That was very early',
      detail: 'The dot had barely started moving. Wait for it to actually vanish — '
        + 'it takes a few seconds, and it is unmistakable when it happens.',
    };
  }
  return {
    ok: true,
    title: 'That looks right',
    detail: `That puts you about ${Math.round(mm / 10)}cm from the screen, which is `
      + 'a normal sitting distance. Now the same thing five more times.',
  };
}

function showPracticeResult(root, verdict) {
  return new Promise((resolve) => {
    const tips = verdict.ok ? '' : `
      <ul class="cr-steps">
        <li>Is your right eye <strong>completely</strong> covered? Cup your palm over it.</li>
        <li>Are you staring at the cross the whole time? Glancing at the dot is
            very tempting, and it is what stops the dot disappearing.</li>
        <li>Sitting closer helps. About an arm's length from the screen works well.</li>
      </ul>`;

    root.innerHTML = `
      <div class="cr-panel">
        <h1>${verdict.title}</h1>
        <p>${verdict.detail}</p>
        ${tips}
        <p class="cr-actions">
          <button id="crAgain" class="${verdict.ok ? 'cr-secondary' : ''}">
            Try the practice again
          </button>
          <button id="crGo" class="${verdict.ok ? '' : 'cr-secondary'}">
            ${verdict.ok ? 'Start the real thing' : 'Continue anyway'}
          </button>
        </p>
      </div>`;

    root.querySelector('#crAgain')
      .addEventListener('click', () => resolve('again'), { once: true });
    root.querySelector('#crGo')
      .addEventListener('click', () => resolve('continue'), { once: true });
  });
}

/** Styles for the tasks, injected so index.html stays about the capture page. */
export const CHINREST_CSS = `
.chinrest { position: fixed; inset: 0; z-index: 30; background: var(--bg);
            display: flex; align-items: center; justify-content: center; }
.cr-panel { max-width: min(1100px, 94vw); padding: 32px; background: var(--panel);
            border: 1px solid var(--border); border-radius: 10px; }
.cr-cardwrap { margin: 24px 0; padding: 20px; background: #0b0d10;
               border-radius: 8px; display: flex; justify-content: flex-start;
               /* Scroll rather than shrink. A clamped card is measured wrong. */
               overflow-x: auto; }
.cr-card { position: relative; background: #2a2f37; border: 2px solid var(--accent);
           border-radius: 10px;
           /* Non-negotiable: a flex parent shrinking this element would make the
              rendered outline differ from the measured one. */
           flex-shrink: 0; }
.cr-grip { position: absolute; right: -9px; bottom: -9px; width: 20px; height: 20px;
           background: var(--accent); border-radius: 50%; cursor: nwse-resize; }
.cr-error { color: var(--bad); min-height: 1.5em; }
.consent-panel { max-height: 92vh; overflow-y: auto; }
.consent-tier { display: flex; gap: 10px; align-items: flex-start;
                padding: 12px 14px; margin: 8px 0; border-radius: 8px;
                border: 1px solid var(--border); cursor: pointer; }
.consent-tier:hover { border-color: var(--accent); }
.consent-tier input { margin-top: 3px; }
.consent-tier ul { margin: 6px 0; padding-left: 18px; }
.consent-tier li { color: var(--muted); font-size: 13px; margin-bottom: 3px; }
.consent-summary { display: block; color: var(--fg); margin-top: 2px; }
.consent-consequence { display: block; color: var(--muted); font-size: 13px;
                       font-style: italic; }
.consent-ack { margin-top: 18px; }
.consent-ack label { display: flex; gap: 8px; align-items: center; }
.cr-field { position: fixed; inset: 0; background: #7f7f7f; }
.cr-cross { position: absolute; transform: translate(-50%,-50%);
            font-size: 34px; color: #111; }
.cr-ball { position: absolute; width: 18px; height: 18px; margin: -9px 0 0 -9px;
           border-radius: 50%; background: #111; display: none; }
.cr-count { position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%);
            color: #333; font-size: 13px; }
/* A standing reminder of the three things people forget mid-task. Dim and at
   the top, well away from the cross and the dot's path. */
.cr-remind { position: absolute; left: 50%; top: 18px; transform: translateX(-50%);
             color: #4a4a4a; font-size: 12px; letter-spacing: .02em; }
.cr-steps { margin: 18px 0; padding-left: 22px; }
.cr-steps li { margin-bottom: 10px; line-height: 1.5; color: var(--fg); }
.cr-hint { font-size: 14px; border-left: 2px solid var(--border); padding-left: 12px; }
.cr-actions { display: flex; gap: 10px; margin: 22px 0 0; }
.cr-secondary { background: transparent; border: 1px solid var(--border); color: var(--fg); }
`;

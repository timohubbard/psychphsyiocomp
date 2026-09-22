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
  pxPerMmFromCard,
  checkCardPlausible,
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
    const blindSpotDistancesPx = await runBlindSpotTask(root, pxPerMmFromCard(cardWidthPx));
    return deriveGeometry({ cardWidthPx, blindSpotDistancesPx });
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
        <p>Hold a bank card, library card or driving licence against the screen.
           Drag the corner until the outline is exactly the same size as your card.</p>
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
 * Map the blind spot, `BLIND_SPOT_REPS` times.
 *
 * The participant covers their right eye, fixates the cross with the left, and
 * presses space when the moving dot disappears. The dot travels left from the
 * cross, so it moves into the temporal field of the open eye.
 *
 * We cannot verify that they covered an eye or held fixation. The only
 * available evidence is whether the repetitions agree — which is why
 * `deriveGeometry` refuses on wide spread rather than averaging it away.
 */
function runBlindSpotTask(root, pxPerMm) {
  return new Promise((resolve) => {
    root.innerHTML = `
      <div class="cr-panel">
        <h1>Distance check</h1>
        <p><strong>Cover your right eye</strong> with your hand and look at the
           black cross with your left eye. A dot will move across the screen.
           Press <strong>space</strong> the moment it disappears.</p>
        <p>Keep your head still and do not follow the dot with your eye.</p>
        <button id="crBsStart">Start</button>
      </div>`;

    root.querySelector('#crBsStart').addEventListener('click', () => {
      root.innerHTML = `
        <div class="cr-field" id="crField">
          <div class="cr-cross" id="crCross">+</div>
          <div class="cr-ball" id="crBall"></div>
          <div class="cr-count" id="crCount"></div>
        </div>`;

      const field = root.querySelector('#crField');
      const cross = root.querySelector('#crCross');
      const ball = root.querySelector('#crBall');
      const count = root.querySelector('#crCount');

      const rect = field.getBoundingClientRect();
      // The cross sits right of centre so the dot has room to travel left
      // through the full plausible blind-spot eccentricity at close distances.
      const crossX = rect.width * 0.75;
      const crossY = rect.height * 0.5;
      cross.style.left = `${crossX}px`;
      cross.style.top = `${crossY}px`;

      const distances = [];
      let ballX = crossX;
      let raf = null;

      const startRep = () => {
        count.textContent = `${distances.length + 1} of ${BLIND_SPOT_REPS}`;
        ballX = crossX - 20;
        ball.style.top = `${crossY}px`;
        ball.style.display = 'block';
        step();
      };

      const step = () => {
        ballX -= BALL_SPEED_PX;
        ball.style.left = `${ballX}px`;

        // Ran off the edge without a keypress: the dot never vanished, or the
        // participant missed it. Record NaN so `summariseBlindSpotReps` counts
        // it as rejected rather than letting a short run look like a full one.
        if (ballX < 0) {
          distances.push(NaN);
          nextRep();
          return;
        }
        raf = requestAnimationFrame(step);
      };

      const nextRep = () => {
        cancelAnimationFrame(raf);
        ball.style.display = 'none';
        if (distances.length >= BLIND_SPOT_REPS) {
          window.removeEventListener('keydown', onKey);
          resolve(distances);
          return;
        }
        setTimeout(startRep, 600);
      };

      const onKey = (ev) => {
        if (ev.code !== 'Space') return;
        ev.preventDefault();
        if (ball.style.display === 'none') return;
        distances.push(crossX - ballX);
        nextRep();
      };

      window.addEventListener('keydown', onKey);
      startRep();
    });

    void pxPerMm; // conversion happens in deriveGeometry, on raw pixels
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
.cr-field { position: fixed; inset: 0; background: #7f7f7f; }
.cr-cross { position: absolute; transform: translate(-50%,-50%);
            font-size: 34px; color: #111; }
.cr-ball { position: absolute; width: 18px; height: 18px; margin: -9px 0 0 -9px;
           border-radius: 50%; background: #111; display: none; }
.cr-count { position: absolute; left: 50%; bottom: 24px; transform: translateX(-50%);
            color: #333; font-size: 13px; }
`;

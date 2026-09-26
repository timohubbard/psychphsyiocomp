/**
 * Drive the virtual chinrest in headless Chrome, as a participant would.
 *
 * Why this exists: smoke:capture could not complete the chinrest, so it could
 * not run m0 — the protocol every real session so far was collected under. The
 * chinrest is two tasks: size an outline to a bank card, then mark the moment a
 * moving dot vanishes into the blind spot, five times after a practice.
 *
 * Both are driven with a chosen, known "truth" so the geometry the page derives
 * can be checked against it:
 *
 *   card   Arrow keys (the page's own fine-adjustment path) until the rendered
 *          outline is CARD_WIDTH_MM at the chosen px/mm. The page measures the
 *          RENDERED width, so that is what is steered, not the internal value.
 *   blind  The blind spot sits at d * tan(13.5 deg) from fixation, the relation
 *          chinrest.js inverts. A watcher in the page fires the Space keydown in
 *          the same animation frame the dot reaches that offset — a CDP poll
 *          would lag the 2 px/frame dot by several pixels. Each rep carries a
 *          little jitter, because five identical marks are not what a person
 *          produces and the page's spread check should see realistic input.
 *
 * The keydown is synthetic (isTrusted false). The page does not check it, and
 * this proves the task's wiring and arithmetic end to end — not that a human
 * can do it, which the pilot sessions already showed.
 */

import { setTimeout as sleep } from 'node:timers/promises';

import { CARD_WIDTH_MM } from '../web/src/chinrest.js';

const BLIND_SPOT_ANGLE_DEG = 13.5;

/**
 * Complete both chinrest tasks. Returns what was intended, so the caller can
 * compare it with the geometry the page recorded.
 */
export async function driveChinrest(page, { pxPerMm = 3.78, distanceMm = 500, jitterPx = 2,
                                            log = () => {} } = {}) {
  // --- card -------------------------------------------------------------
  await page.until(`!!document.getElementById('crCard')`, 'the card task');
  const targetWidth = CARD_WIDTH_MM * pxPerMm;
  for (let i = 0; i < 400; i += 1) {
    const w = await page.js(`document.getElementById('crCard').getBoundingClientRect().width`);
    const diff = targetWidth - w;
    if (Math.abs(diff) < 0.75) break;
    const big = Math.abs(diff) >= 10;
    await page.send('Input.dispatchKeyEvent', {
      type: 'keyDown', key: diff > 0 ? 'ArrowRight' : 'ArrowLeft', code: diff > 0 ? 'ArrowRight' : 'ArrowLeft',
      windowsVirtualKeyCode: diff > 0 ? 39 : 37, modifiers: big ? 8 : 0,
    });
    await page.send('Input.dispatchKeyEvent', {
      type: 'keyUp', key: diff > 0 ? 'ArrowRight' : 'ArrowLeft', code: diff > 0 ? 'ArrowRight' : 'ArrowLeft',
      windowsVirtualKeyCode: diff > 0 ? 39 : 37, modifiers: big ? 8 : 0,
    });
  }
  const rendered = await page.js(`document.getElementById('crCard').getBoundingClientRect().width`);
  const actualPxPerMm = rendered / CARD_WIDTH_MM;
  log(`chinrest card: ${rendered.toFixed(1)} px rendered -> ${actualPxPerMm.toFixed(3)} px/mm`);
  await page.js(`document.getElementById('crCardDone').click()`);
  const cardError = await page.js(`document.getElementById('crError')?.textContent ?? ''`);
  if (cardError) throw new Error(`card task refused: ${cardError}`);

  // --- blind spot -------------------------------------------------------
  await page.until(`!!document.getElementById('crBsStart')`, 'the blind-spot intro');
  await page.js(`document.getElementById('crBsStart').click()`);

  const offsetPx = distanceMm * Math.tan((BLIND_SPOT_ANGLE_DEG * Math.PI) / 180) * actualPxPerMm;
  const marks = [];
  // Practice, then five real reps.
  for (let rep = 0; rep < 6; rep += 1) {
    await page.until(`document.getElementById('crBall')?.style.display === 'block'`, `blind-spot rep ${rep}`);
    const target = offsetPx + (rep === 0 ? 0 : ((rep % 3) - 1) * jitterPx);
    const marked = await page.js(`new Promise((ok) => {
      const cross = document.getElementById('crCross');
      const ball = document.getElementById('crBall');
      const crossX = parseFloat(cross.style.left);
      const tick = () => {
        const off = crossX - parseFloat(ball.style.left);
        if (off >= ${target}) {
          window.dispatchEvent(new KeyboardEvent('keydown', { code: 'Space', key: ' ' }));
          ok(off);
        } else {
          requestAnimationFrame(tick);
        }
      };
      requestAnimationFrame(tick);
    })`);
    marks.push(marked);
    if (rep === 0) {
      await page.until(`!!document.getElementById('crGo')`, 'the practice result');
      const title = await page.js(`document.querySelector('.cr-panel h1')?.textContent ?? ''`);
      log(`chinrest practice: "${title}" at ${marked.toFixed(0)} px`);
      if (!/looks right/i.test(title)) throw new Error(`practice judged "${title}"`);
      await page.js(`document.getElementById('crGo').click()`);
    }
    await sleep(100);
  }
  log(`chinrest blind spot: marks ${marks.slice(1).map((m) => m.toFixed(0)).join(', ')} px (target ${offsetPx.toFixed(0)})`);
  return { pxPerMm: actualPxPerMm, distanceMm, offsetPx, marks };
}

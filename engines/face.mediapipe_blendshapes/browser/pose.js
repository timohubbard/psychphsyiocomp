/**
 * Pure geometry helpers, split out from engine.js so they can be unit-tested
 * in Node without pulling in the MediaPipe WASM bundle or a DOM.
 */

/**
 * Extract yaw/pitch/roll (degrees) from MediaPipe's 4x4 facial transformation
 * matrix.
 *
 * MediaPipe emits column-major data, so element(row, col) = m[col * 4 + row].
 * The rotation is the upper-left 3x3.
 *
 * Decomposed as R = Ry(yaw) · Rx(pitch) · Rz(roll) — the intrinsic Y-X-Z order,
 * which is the head-pose convention:
 *
 *   yaw   — about Y (vertical axis), "looking left/right"
 *   pitch — about X (lateral axis),  "nodding up/down"
 *   roll  — about Z (depth axis),    "tilting toward a shoulder"
 *
 * Note this is NOT the aerospace Z-Y-X ordering. Under Z-Y-X a pure X-rotation
 * decomposes into roll, which for a face is exactly backwards — a nod would be
 * reported as a head tilt. The unit tests pin each axis independently to keep
 * that from regressing.
 *
 * Head pose is tier `high` because it derives from landmark geometry directly
 * rather than from a learned expression classifier — unlike the blendshape
 * channels, which carry real accuracy caveats (REPORT.md §2.2).
 *
 * @param {ArrayLike<number>} m 16-element column-major 4x4 matrix
 * @returns {{yaw: number, pitch: number, roll: number}} degrees
 */
export function eulerFromMatrix(m) {
  if (!m || m.length < 16) {
    throw new TypeError(`expected a 16-element matrix, got ${m?.length}`);
  }

  // element(row, col) = m[col * 4 + row]
  const r02 = m[8];  // (0,2)
  const r10 = m[1];  // (1,0)
  const r11 = m[5];  // (1,1)
  const r12 = m[9];  // (1,2)
  const r22 = m[10]; // (2,2)

  // For R = Ry·Rx·Rz:  r12 = -sin(pitch), r02 = sy·cp, r22 = cy·cp,
  //                    r10 = cp·sr,       r11 = cp·cr
  const pitch = Math.atan2(-r12, Math.hypot(r10, r11));
  const yaw = Math.atan2(r02, r22);
  const roll = Math.atan2(r10, r11);

  return {
    yaw: toDegrees(yaw),
    pitch: toDegrees(pitch),
    roll: toDegrees(roll),
  };
}

export function toDegrees(radians) {
  return (radians * 180) / Math.PI;
}

/**
 * Rec. 601 luma from packed RGBA bytes. Used for the session lighting check.
 *
 * §2.5 is the reason this exists: the rPPG heart-rate accuracy gap between
 * Fitzpatrick type 1 and type 5 collapses from ~2.25 bpm to ~0.21 bpm once
 * luminance clears 30. That is the only quantified bias mitigation anywhere in
 * the evidence base, so measuring luminance is a fairness control, not a
 * nice-to-have diagnostic.
 *
 * @param {Uint8ClampedArray} rgba
 * @returns {number} mean luma, 0-255
 */
export function meanLuma(rgba) {
  if (!rgba || rgba.length === 0) return 0;
  let sum = 0;
  const n = rgba.length / 4;
  for (let i = 0; i < rgba.length; i += 4) {
    sum += 0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2];
  }
  return sum / n;
}

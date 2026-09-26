/**
 * gaze.mediapipe_features — the feature maths, in the browser.
 *
 * A line-for-line port of `eye_features` and `features_from_landmarks` in
 * ../server/engine.py, which carries the reasoning (normalising by the eye's
 * own width, measuring in pixels rather than MediaPipe's per-axis normalised
 * units, subject-left vs image-left). Kept pure — no MediaPipe, no DOM — so a
 * golden fixture can prove the two placements compute the same numbers from
 * the same landmarks (../fixtures/landmarks_golden.json, asserted in both
 * suites). If they ever differ, a session processed in the browser and one
 * processed on the server stop being comparable, silently.
 *
 * It exists for the `features_in_browser` consent tier, where the video never
 * leaves the participant's machine, so there is nothing for the server engine
 * to read. It also runs in ordinary sessions, as a second placement of the
 * same engine to compare against — the M0 pattern, applied to gaze.
 */

// Landmark indices — MediaPipe's 478-point mesh. SUBJECT's left and right,
// exactly as in the server engine.
export const RIGHT_IRIS_CENTRE = 468;
export const LEFT_IRIS_CENTRE = 473;
export const RIGHT_EYE_OUTER = 33;
export const RIGHT_EYE_INNER = 133;
export const LEFT_EYE_INNER = 362;
export const LEFT_EYE_OUTER = 263;
export const RIGHT_EYE_UPPER = 159;
export const RIGHT_EYE_LOWER = 145;
export const LEFT_EYE_UPPER = 386;
export const LEFT_EYE_LOWER = 374;

/** Below this aperture the iris is occluded; see MIN_OPENNESS in the server engine. */
export const MIN_OPENNESS = 0.10;

/** The estimator's channel order. Must equal FEATURE_CHANNELS in the server engine. */
export const FEATURE_CHANNELS = [
  'eye.left_iris_dx', 'eye.left_iris_dy',
  'eye.right_iris_dx', 'eye.right_iris_dy',
  'eye.left_openness', 'eye.right_openness',
  'eye.inter_ocular_px',
  'head_pose.yaw', 'head_pose.pitch', 'head_pose.roll',
];

export const RELIABILITY = {
  'eye.left_iris_dx': 'moderate', 'eye.right_iris_dx': 'moderate',
  'eye.left_iris_dy': 'low', 'eye.right_iris_dy': 'low',
  'eye.left_openness': 'moderate', 'eye.right_openness': 'moderate',
  'eye.inter_ocular_px': 'moderate',
  'head_pose.yaw': 'high', 'head_pose.pitch': 'high', 'head_pose.roll': 'high',
};

const dist = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/**
 * Normalised iris offset and eyelid aperture for one eye: [dx, dy, openness].
 * Corners are an unordered pair, as on the server.
 */
export function eyeFeatures(iris, cornerA, cornerB, lidUpper, lidLower) {
  const width = dist(cornerA, cornerB);
  if (width <= 1e-9) return [NaN, NaN, NaN];
  const cx = (cornerA[0] + cornerB[0]) / 2;
  const cy = (cornerA[1] + cornerB[1]) / 2;
  return [(iris[0] - cx) / width, (iris[1] - cy) / width, dist(lidUpper, lidLower) / width];
}

/**
 * One frame's landmarks ({x, y} normalised, as MediaPipe returns them) to the
 * feature object, or null if unusable. Pixels first, then distances.
 */
export function featuresFromLandmarks(landmarks, widthPx, heightPx) {
  if (!landmarks || landmarks.length <= Math.max(LEFT_IRIS_CENTRE, LEFT_EYE_OUTER)) return null;
  const p = (i) => [landmarks[i].x * widthPx, landmarks[i].y * heightPx];

  const [rDx, rDy, rOpen] = eyeFeatures(
    p(RIGHT_IRIS_CENTRE), p(RIGHT_EYE_OUTER), p(RIGHT_EYE_INNER),
    p(RIGHT_EYE_UPPER), p(RIGHT_EYE_LOWER));
  const [lDx, lDy, lOpen] = eyeFeatures(
    p(LEFT_IRIS_CENTRE), p(LEFT_EYE_OUTER), p(LEFT_EYE_INNER),
    p(LEFT_EYE_UPPER), p(LEFT_EYE_LOWER));

  if ([rDx, rDy, rOpen, lDx, lDy, lOpen].some(Number.isNaN)) return null;
  return {
    'eye.right_iris_dx': rDx,
    'eye.right_iris_dy': rDy,
    'eye.right_openness': rOpen,
    'eye.left_iris_dx': lDx,
    'eye.left_iris_dy': lDy,
    'eye.left_openness': lOpen,
    'eye.inter_ocular_px': dist(p(LEFT_IRIS_CENTRE), p(RIGHT_IRIS_CENTRE)),
  };
}

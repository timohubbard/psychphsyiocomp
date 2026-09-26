/**
 * gaze.mediapipe_features — browser-live placement.
 *
 * Emits the same channels as the server engine, from the FaceLandmarker result
 * the blendshape engine already computes each frame (`attachTo`), so gaze
 * costs no second inference. Features only, never a gaze direction — the
 * estimator stays a server-side stage that needs the calibration events.
 *
 * Why it exists: under the `features_in_browser` consent tier the recording
 * never leaves the participant's machine, so these rows are the only gaze
 * measurement the session will ever have. In an ordinary session they are a
 * second placement beside the server pass, with their own `source`, to be
 * compared rather than merged.
 */

import manifest from '../engine.manifest.json' with { type: 'json' };
import { eulerFromMatrix } from '../../face.mediapipe_blendshapes/browser/pose.js';
import { MIN_OPENNESS, RELIABILITY, featuresFromLandmarks } from './features.js';

const QUALITY_WINDOW_MS = 5000;

export const SOURCE = `${manifest.engine_id}@${manifest.version}+browser-live`;

export class MediaPipeGazeFeaturesLive {
  constructor() {
    this.manifest = { ...manifest, placement: 'browser-live', runtime: 'wasm' };
    this.source = SOURCE;
    this._outputCb = null;
    this._resetWindow(null);
  }

  /** Subscribe to a MediaPipeBlendshapesLive engine's per-frame landmarker result. */
  attachTo(faceEngine) {
    faceEngine.onResult((result, ts, size) => this._onResult(result, ts, size));
  }

  onOutput(cb) {
    this._outputCb = cb;
  }

  _resetWindow(start) {
    this._windowStart = start;
    this._frames = 0;
    this._faces = 0;
    this._irisOk = 0;
  }

  _onResult(result, ts, { width, height }) {
    if (this._windowStart === null) this._windowStart = ts.native_ts;
    this._frames += 1;

    const signals = [];
    const landmarks = result.faceLandmarks?.[0];
    if (landmarks) {
      this._faces += 1;
      const feats = featuresFromLandmarks(landmarks, width, height);
      // Both eyes shut: the iris estimate is meaningless, not noisy — dropped
      // and counted, exactly as the server engine does.
      const closed = feats && feats['eye.left_openness'] < MIN_OPENNESS
        && feats['eye.right_openness'] < MIN_OPENNESS;
      if (feats && !closed) {
        this._irisOk += 1;
        for (const [channel, value] of Object.entries(feats)) {
          signals.push(this._row(channel, value, ts));
        }
        const matrix = result.facialTransformationMatrixes?.[0]?.data;
        if (matrix) {
          for (const [axis, value] of Object.entries(eulerFromMatrix(matrix))) {
            signals.push(this._row(`head_pose.${axis}`, value, ts));
          }
        }
      }
    }

    const quality = ts.native_ts - this._windowStart >= QUALITY_WINDOW_MS
      ? this._quality(ts.native_ts) : [];
    if (this._outputCb && (signals.length || quality.length)) {
      this._outputCb({ source: this.source, signals, events: [], quality });
    }
  }

  _row(channel, value, ts) {
    return {
      stream: 'gaze', channel, native_clock_id: ts.native_clock_id,
      native_ts: ts.native_ts, value, reliability_tier: RELIABILITY[channel],
    };
  }

  /** face_detect_rate and iris_valid_rate — the second says gaze was measurable. */
  _quality(endTs) {
    const row = (metric, value) => ({
      stream: 'gaze', metric, window_start_native_ts: this._windowStart,
      window_end_native_ts: endTs, value,
    });
    const rows = [
      row('face_detect_rate', this._frames ? this._faces / this._frames : 0),
      row('iris_valid_rate', this._frames ? this._irisOk / this._frames : 0),
    ];
    this._resetWindow(endTs);
    return rows;
  }

  /** The trailing partial window, so a short session still reports quality. */
  flush(finalTs) {
    const quality = finalTs && this._windowStart !== null && this._frames > 0
      ? this._quality(finalTs.native_ts) : [];
    return { source: this.source, signals: [], events: [], quality };
  }
}

/**
 * face.mediapipe_blendshapes — browser-live placement.
 *
 * M0 reference engine. Both other engines get copied from this, so the point
 * is less "blendshapes are useful" and more "this is the shape every engine
 * has to have."
 *
 * It exists in BOTH placements deliberately. The same engine_id runs here in
 * WASM for live participant feedback, and server-side in Python over the
 * uploaded video for the authoritative pass. They emit different `source`
 * values so their outputs sit side by side and can be compared, rather than
 * one silently overwriting the other. That duality is the M0 success criterion.
 *
 * Contract: packages/engine-contract/src/manifest.ts
 */

import {
  FaceLandmarker,
  FilesetResolver,
} from 'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18';

import manifest from '../engine.manifest.json' with { type: 'json' };
import { eulerFromMatrix, meanLuma } from './pose.js';

/** Blendshape names MediaPipe emits that we drop — neutral is a residual, not a signal. */
const IGNORED_BLENDSHAPES = new Set(['_neutral']);

/**
 * Rolling window for quality metrics. Long enough to be stable, short enough
 * that a participant walking out of frame shows up promptly.
 */
const QUALITY_WINDOW_MS = 5000;

export class MediaPipeBlendshapesLive {
  constructor() {
    this.manifest = { ...manifest, placement: 'browser-live', runtime: 'wasm' };
    this.source = `${manifest.engine_id}@${manifest.version}`;

    this._landmarker = null;
    this._params = null;
    this._outputCb = null;
    // Other engines that read the same landmarker result (gaze features), so
    // a second engine costs no second inference per frame.
    this._resultCbs = [];

    // Quality accounting. REPORT.md §2.1 measured webcam gaze at 9-39 fps,
    // jittered several-fold across participants — the rate is device- and
    // load-dependent and must be MEASURED per session, never assumed. §5.3
    // makes it a pre-registered exclusion variable, so it is a first-class
    // output here rather than a console.log.
    this._windowStart = null;
    this._framesSeen = 0;
    this._framesWithFace = 0;
    this._luminanceSum = 0;
    this._luminanceCount = 0;

    // Face-loss event tracking.
    this._faceLostAt = null;

    // Reused scratch canvas for luminance sampling.
    this._lumaCanvas = null;
    this._lumaCtx = null;
  }

  async init(cfg = {}) {
    const params = {
      min_face_detection_confidence: 0.5,
      min_face_presence_confidence: 0.5,
      min_tracking_confidence: 0.5,
      output_facial_transformation_matrixes: true,
      ...cfg,
    };
    this._params = params;

    const fileset = await FilesetResolver.forVisionTasks(
      'https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.18/wasm',
    );

    this._landmarker = await FaceLandmarker.createFromOptions(fileset, {
      baseOptions: {
        modelAssetPath:
          'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task',
        delegate: 'GPU',
      },
      runningMode: 'VIDEO',
      numFaces: 1,
      outputFaceBlendshapes: true,
      outputFacialTransformationMatrixes: params.output_facial_transformation_matrixes,
      minFaceDetectionConfidence: params.min_face_detection_confidence,
      minFacePresenceConfidence: params.min_face_presence_confidence,
      minTrackingConfidence: params.min_tracking_confidence,
    });
  }

  onOutput(cb) {
    this._outputCb = cb;
  }

  /** Receive each frame's raw landmarker result, with its timestamp and frame size. */
  onResult(cb) {
    this._resultCbs.push(cb);
  }

  /**
   * Feed one frame.
   *
   * @param {HTMLVideoElement|VideoFrame} frame
   * @param {{native_clock_id: string, native_ts: number}} ts
   *   Stamped by the caller with performance.now(). This engine never reads a
   *   clock itself and never converts between clocks — REPORT.md §3.3, that is
   *   the alignment service's job, and doing it per-engine ships the same bug
   *   once per engine.
   */
  pushFrame(frame, ts) {
    if (!this._landmarker) throw new Error('init() must be awaited before pushFrame()');

    if (this._windowStart === null) this._windowStart = ts.native_ts;
    this._framesSeen += 1;

    const result = this._landmarker.detectForVideo(frame, ts.native_ts);
    if (this._resultCbs.length) {
      const size = {
        width: frame.videoWidth ?? frame.displayWidth ?? frame.width,
        height: frame.videoHeight ?? frame.displayHeight ?? frame.height,
      };
      for (const cb of this._resultCbs) cb(result, ts, size);
    }

    const signals = [];
    const events = [];

    const hasFace =
      result.faceBlendshapes?.length > 0 && result.faceBlendshapes[0].categories?.length > 0;

    if (hasFace) {
      this._framesWithFace += 1;

      // Face recovered — close any open loss event.
      if (this._faceLostAt !== null) {
        events.push({
          event_type: 'face_lost',
          native_clock_id: ts.native_clock_id,
          onset_native_ts: this._faceLostAt,
          offset_native_ts: ts.native_ts,
        });
        this._faceLostAt = null;
      }

      for (const cat of result.faceBlendshapes[0].categories) {
        if (IGNORED_BLENDSHAPES.has(cat.categoryName)) continue;
        signals.push({
          stream: 'face',
          // Namespaced `blendshape.` deliberately. These are ARKit-style rig
          // coefficients, NOT FACS action units. Several map near-1:1
          // (browDown~AU4, cheekSquint~AU6, mouthSmile~AU12) but that mapping
          // is unvalidated, so relabelling them as AUs would launder an
          // assumption into the data. Py-Feat supplies real AUs at M2.
          channel: `blendshape.${cat.categoryName}`,
          native_clock_id: ts.native_clock_id,
          native_ts: ts.native_ts,
          value: cat.score,
          reliability_tier: 'moderate',
        });
      }

      const matrix = result.facialTransformationMatrixes?.[0]?.data;
      if (matrix) {
        const pose = eulerFromMatrix(matrix);
        for (const [axis, value] of Object.entries(pose)) {
          signals.push({
            stream: 'face',
            channel: `head_pose.${axis}`,
            native_clock_id: ts.native_clock_id,
            native_ts: ts.native_ts,
            value,
            reliability_tier: 'high',
          });
        }
      }
    } else if (this._faceLostAt === null) {
      this._faceLostAt = ts.native_ts;
    }

    // Luminance is sampled whether or not a face was found — a dark room is
    // exactly the case where detection fails, so gating on face presence would
    // hide the cause. §2.5: the rPPG skin-tone gap largely closes at >=30, the
    // one quantified bias mitigation in the whole evidence base.
    const luma = this._sampleLuminance(frame);
    if (luma !== null) {
      this._luminanceSum += luma;
      this._luminanceCount += 1;
    }

    const quality = this._maybeEmitQuality(ts);

    if (this._outputCb && (signals.length || events.length || quality.length)) {
      this._outputCb({ signals, events, quality });
    }
  }

  /** Mean luminance over a downsampled grid. Cheap, and only needs to be indicative. */
  _sampleLuminance(frame) {
    const w = frame.videoWidth ?? frame.displayWidth ?? frame.width;
    const h = frame.videoHeight ?? frame.displayHeight ?? frame.height;
    if (!w || !h) return null;

    if (!this._lumaCanvas) {
      this._lumaCanvas = new OffscreenCanvas(32, 32);
      this._lumaCtx = this._lumaCanvas.getContext('2d', { willReadFrequently: true });
    }
    try {
      this._lumaCtx.drawImage(frame, 0, 0, 32, 32);
      const { data } = this._lumaCtx.getImageData(0, 0, 32, 32);
      return meanLuma(data);
    } catch {
      return null;
    }
  }

  _maybeEmitQuality(ts) {
    if (this._windowStart === null) return [];
    const elapsed = ts.native_ts - this._windowStart;
    if (elapsed < QUALITY_WINDOW_MS) return [];

    const rows = [
      {
        stream: 'face',
        metric: 'achieved_fps',
        window_start_native_ts: this._windowStart,
        window_end_native_ts: ts.native_ts,
        value: (this._framesSeen / elapsed) * 1000,
      },
      {
        stream: 'face',
        metric: 'face_detect_rate',
        window_start_native_ts: this._windowStart,
        window_end_native_ts: ts.native_ts,
        value: this._framesSeen ? this._framesWithFace / this._framesSeen : 0,
      },
    ];

    if (this._luminanceCount > 0) {
      rows.push({
        stream: 'face',
        metric: 'mean_luminance',
        window_start_native_ts: this._windowStart,
        window_end_native_ts: ts.native_ts,
        value: this._luminanceSum / this._luminanceCount,
      });
    }

    this._windowStart = ts.native_ts;
    this._framesSeen = 0;
    this._framesWithFace = 0;
    this._luminanceSum = 0;
    this._luminanceCount = 0;

    return rows;
  }

  /** Close open events and flush a final partial quality window. */
  async flush(finalTs) {
    const events = [];
    if (this._faceLostAt !== null && finalTs) {
      events.push({
        event_type: 'face_lost',
        native_clock_id: finalTs.native_clock_id,
        onset_native_ts: this._faceLostAt,
        offset_native_ts: finalTs.native_ts,
      });
      this._faceLostAt = null;
    }

    // Emit the trailing window even if short — a 40-second session should not
    // silently produce zero quality rows just because it never filled a window.
    let quality = [];
    if (finalTs && this._windowStart !== null && this._framesSeen > 0) {
      const elapsed = Math.max(finalTs.native_ts - this._windowStart, 1);
      quality = [
        {
          stream: 'face',
          metric: 'achieved_fps',
          window_start_native_ts: this._windowStart,
          window_end_native_ts: finalTs.native_ts,
          value: (this._framesSeen / elapsed) * 1000,
        },
        {
          stream: 'face',
          metric: 'face_detect_rate',
          window_start_native_ts: this._windowStart,
          window_end_native_ts: finalTs.native_ts,
          value: this._framesWithFace / this._framesSeen,
        },
      ];
      if (this._luminanceCount > 0) {
        quality.push({
          stream: 'face',
          metric: 'mean_luminance',
          window_start_native_ts: this._windowStart,
          window_end_native_ts: finalTs.native_ts,
          value: this._luminanceSum / this._luminanceCount,
        });
      }
    }

    return { signals: [], events, quality };
  }

  close() {
    this._landmarker?.close();
    this._landmarker = null;
  }
}


/**
 * Engine contract — single source of truth.
 *
 * An engine is a pure, versioned function:
 *     (media, params) -> signals + events + quality
 *
 * Engines are deterministic and containerized. An engine knows nothing about
 * the database, the study runner, or clock alignment. It emits samples stamped
 * with its OWN native clock; a separate, non-pluggable alignment service fills
 * `master_ts`. See REPORT.md §3.3 — AudioContext.currentTime is a different
 * clock from performance.now(), and letting each engine solve that itself means
 * shipping the same bug four times.
 *
 * Keep this file in sync with python/engine_contract/manifest.py.
 */

export type Modality =
  | 'gaze'
  | 'face'
  | 'voice'
  | 'respiration'
  | 'cardiac';

export type Runtime =
  | 'python-gpu'
  | 'python-cpu'
  | 'wasm'
  | 'webgpu';

/**
 * Where an engine runs. The same engine_id may ship in both placements
 * (see engines/face.mediapipe_blendshapes) — each placement emits a distinct
 * `source` so their outputs can be compared rather than silently merged.
 */
export type Placement =
  | 'server-batch'
  | 'server-stream'
  | 'browser-live';

/**
 * Per-channel trustworthiness, from the validation evidence — NOT a UI
 * convention. REPORT.md §2.2: AU12 lands at F1 .72-.83 while AU20 sits at
 * .13-.24. Carrying this in the schema makes it structurally impossible for a
 * rendering layer to present them as equals.
 */
export type ReliabilityTier =
  | 'high'        // validated, use freely
  | 'moderate'    // usable, report with uncertainty
  | 'low'         // exploratory only, do not headline
  | 'unvalidated'; // no accuracy evidence exists (e.g. respiration pre-study)

export type CommercialUse = 'yes' | 'no' | 'unknown';

/**
 * Licensing is load-bearing for this project, not metadata.
 *
 * This build targets ACADEMIC / NON-PROFIT use, which unlocks OpenFace 3.0,
 * LibreFace and openSMILE directly. Several of those are explicitly
 * non-commercial. Declaring it per-engine means `tools/license-inventory`
 * can answer "what would we have to rip out if this went commercial?" at any
 * time, instead of that becoming an archaeology project later.
 */
export interface EngineLicense {
  /** SPDX identifier where one applies, else 'custom'. */
  spdx: string;
  commercial_use: CommercialUse;
  url: string;
  /** Free-text caveats, e.g. a single non-commercial weight inside an MIT repo. */
  notes?: string;
}

/**
 * Where the weights came from. Training-set provenance is the usual reason a
 * permissively-licensed repo still can't ship commercially.
 */
export interface EngineProvenance {
  weights_sha256?: string;
  training_datasets: string[];
  paper_doi?: string;
}

export type MediaKind = 'video' | 'audio';

/**
 * Input requirements, enforced by probe() rather than documented in a README.
 *
 * These encode hard findings: rPPG on heavily compressed video performs worse
 * than always guessing 75 bpm (§2.4); voice valence is lexically driven and
 * dies under noise suppression (§2.3); gaze below ~5 Hz effective sampling is
 * excluded by published practice (§5.3).
 */
export interface InputSpec {
  kind: MediaKind;
  min_fps?: number;
  min_resolution?: { width: number; height: number };
  min_bitrate_kbps?: number;
  colorspace?: string;
  /** Minimum mean ROI luminance. §2.5: the rPPG skin-tone gap largely closes at >=30. */
  min_roi_luminance?: number;
  /**
   * getUserMedia constraints that must have been APPLIED at capture time.
   * We record what was actually applied per session, not what was requested —
   * the spec permits a UA to ignore the request without failing (§5.2).
   */
  required_audio_constraints?: Partial<{
    echoCancellation: boolean;
    noiseSuppression: boolean;
    autoGainControl: boolean;
  }>;
}

export interface SignalSpec {
  channel: string;
  unit: string;
  /** Nominal rate. Real rate varies per session and is logged as a quality metric. */
  nominal_rate_hz: number;
  value_type: 'float' | 'int' | 'bool' | 'categorical';
  range?: [number, number];
  categories?: string[];
  reliability_tier: ReliabilityTier;
  description?: string;
}

export interface EventSpec {
  event_type: string;
  description?: string;
  /** Whether this event carries a duration or is instantaneous. */
  has_offset?: boolean;
}

export interface QualitySpec {
  metric: string;
  unit: string;
  description?: string;
  /**
   * Threshold below/above which a session or window is flagged. Published
   * starting points in §5.3: 5 Hz minimum sampling, 0.5 face-detection confidence.
   */
  warn_below?: number;
  warn_above?: number;
}

export interface EngineManifest {
  /** Stable, namespaced by modality, e.g. 'resp.chestmotion'. */
  engine_id: string;
  /** Semver. Appears in every output row via `source = engine_id@version`. */
  version: string;
  modality: Modality;
  runtime: Runtime;
  placement: Placement;

  inputs: InputSpec[];
  /** JSONSchema for engine params (band_hz, grid size, fusion_mode, ...). */
  params_schema: Record<string, unknown>;

  outputs: {
    signals: SignalSpec[];
    events: EventSpec[];
    quality: QualitySpec[];
  };

  license: EngineLicense;
  provenance: EngineProvenance;
  determinism: 'deterministic' | 'nondeterministic';
}

/** Result of probe(). Ineligibility is RECORDED, never a silent skip. */
export interface Eligibility {
  eligible: boolean;
  /** Machine-readable reasons, e.g. ['bitrate_below_min', 'noise_suppression_applied']. */
  reasons: string[];
  /** Human-readable explanation for the quality row and the researcher. */
  detail?: string;
}

/** Describes media handed to an engine, before it decides whether it can run. */
export interface MediaDescriptor {
  path: string;
  kind: MediaKind;
  sha256: string;
  duration_s: number;
  fps?: number;
  width?: number;
  height?: number;
  bitrate_kbps?: number;
  codec?: string;
  applied_audio_constraints?: Record<string, boolean>;
  mean_roi_luminance?: number;
}

/** A clock stamp. Engines never convert between clocks — that's the aligner's job. */
export interface ClockStamp {
  native_clock_id: string;
  native_ts: number;
}

export interface SignalRow {
  stream: string;
  channel: string;
  native_clock_id: string;
  native_ts: number;
  value: number | string | boolean;
  reliability_tier: ReliabilityTier;
}

export interface EventRow {
  event_type: string;
  native_clock_id: string;
  onset_native_ts: number;
  offset_native_ts?: number;
  stimulus_id?: string;
  metadata?: Record<string, unknown>;
}

export interface QualityRow {
  stream: string;
  metric: string;
  window_start_native_ts: number;
  window_end_native_ts: number;
  value: number;
}

export interface Chunk {
  signals: SignalRow[];
  events: EventRow[];
  quality: QualityRow[];
}

/**
 * Streaming engine interface for browser-live placement.
 * Same contract shape as the batch interface, different delivery.
 */
export interface LiveEngine {
  readonly manifest: EngineManifest;
  init(cfg: Record<string, unknown>): Promise<void>;
  pushFrame(frame: VideoFrame, ts: ClockStamp): void;
  pushAudio(chunk: AudioData, ts: ClockStamp): void;
  onOutput(cb: (c: Chunk) => void): void;
  flush(): Promise<Chunk>;
}

/** `source` column value. Two engines on one modality coexist as separate rows. */
export function sourceId(m: Pick<EngineManifest, 'engine_id' | 'version'>): string {
  return `${m.engine_id}@${m.version}`;
}

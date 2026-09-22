-- Canonical tables for multimodal behavioral data.
--
-- REPORT.md §3.4 established that NO formal export standard exists for this
-- data class — confirmed by two research passes, not merely unfound. BIDS and
-- LSL's XDF are the nearest analogues to borrow structure from, not adopt.
-- This schema is that borrowed structure, generalized to be modality-agnostic.
--
-- Physical storage is Parquet partitioned by session_id / stream; this DDL is
-- the reference definition and the DuckDB/Postgres view over those files.
--
-- Three rules drive the design:
--
--   1. Every row carries `source = engine_id@version` plus `params_hash`.
--      Two engines on one modality coexist. Re-running an engine is an APPEND,
--      never a migration. §2.2 found engine choice swung valid-frame yield
--      43%->63% on identical video, so a pipeline that cannot re-run
--      permanently bakes in whichever engine was picked first.
--
--   2. `reliability_tier` is a schema field, not a UI convention. §2.2's per-AU
--      floor (AU12 at F1 .72-.83 vs AU20 at .13-.24) is enforced structurally.
--
--   3. Engines emit NATIVE timestamps only. A separate, non-pluggable alignment
--      service fills master_ts and master_ts_uncertainty_ms. §3.3: AudioContext
--      .currentTime is a different clock from performance.now(), and letting
--      each engine solve that itself ships the same bug once per engine.

-- ---------------------------------------------------------------------------
-- sessions — one row per participant session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,
    participant_id          TEXT NOT NULL,
    study_id                TEXT NOT NULL,
    started_utc             TIMESTAMP NOT NULL,
    ended_utc               TIMESTAMP,

    -- Capture environment, recorded because it gates which engines may run.
    user_agent              TEXT,
    screen_width_px         INTEGER,
    screen_height_px        INTEGER,
    device_pixel_ratio      REAL,

    -- Screen geometry recovered per participant. §5.1: viewing distance across
    -- 1,153 online participants was mean 47.3cm, SD 8.9 — degrees of visual
    -- angle are meaningless without a per-participant estimate.
    viewing_distance_mm     REAL,
    px_per_mm               REAL,
    geometry_method         TEXT,   -- 'virtual_chinrest' | 'declared' | 'unknown'
    geometry_error_mm       REAL,   -- §5.1: 2.4-5.5cm MAE is the documented range

    -- What getUserMedia ACTUALLY applied, not what we asked for. §5.2: the spec
    -- permits a UA to ignore a constraint without failing, and these determine
    -- which voice channels are even valid (§2.3).
    applied_audio_constraints JSON,

    consent_tier            TEXT,   -- 'features_only' | 'media_retained' | 'media_plus_transcript'
    notes                   TEXT
);

-- ---------------------------------------------------------------------------
-- runs — one row per (engine, version, params) applied to one session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    run_id                  TEXT PRIMARY KEY,
    session_id              TEXT NOT NULL REFERENCES sessions(session_id),
    engine_id               TEXT NOT NULL,
    version                 TEXT NOT NULL,
    source                  TEXT NOT NULL,   -- engine_id@version, denormalized for joins
    params                  JSON NOT NULL,
    params_hash             TEXT NOT NULL,
    media_sha256            TEXT,

    started_utc             TIMESTAMP NOT NULL,
    ended_utc               TIMESTAMP,
    status                  TEXT NOT NULL,   -- 'ok' | 'ineligible' | 'failed'

    -- probe() result. An ineligible run is RECORDED with its reasons, never a
    -- silent skip — that is how the report's traps become machine-enforced
    -- rather than tribal knowledge.
    eligible                BOOLEAN NOT NULL,
    ineligible_reasons      JSON,
    eligibility_detail      TEXT,

    -- Carried from the manifest so a historical run's licensing is auditable
    -- even after the engine package is upgraded or removed.
    license_spdx            TEXT,
    license_commercial_use  TEXT             -- 'yes' | 'no' | 'unknown'
);

CREATE INDEX IF NOT EXISTS idx_runs_session ON runs(session_id);
CREATE INDEX IF NOT EXISTS idx_runs_source  ON runs(source);

-- ---------------------------------------------------------------------------
-- signals — the long-format sample table. The spine of everything.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS signals (
    session_id              TEXT NOT NULL,
    participant_id          TEXT NOT NULL,
    stream                  TEXT NOT NULL,   -- 'gaze' | 'face' | 'voice' | 'respiration' | ...
    channel                 TEXT NOT NULL,   -- 'gaze_x_px', 'AU12', 'resp_waveform', ...

    -- Aligner-owned. Nullable until alignment runs; uncertainty is NOT optional
    -- once it does, because §3.3 says AV sync is a ceiling, not a bug to fix.
    master_ts               DOUBLE,
    master_ts_uncertainty_ms REAL,

    -- Engine-owned. The authoritative record; alignment is a derived view of it.
    native_ts               DOUBLE NOT NULL,
    native_clock_id         TEXT NOT NULL,   -- 'performance.now' | 'audiocontext' | 'lsl' | ...

    value                   DOUBLE,
    value_text              TEXT,            -- for categorical channels

    source                  TEXT NOT NULL,   -- engine_id@version
    params_hash             TEXT NOT NULL,
    reliability_tier        TEXT NOT NULL    -- 'high'|'moderate'|'low'|'unvalidated'
);

CREATE INDEX IF NOT EXISTS idx_signals_session_stream ON signals(session_id, stream);
CREATE INDEX IF NOT EXISTS idx_signals_channel        ON signals(session_id, channel);
CREATE INDEX IF NOT EXISTS idx_signals_master_ts      ON signals(session_id, master_ts);

-- ---------------------------------------------------------------------------
-- events — stimulus onsets, markers, engine-detected discrete events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS events (
    session_id              TEXT NOT NULL,
    participant_id          TEXT NOT NULL,
    event_type              TEXT NOT NULL,   -- 'stimulus_onset', 'calibration_point',
                                             -- 'inhale_onset', 'sync_clapper', ...
    onset_master_ts         DOUBLE,
    offset_master_ts        DOUBLE,
    onset_native_ts         DOUBLE NOT NULL,
    offset_native_ts        DOUBLE,
    native_clock_id         TEXT NOT NULL,

    stimulus_id             TEXT,
    source                  TEXT NOT NULL,   -- 'runner@1.0.0' for stimulus events
    metadata                JSON
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type    ON events(session_id, event_type);

-- ---------------------------------------------------------------------------
-- quality — first-class, same family as signals. Not a log file.
-- ---------------------------------------------------------------------------
-- §5.3 supplies published starting thresholds: 5 Hz minimum effective sampling
-- (one study excluded 18/220 participants on exactly this), 0.5 face-detection
-- confidence. Because respiration has NO verified accuracy figure anywhere
-- (§2.4), a calibrated confidence channel is what makes it shippable at all.
CREATE TABLE IF NOT EXISTS quality (
    session_id              TEXT NOT NULL,
    participant_id          TEXT NOT NULL,
    stream                  TEXT NOT NULL,
    metric                  TEXT NOT NULL,   -- 'achieved_fps', 'face_detect_rate',
                                             -- 'mean_luminance', 'calibration_error_deg',
                                             -- 'periodicity_index', 'inter_engine_agreement'
    window_start_master_ts  DOUBLE,
    window_end_master_ts    DOUBLE,
    window_start_native_ts  DOUBLE NOT NULL,
    window_end_native_ts    DOUBLE NOT NULL,
    native_clock_id         TEXT NOT NULL,

    value                   DOUBLE NOT NULL,
    source                  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_session ON quality(session_id, stream, metric);

-- ---------------------------------------------------------------------------
-- Convenience views
-- ---------------------------------------------------------------------------

-- Per-session, per-stream effective sampling rate. §2.1 measured webcam gaze at
-- 9-39 fps, jittered — rate is device- and load-dependent and MUST be measured
-- per session rather than assumed, then pre-registered as an exclusion variable.
CREATE VIEW IF NOT EXISTS v_session_sampling_rate AS
SELECT
    session_id,
    stream,
    source,
    COUNT(*)                                          AS n_samples,
    MIN(native_ts)                                    AS t_start,
    MAX(native_ts)                                    AS t_end,
    COUNT(*) / NULLIF(MAX(native_ts) - MIN(native_ts), 0) AS effective_rate_hz
FROM signals
GROUP BY session_id, stream, source;

-- Which sessions have the same channel from more than one engine. §2.2 measured
-- r = 0.37-0.75 between facial engines on identical video — that spread IS a
-- free uncertainty estimate, so never run single-engine on facial.
CREATE VIEW IF NOT EXISTS v_multi_engine_channels AS
SELECT
    session_id,
    stream,
    channel,
    COUNT(DISTINCT source) AS n_sources,
    GROUP_CONCAT(DISTINCT source) AS sources
FROM signals
GROUP BY session_id, stream, channel
HAVING COUNT(DISTINCT source) > 1;

-- Engines whose licence forbids or does not confirm commercial use. This build
-- is academic/non-profit, so these are legitimately in use — the view exists so
-- the "what would we rip out if we went commercial" answer is never stale.
CREATE VIEW IF NOT EXISTS v_research_only_runs AS
SELECT DISTINCT
    source,
    engine_id,
    version,
    license_spdx,
    license_commercial_use,
    COUNT(*) OVER (PARTITION BY source) AS n_runs
FROM runs
WHERE license_commercial_use IN ('no', 'unknown');

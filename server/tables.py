"""Canonical table writer — Parquet, partitioned by session and stream.

Implements the schema in packages/engine-contract/schema/canonical_tables.sql.

REPORT.md §3.4 established that no formal export standard exists for multimodal
behavioural data — confirmed by two research passes, not merely unfound. BIDS
and LSL's XDF are the nearest analogues to borrow structure from. This is that
borrowed structure: a long-format signal table plus a separate event table,
both carrying ``source`` so two engines on one modality coexist and a re-run is
an append rather than a migration.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from alignment import ClockSolution
from engine_contract import Chunk, Eligibility, EngineManifest

# ---------------------------------------------------------------------------
# Arrow schemas. Explicit rather than inferred — inferred schemas drift the
# moment a column happens to be all-null in one session's data.
# ---------------------------------------------------------------------------

SIGNALS_SCHEMA = pa.schema([
    pa.field("session_id", pa.string(), nullable=False),
    pa.field("participant_id", pa.string(), nullable=False),
    pa.field("stream", pa.string(), nullable=False),
    pa.field("channel", pa.string(), nullable=False),
    # Nullable by design: an unaligned stream must be visibly unaligned.
    pa.field("master_ts", pa.float64(), nullable=True),
    pa.field("master_ts_uncertainty_ms", pa.float32(), nullable=True),
    pa.field("native_ts", pa.float64(), nullable=False),
    pa.field("native_clock_id", pa.string(), nullable=False),
    pa.field("value", pa.float64(), nullable=True),
    pa.field("value_text", pa.string(), nullable=True),
    pa.field("source", pa.string(), nullable=False),
    pa.field("params_hash", pa.string(), nullable=False),
    pa.field("reliability_tier", pa.string(), nullable=False),
])

EVENTS_SCHEMA = pa.schema([
    pa.field("session_id", pa.string(), nullable=False),
    pa.field("participant_id", pa.string(), nullable=False),
    pa.field("event_type", pa.string(), nullable=False),
    pa.field("onset_master_ts", pa.float64(), nullable=True),
    pa.field("offset_master_ts", pa.float64(), nullable=True),
    pa.field("onset_native_ts", pa.float64(), nullable=False),
    pa.field("offset_native_ts", pa.float64(), nullable=True),
    pa.field("native_clock_id", pa.string(), nullable=False),
    pa.field("stimulus_id", pa.string(), nullable=True),
    pa.field("source", pa.string(), nullable=False),
    pa.field("metadata", pa.string(), nullable=True),  # JSON-encoded
])

QUALITY_SCHEMA = pa.schema([
    pa.field("session_id", pa.string(), nullable=False),
    pa.field("participant_id", pa.string(), nullable=False),
    pa.field("stream", pa.string(), nullable=False),
    pa.field("metric", pa.string(), nullable=False),
    pa.field("window_start_master_ts", pa.float64(), nullable=True),
    pa.field("window_end_master_ts", pa.float64(), nullable=True),
    pa.field("window_start_native_ts", pa.float64(), nullable=False),
    pa.field("window_end_native_ts", pa.float64(), nullable=False),
    pa.field("native_clock_id", pa.string(), nullable=False),
    pa.field("value", pa.float64(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
])

RUNS_SCHEMA = pa.schema([
    pa.field("run_id", pa.string(), nullable=False),
    pa.field("session_id", pa.string(), nullable=False),
    pa.field("engine_id", pa.string(), nullable=False),
    pa.field("version", pa.string(), nullable=False),
    pa.field("source", pa.string(), nullable=False),
    pa.field("params", pa.string(), nullable=False),      # JSON
    pa.field("params_hash", pa.string(), nullable=False),
    pa.field("media_sha256", pa.string(), nullable=True),
    pa.field("started_utc", pa.timestamp("ms", tz="UTC"), nullable=False),
    pa.field("ended_utc", pa.timestamp("ms", tz="UTC"), nullable=True),
    pa.field("status", pa.string(), nullable=False),
    pa.field("eligible", pa.bool_(), nullable=False),
    pa.field("ineligible_reasons", pa.string(), nullable=True),  # JSON array
    pa.field("eligibility_detail", pa.string(), nullable=True),
    # Carried from the manifest so a historical run's licensing stays auditable
    # even after the engine package is upgraded or removed.
    pa.field("license_spdx", pa.string(), nullable=True),
    pa.field("license_commercial_use", pa.string(), nullable=True),
    # Alignment provenance — how this run's timestamps were mapped, and how
    # well. Without this a NULL master_ts is unexplainable after the fact.
    pa.field("clock_id", pa.string(), nullable=True),
    pa.field("clock_offset_ms", pa.float64(), nullable=True),
    pa.field("clock_rate", pa.float64(), nullable=True),
    pa.field("clock_uncertainty_ms", pa.float64(), nullable=True),
    pa.field("clock_n_anchors", pa.int32(), nullable=True),
    pa.field("unaligned_reason", pa.string(), nullable=True),
])


SESSIONS_SCHEMA = pa.schema([
    pa.field("session_id", pa.string(), nullable=False),
    pa.field("participant_id", pa.string(), nullable=False),
    pa.field("study_id", pa.string(), nullable=False),
    pa.field("started_utc", pa.timestamp("ms", tz="UTC"), nullable=True),
    pa.field("user_agent", pa.string(), nullable=True),
    pa.field("screen_width_px", pa.int32(), nullable=True),
    pa.field("screen_height_px", pa.int32(), nullable=True),
    pa.field("device_pixel_ratio", pa.float32(), nullable=True),
    # Screen geometry from the virtual chinrest. All four nullable together:
    # §5.1 puts viewing distance at mean 47.3cm with SD 8.9 across 1,153 online
    # participants, so a degrees-of-visual-angle figure computed from a nominal
    # distance is a pixel count wearing a unit. A session that could not recover
    # geometry must be visibly unable to, not quietly assigned the mean.
    pa.field("viewing_distance_mm", pa.float64(), nullable=True),
    pa.field("px_per_mm", pa.float64(), nullable=True),
    pa.field("geometry_method", pa.string(), nullable=True),
    pa.field("geometry_error_mm", pa.float64(), nullable=True),
    # Kept distinct from geometry_error_mm on purpose. This is how much the
    # participant's own repetitions agreed (precision); the error column is
    # bounded below by the published 5.5cm accuracy floor of the method itself,
    # which no amount of participant care can improve on.
    pa.field("geometry_precision_mm", pa.float64(), nullable=True),
    pa.field("geometry_refusal_reason", pa.string(), nullable=True),
    pa.field("applied_audio_constraints", pa.string(), nullable=True),  # JSON
    # What the participant agreed to keep. Nullable, and a NULL means "no
    # decision was recorded" — which is a different thing from the most
    # restrictive tier, and must not be silently treated as one.
    pa.field("consent_tier", pa.string(), nullable=True),
    pa.field("consent_retention_days", pa.int32(), nullable=True),
    # Which protocol this session ran under. The content hash rather than the
    # definition, so a study edited in place is detectable even when nobody
    # bumped the version — see server/study.py. Nullable for the pilots
    # captured before study definitions existed; NULL means "no protocol was
    # recorded", which is not the same as "the default protocol".
    pa.field("study_version", pa.string(), nullable=True),
    pa.field("study_content_hash", pa.string(), nullable=True),
    pa.field("study_modalities", pa.string(), nullable=True),  # JSON list
    # 'developer' (a self-test) or 'participants' (run under an ethics
    # reference), from the study at capture time. NULL for sessions captured
    # before the field existed — "not recorded", which cohort analysis treats
    # like a self-test rather than guessing either way.
    pa.field("audience", pa.string(), nullable=True),
    # The between-subject arm this participant was assigned, NULL for a study
    # without conditions. How it was drawn (seed, method) is in the
    # `condition_assigned` event, so analysis can check the split.
    pa.field("condition", pa.string(), nullable=True),
    pa.field("achieved_fps", pa.float64(), nullable=True),
    pa.field("clock_id", pa.string(), nullable=True),
    pa.field("clock_resolution_ms", pa.float64(), nullable=True),
    pa.field("cross_origin_isolated", pa.bool_(), nullable=True),
])


def params_hash(params: dict[str, Any]) -> str:
    """Stable hash of an engine's parameters.

    Part of every signal row so that re-running the same engine with *different*
    params appends a distinguishable set rather than silently mixing two
    parameterisations into one channel.
    """
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class SessionContext:
    """Everything a writer needs that an engine deliberately does not know."""

    session_id: str
    participant_id: str
    study_id: str = "default"


class CanonicalWriter:
    """Accumulates engine output and writes the canonical Parquet tables.

    Rows are buffered in memory and flushed on ``close()``. That is fine for
    session-scale data (a 10-minute session is order 10^5-10^6 rows) and keeps
    the append-only semantics obvious. A streaming writer can replace this
    later without changing the on-disk layout.
    """

    def __init__(self, root: str | Path, ctx: SessionContext) -> None:
        self.root = Path(root)
        self.ctx = ctx
        self._signals: list[dict[str, Any]] = []
        self._events: list[dict[str, Any]] = []
        self._quality: list[dict[str, Any]] = []
        self._runs: list[dict[str, Any]] = []
        self._session: dict[str, Any] | None = None

    # -- ingestion ---------------------------------------------------------

    def set_session_metadata(self, manifest: dict[str, Any]) -> dict[str, Any]:
        """Record the capture-side session row from the browser's manifest.

        Geometry is unpacked rather than stored as opaque JSON because it gates
        analysis: without ``px_per_mm`` and ``viewing_distance_mm`` no spatial
        error can be expressed in degrees, and an analyst needs to be able to
        select on that with a predicate rather than by parsing a blob.

        A refused chinrest is written as a row with NULL geometry and a populated
        ``geometry_refusal_reason``. That distinction matters: a NULL with a
        reason is a participant who tried and the method declined to guess, which
        is a different exclusion decision from a session where the task never ran.
        """
        geometry = manifest.get("geometry") or {}
        screen = manifest.get("screen") or {}
        clock = manifest.get("clock") or {}
        audio = manifest.get("applied_audio_constraints")
        study = manifest.get("study") or {}

        started = manifest.get("created_utc")
        started_dt = None
        if started:
            try:
                started_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            except ValueError:
                started_dt = None

        self._session = {
            "session_id": self.ctx.session_id,
            "participant_id": self.ctx.participant_id,
            "study_id": self.ctx.study_id,
            "started_utc": started_dt,
            "user_agent": manifest.get("user_agent"),
            "screen_width_px": _opt_int(screen.get("width_px")),
            "screen_height_px": _opt_int(screen.get("height_px")),
            "device_pixel_ratio": screen.get("device_pixel_ratio"),
            "viewing_distance_mm": geometry.get("viewing_distance_mm"),
            "px_per_mm": geometry.get("px_per_mm"),
            "geometry_method": geometry.get("geometry_method", "unknown"),
            "geometry_error_mm": geometry.get("geometry_error_mm"),
            "geometry_precision_mm": geometry.get("precision_mm"),
            "geometry_refusal_reason": geometry.get("reason"),
            "applied_audio_constraints": json.dumps(audio) if audio else None,
            "consent_tier": (manifest.get("consent") or {}).get("tier"),
            "consent_retention_days": _opt_int(
                (manifest.get("consent") or {}).get("retentionDays")),
            "study_version": study.get("study_version"),
            "study_content_hash": study.get("study_content_hash"),
            "study_modalities": (json.dumps(study["modalities"])
                                 if study.get("modalities") else None),
            "audience": study.get("audience"),
            "condition": manifest.get("condition"),
            "achieved_fps": manifest.get("achieved_fps"),
            "clock_id": clock.get("master_clock_id"),
            "clock_resolution_ms": clock.get("measured_resolution_ms"),
            "cross_origin_isolated": clock.get("cross_origin_isolated"),
        }
        return self._session

    def degrees_per_px(self) -> float | None:
        """Angular size of one CSS pixel, or None if geometry was not recovered.

        The single place the dva conversion factor is computed server-side, so
        that a refusal propagates as None instead of each analysis inventing its
        own fallback distance. Small-angle approximation is deliberate and safe
        here: at the §5.1 population mean it is accurate to far better than the
        method's own 7.4% uncertainty.
        """
        s = self._session
        if not s or not s.get("px_per_mm") or not s.get("viewing_distance_mm"):
            return None
        mm_per_px = 1.0 / s["px_per_mm"]
        return math.degrees(math.atan2(mm_per_px, s["viewing_distance_mm"]))

    def add_chunks(
        self,
        chunks: Iterable[Chunk],
        *,
        source: str,
        params: dict[str, Any],
        solution: ClockSolution,
    ) -> int:
        """Ingest engine output, converting native timestamps to master.

        ``solution`` decides whether ``master_ts`` is populated at all. An
        unaligned clock yields NULL master timestamps plus a recorded reason —
        never a zero-offset guess dressed up as an alignment.
        """
        ph = params_hash(params)
        n_rows = 0

        for chunk in chunks:
            for s in chunk.signals:
                master_ts, unc = solution.to_master(s.native_ts)
                numeric = isinstance(s.value, (int, float)) and not isinstance(s.value, bool)
                self._signals.append({
                    "session_id": self.ctx.session_id,
                    "participant_id": self.ctx.participant_id,
                    "stream": s.stream,
                    "channel": s.channel,
                    "master_ts": master_ts,
                    "master_ts_uncertainty_ms": unc,
                    "native_ts": s.native_ts,
                    "native_clock_id": s.native_clock_id,
                    "value": float(s.value) if numeric else None,
                    "value_text": None if numeric else str(s.value),
                    "source": source,
                    "params_hash": ph,
                    "reliability_tier": s.reliability_tier,
                })
                n_rows += 1

            for e in chunk.events:
                onset_master, _ = solution.to_master(e.onset_native_ts)
                offset_master = (
                    solution.to_master(e.offset_native_ts)[0]
                    if e.offset_native_ts is not None else None
                )
                self._events.append({
                    "session_id": self.ctx.session_id,
                    "participant_id": self.ctx.participant_id,
                    "event_type": e.event_type,
                    "onset_master_ts": onset_master,
                    "offset_master_ts": offset_master,
                    "onset_native_ts": e.onset_native_ts,
                    "offset_native_ts": e.offset_native_ts,
                    "native_clock_id": e.native_clock_id,
                    "stimulus_id": e.stimulus_id,
                    "source": source,
                    "metadata": json.dumps(e.metadata) if e.metadata else None,
                })
                n_rows += 1

            for q in chunk.quality:
                start_master, _ = solution.to_master(q.window_start_native_ts)
                end_master, _ = solution.to_master(q.window_end_native_ts)
                self._quality.append({
                    "session_id": self.ctx.session_id,
                    "participant_id": self.ctx.participant_id,
                    "stream": q.stream,
                    "metric": q.metric,
                    "window_start_master_ts": start_master,
                    "window_end_master_ts": end_master,
                    "window_start_native_ts": q.window_start_native_ts,
                    "window_end_native_ts": q.window_end_native_ts,
                    "native_clock_id": solution.clock_id,
                    "value": q.value,
                    "source": source,
                })
                n_rows += 1

        return n_rows

    def add_run(
        self,
        *,
        run_id: str,
        manifest: EngineManifest,
        source: str,
        params: dict[str, Any],
        eligibility: Eligibility,
        solution: ClockSolution,
        media_sha256: str | None,
        started: datetime,
        ended: datetime | None = None,
        status: str = "ok",
    ) -> None:
        self._runs.append({
            "run_id": run_id,
            "session_id": self.ctx.session_id,
            "engine_id": manifest.engine_id,
            "version": manifest.version,
            "source": source,
            "params": json.dumps(params, sort_keys=True),
            "params_hash": params_hash(params),
            "media_sha256": media_sha256,
            "started_utc": started,
            "ended_utc": ended or datetime.now(timezone.utc),
            "status": status,
            "eligible": eligibility.eligible,
            "ineligible_reasons": (
                json.dumps(list(eligibility.reasons)) if eligibility.reasons else None
            ),
            "eligibility_detail": eligibility.detail,
            "license_spdx": manifest.license.spdx,
            "license_commercial_use": manifest.license.commercial_use,
            "clock_id": solution.clock_id,
            "clock_offset_ms": solution.offset_ms if solution.aligned else None,
            "clock_rate": solution.rate if solution.aligned else None,
            "clock_uncertainty_ms": (
                solution.uncertainty_ms if solution.aligned else None
            ),
            "clock_n_anchors": solution.n_anchors,
            "unaligned_reason": solution.unaligned_reason,
        })

    # -- output ------------------------------------------------------------

    def close(self) -> dict[str, Path]:
        """Write all tables. Returns a map of table name -> path."""
        session_dir = self.root / f"session_id={self.ctx.session_id}"
        session_dir.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}

        # Reprocessing replaces the session wholesale. Each file below is
        # overwritten, but a stream partition from an earlier run that this run
        # does not produce (say, respiration from a run with --resp, then a run
        # without) would otherwise survive beside the new tables — rows from a
        # different run, read back as part of this one. Only this writer's own
        # outputs are removed; AOI sets and annotations live elsewhere.
        for stale in session_dir.glob("stream=*/*.parquet"):
            stale.unlink()
        for stale in session_dir.glob("*.parquet"):
            stale.unlink()

        # signals and quality partition by stream; a gaze analysis should not
        # have to read facial rows to find its own.
        for name, rows, schema in (
            ("signals", self._signals, SIGNALS_SCHEMA),
            ("quality", self._quality, QUALITY_SCHEMA),
        ):
            for stream in sorted({r["stream"] for r in rows}) or []:
                subset = [r for r in rows if r["stream"] == stream]
                out_dir = session_dir / f"stream={stream}"
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{name}.parquet"
                pq.write_table(_to_table(subset, schema), path, compression="zstd")
                written[f"{name}/{stream}"] = path
            if not rows:
                # Write an empty, correctly-typed file so downstream readers get
                # a schema rather than a missing-file error.
                path = session_dir / f"{name}.parquet"
                pq.write_table(_to_table([], schema), path, compression="zstd")
                written[name] = path

        for name, rows, schema in (
            ("events", self._events, EVENTS_SCHEMA),
            ("runs", self._runs, RUNS_SCHEMA),
            # Always written, even with no capture manifest, so that reading
            # `sessions` never raises for a session that merely lacked one.
            ("sessions", [self._session] if self._session else [], SESSIONS_SCHEMA),
        ):
            path = session_dir / f"{name}.parquet"
            pq.write_table(_to_table(rows, schema), path, compression="zstd")
            written[name] = path

        return written

    # -- introspection, for tests and the verification notebook ------------

    @property
    def signal_count(self) -> int:
        return len(self._signals)

    def signal_rows(self, channels: set[str] | frozenset[str],
                    source: str | None = None) -> list[dict[str, Any]]:
        """Rows already added this run, for a stage that derives from an engine's
        output (server/blinks.py) — read here, not re-read from disk, because the
        tables are only written when the writer closes."""
        return [r for r in self._signals
                if r["channel"] in channels and (source is None or r["source"] == source)]

    def sources(self) -> set[str]:
        return {r["source"] for r in self._signals}


def _opt_int(value: Any) -> int | None:
    """Coerce to int, tolerating the None and float forms JSON round-trips give."""
    return None if value is None else int(value)


def _to_table(rows: list[dict[str, Any]], schema: pa.Schema) -> pa.Table:
    """Build an Arrow table with an explicit schema, tolerating zero rows."""
    if not rows:
        return pa.Table.from_pydict(
            {f.name: [] for f in schema}, schema=schema
        )
    columns = {f.name: [r.get(f.name) for r in rows] for f in schema}
    return pa.Table.from_pydict(columns, schema=schema)


def read_session(root: str | Path, session_id: str, table: str = "signals") -> pa.Table:
    """Read one table back for a session, concatenating stream partitions."""
    session_dir = Path(root) / f"session_id={session_id}"
    if not session_dir.exists():
        raise FileNotFoundError(f"no such session: {session_dir}")

    paths = sorted(session_dir.glob(f"stream=*/{table}.parquet"))
    if not paths:
        flat = session_dir / f"{table}.parquet"
        if flat.exists():
            paths = [flat]
    if not paths:
        raise FileNotFoundError(f"no {table} table under {session_dir}")

    return pa.concat_tables([pq.read_table(p) for p in paths])

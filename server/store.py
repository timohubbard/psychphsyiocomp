"""Read side of the canonical tables — what the researcher UI asks questions of.

Separate from `tables.py`, which only writes. The split is not ceremony: the
writer is append-only and session-scoped, while every question a researcher asks
is cross-session and read-only, and letting one module do both invites a summary
view to start mutating the thing it summarises.

Everything here returns plain dicts and lists so the API layer is a thin
serialiser rather than a second place where meaning gets decided.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

#: Metrics that describe the session as a whole rather than a rolling window.
SESSION_SCOPED_METRICS = frozenset({
    "gaze_average_offset_px", "gaze_average_offset_deg", "gaze_percent_in_roi",
    "gaze_samples_per_sec", "gaze_validation_targets", "gaze_fit_refused",
    "gaze_calibration_targets",
})


def session_dirs(root: str | Path) -> list[Path]:
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith("session_id="))


def _read(path: Path):
    return pq.read_table(path) if path.exists() else None


def _read_partitioned(session_dir: Path, name: str):
    """Read a table that may be split across stream partitions."""
    parts = sorted(session_dir.glob(f"stream=*/{name}.parquet"))
    flat = session_dir / f"{name}.parquet"
    if not parts and flat.exists():
        return _read(flat)
    if not parts:
        return None
    import pyarrow as pa
    return pa.concat_tables([pq.read_table(p) for p in parts])


def list_sessions(root: str | Path) -> list[dict[str, Any]]:
    """One summary row per processed session, newest first."""
    out: list[dict[str, Any]] = []

    for d in session_dirs(root):
        session_id = d.name.split("=", 1)[1]
        sessions = _read(d / "sessions.parquet")
        meta: dict[str, Any] = {}
        if sessions is not None and sessions.num_rows:
            meta = sessions.to_pylist()[0]

        signals = _read_partitioned(d, "signals")
        quality = _read_partitioned(d, "quality")
        runs = _read(d / "runs.parquet")

        sources = (sorted(pc.unique(signals.column("source")).to_pylist())
                   if signals is not None and signals.num_rows else [])

        row = {
            "session_id": session_id,
            "participant_id": meta.get("participant_id"),
            "study_id": meta.get("study_id"),
            "started_utc": _iso(meta.get("started_utc")),
            "signal_rows": signals.num_rows if signals is not None else 0,
            "sources": sources,
            "n_sources": len(sources),
            "viewing_distance_mm": meta.get("viewing_distance_mm"),
            "geometry_error_mm": meta.get("geometry_error_mm"),
            "geometry_method": meta.get("geometry_method"),
            "geometry_refusal_reason": meta.get("geometry_refusal_reason"),
            "achieved_fps": meta.get("achieved_fps"),
            "duration_s": _duration_s(signals),
            "runs": _run_summary(runs),
        }
        row.update(_session_metrics(quality))
        # Surfaced as a first-class field because it is the question a
        # researcher opens this list to answer.
        row["aligned"] = _aligned_fraction(signals)
        out.append(row)

    out.sort(key=lambda r: (r["started_utc"] or "", r["session_id"]), reverse=True)
    return out


def session_detail(root: str | Path, session_id: str) -> dict[str, Any]:
    d = Path(root) / f"session_id={session_id}"
    if not d.exists():
        raise FileNotFoundError(session_id)

    signals = _read_partitioned(d, "signals")
    quality = _read_partitioned(d, "quality")
    events = _read(d / "events.parquet")
    runs = _read(d / "runs.parquet")
    sessions = _read(d / "sessions.parquet")

    meta = sessions.to_pylist()[0] if sessions is not None and sessions.num_rows else {}

    detail: dict[str, Any] = {
        "session_id": session_id,
        "meta": {k: _plain(v) for k, v in meta.items()},
        "channels": _channel_summary(signals),
        "quality": _quality_series(quality),
        "session_metrics": _session_metrics(quality),
        "events": _event_summary(events),
        "runs": _run_summary(runs),
        "duration_s": _duration_s(signals),
        "aligned": _aligned_fraction(signals),
    }
    return detail


def channel_series(
    root: str | Path, session_id: str, channel: str, source: str | None = None,
    max_points: int = 2000,
) -> dict[str, Any]:
    """One channel's time series, decimated for display.

    Decimation is by STRIDE, not by averaging. A browser plot of 700,000 points
    is useless either way, but averaging would smooth away exactly the brief
    events — blinks, saccades — that someone scanning a trace is looking for.
    """
    d = Path(root) / f"session_id={session_id}"
    signals = _read_partitioned(d, "signals")
    if signals is None:
        return {"channel": channel, "points": [], "n_total": 0}

    mask = pc.equal(signals.column("channel"), channel)
    if source:
        mask = pc.and_(mask, pc.equal(signals.column("source"), source))
    t = signals.filter(mask)

    ts = t.column("master_ts").to_pylist()
    vals = t.column("value").to_pylist()
    pairs = sorted((a, b) for a, b in zip(ts, vals) if a is not None and b is not None)

    stride = max(1, len(pairs) // max_points)
    return {
        "channel": channel,
        "source": source,
        "n_total": len(pairs),
        "stride": stride,
        "points": [[round(a, 1), b] for a, b in pairs[::stride]],
    }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _plain(v: Any) -> Any:
    """JSON-safe, without pretending a timestamp is a number."""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _iso(v: Any) -> str | None:
    return v.isoformat() if hasattr(v, "isoformat") else v


def _duration_s(signals) -> float | None:
    if signals is None or not signals.num_rows:
        return None
    col = signals.column("master_ts")
    lo, hi = pc.min(col).as_py(), pc.max(col).as_py()
    if lo is None or hi is None:
        return None
    return round((hi - lo) / 1000.0, 1)


def _aligned_fraction(signals) -> float | None:
    """Fraction of rows carrying a master timestamp.

    Anything below 1.0 means some stream could not be anchored, and the
    alignment service recorded a reason rather than guessing. That is a headline
    number, not a footnote — unaligned rows cannot be compared against anything.
    """
    if signals is None or not signals.num_rows:
        return None
    n = pc.sum(pc.invert(pc.is_null(signals.column("master_ts")))).as_py() or 0
    return round(n / signals.num_rows, 4)


def _channel_summary(signals) -> list[dict[str, Any]]:
    if signals is None or not signals.num_rows:
        return []
    import pyarrow as pa

    grouped = (
        pa.Table.from_arrays(
            [signals.column("channel"), signals.column("source"),
             signals.column("reliability_tier"), signals.column("value")],
            names=["channel", "source", "reliability_tier", "value"],
        )
        .group_by(["channel", "source", "reliability_tier"])
        .aggregate([("value", "count"), ("value", "mean"),
                    ("value", "min"), ("value", "max")])
    )
    rows = grouped.to_pylist()
    for r in rows:
        r["n"] = r.pop("value_count")
        for k in ("value_mean", "value_min", "value_max"):
            v = r.pop(k)
            r[k.replace("value_", "")] = round(v, 6) if isinstance(v, float) else v
    rows.sort(key=lambda r: (r["source"], r["channel"]))
    return rows


def _quality_series(quality) -> list[dict[str, Any]]:
    """Windowed quality metrics, excluding the session-scoped ones."""
    if quality is None or not quality.num_rows:
        return []
    rows = quality.to_pylist()
    return [
        {"metric": r["metric"], "source": r["source"], "stream": r["stream"],
         "t": r.get("window_start_master_ts"), "value": r["value"]}
        for r in rows if r["metric"] not in SESSION_SCOPED_METRICS
    ]


def _session_metrics(quality) -> dict[str, Any]:
    """The one-number-per-session metrics, flattened for a summary row."""
    if quality is None or not quality.num_rows:
        return {}
    out: dict[str, Any] = {}
    for r in quality.to_pylist():
        if r["metric"] in SESSION_SCOPED_METRICS:
            out[r["metric"]] = r["value"]
    return out


def _event_summary(events) -> list[dict[str, Any]]:
    if events is None or not events.num_rows:
        return []
    rows = events.to_pylist()
    out = []
    for r in rows:
        meta = r.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                pass
        out.append({
            "event_type": r["event_type"],
            "onset": r.get("onset_master_ts"),
            "offset": r.get("offset_master_ts"),
            "stimulus_id": r.get("stimulus_id"),
            "metadata": meta,
        })
    out.sort(key=lambda r: (r["onset"] is None, r["onset"] or 0))
    return out


def _run_summary(runs) -> list[dict[str, Any]]:
    if runs is None or not runs.num_rows:
        return []
    return [{
        "engine_id": r["engine_id"],
        "version": r["version"],
        "source": r["source"],
        "status": r["status"],
        "eligible": r["eligible"],
        "ineligible_reasons": r.get("ineligible_reasons"),
        # Carried so a historical run's licensing stays auditable after the
        # engine package is upgraded or removed.
        "license_spdx": r.get("license_spdx"),
        "license_commercial_use": r.get("license_commercial_use"),
        "clock_uncertainty_ms": r.get("clock_uncertainty_ms"),
        "unaligned_reason": r.get("unaligned_reason"),
    } for r in runs.to_pylist()]

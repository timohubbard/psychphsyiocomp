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

import numpy as np
import pyarrow.compute as pc
import pyarrow.parquet as pq

#: Metrics that describe the session as a whole rather than a rolling window.
SESSION_SCOPED_METRICS = frozenset({
    "gaze_average_offset_px", "gaze_average_offset_deg", "gaze_percent_in_roi",
    "gaze_samples_per_sec", "gaze_validation_targets", "gaze_fit_refused",
    "gaze_calibration_targets", "gaze_onscreen_rate", "gaze_median_extrapolation",
    "gaze_n_fixations", "gaze_median_fixation_ms",
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
        "engine_quality": _engine_quality(quality),
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


def scanpath(root: str | Path, session_id: str,
             start_ms: float | None = None, end_ms: float | None = None) -> dict[str, Any]:
    """Fixations and saccades for drawing, optionally within a time window.

    Read from the events table rather than recomputed from samples, so what is
    drawn is exactly what was recorded — §4.1 warns fixation counts and
    durations are algorithm-dependent, and a viewer that re-derived them with
    different settings would show a different session from the one the metrics
    describe.
    """
    d = Path(root) / f"session_id={session_id}"
    events = _read(d / "events.parquet")
    if events is None or not events.num_rows:
        return {"fixations": [], "saccades": [], "stimuli": []}

    fixations, saccades, stimuli = [], [], []
    for r in events.to_pylist():
        onset, offset = r.get("onset_master_ts"), r.get("offset_master_ts")
        if onset is None:
            continue
        if start_ms is not None and onset < start_ms:
            continue
        if end_ms is not None and onset > end_ms:
            continue

        meta = r.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except json.JSONDecodeError:
                meta = {}
        meta = meta or {}

        if r["event_type"] == "gaze_fixation":
            fixations.append({
                "t": onset, "duration_ms": (offset - onset) if offset else 0.0,
                "x": meta.get("x"), "y": meta.get("y"),
                "n_samples": meta.get("n_samples"),
            })
        elif r["event_type"] == "gaze_saccade":
            saccades.append({
                "t": onset, "duration_ms": (offset - onset) if offset else 0.0,
                "amplitude_deg": meta.get("amplitude_deg"),
                "peak_velocity_deg_s": meta.get("peak_velocity_deg_s"),
            })
        elif r["event_type"].endswith("_point_sampling") and "x" in meta:
            # The target that was on screen. Drawn alongside so a reader can see
            # for themselves whether the fixations went where they were told to
            # look, rather than taking the hit rate on trust.
            stimuli.append({
                "t": onset, "end": offset, "x": meta["x"], "y": meta["y"],
                "kind": r["event_type"].replace("_sampling", ""),
            })

    fixations.sort(key=lambda f: f["t"])
    return {
        "fixations": [f for f in fixations if f["x"] is not None],
        "saccades": saccades,
        "stimuli": sorted(stimuli, key=lambda s: s["t"]),
    }


def phases(root: str | Path, session_id: str) -> list[dict[str, Any]]:
    """Time windows a researcher would want to look at separately.

    A whole-session scanpath overlays the calibration block, the instruction
    screens someone spent eighteen seconds reading, and a minute of staring at a
    fixation cross. All of that is real gaze, and drawing it together makes an
    unreadable tangle that hides the structure rather than showing it — the
    stimulus, not the participant, is what changed.

    Derived from the event log rather than configured, so a study that changes
    its sequence gets the right windows without anyone updating a list.
    """
    d = Path(root) / f"session_id={session_id}"
    events = _read(d / "events.parquet")
    if events is None or not events.num_rows:
        return []

    spans: dict[str, list[float]] = {}
    for r in events.to_pylist():
        onset, offset = r.get("onset_master_ts"), r.get("offset_master_ts")
        if onset is None:
            continue
        end = offset if offset is not None else onset

        etype = r["event_type"]
        if etype.endswith("_point_sampling"):
            key = etype.replace("_point_sampling", "")
        elif etype == "fixation" and r.get("stimulus_id"):
            # The stimulus cross, not a derived gaze fixation — those are
            # namespaced `gaze_fixation` precisely so this test is possible.
            key = "fixation_cross"
        else:
            # Instructions are interleaved through the session, so a single
            # min-to-max span would cover almost all of it and mean nothing.
            # Phases are contiguous viewing blocks or they are not phases.
            continue

        if key not in spans:
            spans[key] = [onset, end]
        else:
            spans[key][0] = min(spans[key][0], onset)
            spans[key][1] = max(spans[key][1], end)

    label = {
        "calibration": "Calibration block",
        "validation": "Validation block",
        "fixation_cross": "Fixation cross",
    }
    out = [{"key": k, "label": label.get(k, k), "start": v[0], "end": v[1],
            "duration_s": round((v[1] - v[0]) / 1000.0, 1)}
           for k, v in spans.items()]
    out.sort(key=lambda p: p["start"])
    return out


#: Both AU engines emit an occurrence score whose classifier decision boundary
#: is 0.5 — Py-Feat's XGBoost `predict_proba`, and OpenGraphAU's cosine score
#: which upstream thresholds at 0.5. This is the engines' own boundary, not one
#: chosen here, which is why it can be used to say "this engine thought the AU
#: was present in x% of frames".
AU_PRESENT_AT = 0.5


def agreement_report(root: str | Path, session_id: str,
                     max_channels: int = 400) -> dict[str, Any]:
    """Per-channel agreement between sources, and what kind of comparison it is.

    §2.2: engine choice alone swung valid-face-frame yield 43%->63% and
    expression counts 3-4x on identical video, with between-engine agreement at
    r = 0.37-0.75. That spread is the free uncertainty estimate, and a channel
    produced by one engine has none — which this reports explicitly rather than
    by omission.

    Filtering happens in Arrow rather than by materialising every row as a dict.
    A session is ~800,000 rows and the alternative is slow enough that the app
    would feel broken.
    """
    from agreement import agreement_for_channel, summarise

    d = Path(root) / f"session_id={session_id}"
    signals = _read_partitioned(d, "signals")
    if signals is None or not signals.num_rows:
        return {"channels": [], "summary": summarise([])}

    channels = sorted(pc.unique(signals.column("channel")).to_pylist())[:max_channels]

    results: list[Any] = []
    present: dict[tuple[str, str], float] = {}
    for ch in channels:
        sub = signals.filter(pc.equal(signals.column("channel"), ch))
        rows = sub.select(["channel", "source", "master_ts", "value"]).to_pylist()
        results.extend(agreement_for_channel(rows, ch))
        if ch.startswith("au."):
            by_src: dict[str, list[float]] = {}
            for r in rows:
                if r["value"] is not None:
                    by_src.setdefault(r["source"], []).append(r["value"])
            for src, vals in by_src.items():
                present[(ch, src)] = float(np.mean(np.asarray(vals) >= AU_PRESENT_AT))

    # Whether the protocol asked for any facial movement. The pilot's AU
    # engines "agreed" at median r = 0.14 on a face that stayed neutral
    # throughout — a figure that reads as disagreement but measured noise.
    events = _read_partitioned(d, "events")
    elicited = bool(events is not None and events.num_rows and pc.any(pc.equal(
        events.column("event_type"), "expression_hold")).as_py())

    return {
        "channels": [{
            "channel": a.channel, "source_a": a.source_a, "source_b": a.source_b,
            "r": a.r, "n": a.n_overlapping, "verdict": a.verdict,
            "kind": a.kind, "detail": a.detail,
            "sd_a": a.sd_a, "sd_b": a.sd_b,
            # Share of frames each engine itself called the AU present. Shown
            # beside r so a low correlation on a unit neither engine ever saw
            # can be read as what it is.
            "present_a": present.get((a.channel, a.source_a)),
            "present_b": present.get((a.channel, a.source_b)),
        } for a in results],
        "summary": {**summarise(results), "movements_elicited": elicited,
                    "au_present_at": AU_PRESENT_AT},
    }


def _engine_quality(quality) -> dict[str, dict[str, Any]]:
    """Last value of every quality metric, grouped by the engine that emitted it.

    `_session_metrics` flattens by metric name, which only works because the
    gaze metrics are prefixed `gaze_`. The engines added since are not: three
    different sources emit `mean_luminance`, and `usable_fraction` is a name any
    engine could reasonably pick. Flattening those into one namespace would let
    whichever engine wrote last silently win.

    Keyed by modality (`voice`, `resp`, ...) taken from the engine id, because
    that is what a researcher is asking about — not which engine implements it.
    """
    if quality is None or not quality.num_rows:
        return {}

    out: dict[str, dict[str, Any]] = {}
    for r in quality.to_pylist():
        modality = str(r["source"]).split(".", 1)[0]
        entry = out.setdefault(modality, {"sources": [], "metrics": {}})
        if r["source"] not in entry["sources"]:
            entry["sources"].append(r["source"])
        # Last write wins within one engine, which for a once-per-run metric is
        # the only value and for a windowed one is the most recent window.
        entry["metrics"][r["metric"]] = r["value"]
    return out


def expression_report(root: str | Path, session_id: str) -> dict[str, Any]:
    """Each AU engine scored against the movements the session asked for.

    See server/expression_scoring.py. A session without the expression_prompts
    task returns a refusal with its reason, not an empty table.
    """
    from expression_scoring import score_session, summarise

    d = Path(root) / f"session_id={session_id}"
    events = _read_partitioned(d, "events")
    signals = _read_partitioned(d, "signals")
    ev = events.to_pylist() if events is not None else []
    rows: list[dict[str, Any]] = []
    if signals is not None and signals.num_rows:
        au = signals.filter(pc.starts_with(signals.column("channel"), "au."))
        rows = au.select(["source", "channel", "master_ts", "value"]).to_pylist()
    report = score_session(rows, ev)
    return {**report.to_dict(), "summary": summarise(report)}

"""Per-stimulus results: where gaze went on each picture, and heatmaps across people.

Each `stimulus` event records where the stimulus was placed on the stage
(`rect_norm`) and the stage's size in pixels, in the same frame the gaze
estimator predicts in. That is what lets everything here be expressed on the
stimulus itself rather than on one participant's screen:

- **AOI metrics** — AOI sets drawn on a stimulus (`stimulus_id` set) are
  placed per presentation with `aoi.to_stage`, then scored with the same
  `aoi.analyse` the screen-space editor uses, over the fixations inside the
  presentation window. Padding is the study's declared `analysis.aoi_pad_deg`;
  §4.2 is why it has no default, and without it these metrics are refused.
- **Heatmaps** — gaze samples mapped into stimulus coordinates, smoothed with
  a Gaussian whose width is given in DEGREES and converted per participant
  through their own geometry, so the same blur means the same visual angle for
  everyone. Each participant contributes equally (their density is
  normalised before averaging), so one long-looking participant cannot paint
  the map. A participant without geometry is refused, not blurred in pixels.

- **Blinks** — per presentation: count, rate per minute of FACE-PRESENT time
  in the window (not of the window: a participant who looked away did not
  stop blinking), share of time with eyes closed, and the latency of the first
  blink after onset. Blinks are inhibited while attention is engaged and
  released after, so the latency is the measure the literature leans on.
  Refused where the face was present for under half the window.
- **Heart rate** — per presentation, only from rPPG windows lying WHOLLY
  inside it. Each value averages 10 s, so a window straddling onset carries
  the pre-stimulus period into the "response"; a stimulus shorter than one
  window is refused rather than given a number that is mostly something else.
  The change is against the session's rest-fixation span when it has one.
  Every value is tiered unvalidated, as the engine's are.

Nothing here reads the recording: fixations, gaze samples and events are the
canonical tables' own rows.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

import numpy as np
import pyarrow.compute as pc

import aoi_store
from aoi import AOISet, analyse, to_stage
from tables import read_session

GAZE_SOURCE_PREFIX = "gaze.ridge@"
BLINK_SOURCE_PREFIX = "blinks.derived@"
CARDIAC_SOURCE_PREFIX = "cardiac.rppg_pos@"
DEFAULT_HEATMAP_SIGMA_DEG = 1.0
#: A presentation with the face present for less of it than this gets no blink figures.
MIN_FACE_SHARE = 0.5
#: Samples further apart than this are face-absent time (blinks.BlinkParams.max_gap_ms).
FACE_GAP_MS = 250.0


def degrees_per_px(session: dict[str, Any]) -> float | None:
    """As tables.CanonicalWriter.degrees_per_px, from a sessions-table row."""
    ppm, dist = session.get("px_per_mm"), session.get("viewing_distance_mm")
    if not ppm or not dist:
        return None
    return math.degrees(math.atan2(1.0 / ppm, dist))


def _meta(e: dict[str, Any]) -> dict[str, Any]:
    m = e.get("metadata")
    if isinstance(m, str):
        try:
            return json.loads(m) or {}
        except json.JSONDecodeError:
            return {}
    return m or {}


def presentations(events: Iterable[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Each stimulus shown, on the master clock. Returns (shown, refusals)."""
    shown, refused = [], []
    for e in events:
        if e.get("event_type") != "stimulus":
            continue
        m = _meta(e)
        on, off = e.get("onset_master_ts"), e.get("offset_master_ts")
        if on is None or off is None or not m.get("rect_norm"):
            refused.append({"stimulus_id": e.get("stimulus_id"),
                            "reason": "unaligned" if on is None or off is None else "no_rect"})
            continue
        shown.append({"stimulus_id": e.get("stimulus_id"), "onset": float(on), "offset": float(off),
                      "rect": m["rect_norm"], "stage_px": m.get("stage_px") or {},
                      "presentation": m.get("presentation")})
    return shown, refused


def _gaze(signals) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g = signals.filter(pc.starts_with(signals["source"], GAZE_SOURCE_PREFIX))

    def ch(name):
        t = g.filter(pc.equal(g["channel"], name))
        return (np.asarray(t["master_ts"].to_pylist(), float),
                np.asarray(t["value"].to_pylist(), float))

    tx, x = ch("gaze.x")
    ty, y = ch("gaze.y")
    if len(tx) != len(ty) or not np.array_equal(tx, ty):
        # gaze.x and gaze.y are written in pairs; a mismatch means a row was
        # lost, and pairing by position would mix two samples' coordinates.
        common, ix, iy = np.intersect1d(tx, ty, return_indices=True)
        return common, x[ix], y[iy]
    return tx, x, y


def _one_source(signals, prefix: str, channel: str):
    """(ts, values, source) for a channel from the one source with this prefix;
    None when there is none, ("ambiguous", sources) when there are several.
    Two versions of one stage in a session are two answers to one question, so
    neither is picked silently."""
    t = signals.filter(pc.and_(pc.starts_with(signals["source"], prefix),
                               pc.equal(signals["channel"], channel)))
    srcs = sorted(set(t["source"].to_pylist()))
    if len(srcs) != 1:
        return None if not srcs else ("ambiguous", srcs)
    ts = np.asarray(t["master_ts"].to_pylist(), float)
    vs = np.asarray(t["value"].to_pylist(), float)
    ok = ~(np.isnan(ts) | np.isnan(vs))
    order = np.argsort(ts[ok])
    return ts[ok][order], vs[ok][order], srcs[0]


def blink_rows(p: dict, base: dict, active, blink_onsets: np.ndarray) -> tuple[dict | None, dict | None]:
    """(row, refusal) for one presentation."""
    common = {**base, "stimulus_id": p["stimulus_id"], "presentation": p["presentation"],
              "duration_ms": p["offset"] - p["onset"]}
    ts, vs, _ = active
    inside = (ts >= p["onset"]) & (ts <= p["offset"])
    gaps = np.diff(ts[inside])
    face_ms = float(gaps[gaps <= FACE_GAP_MS].sum()) if len(gaps) else 0.0
    if face_ms < MIN_FACE_SHARE * common["duration_ms"]:
        return None, {**common, "measure": "blinks", "reason": "face_absent",
                      "detail": f"face present {face_ms / max(common['duration_ms'], 1):.0%} of the window"}
    onsets = blink_onsets[(blink_onsets >= p["onset"]) & (blink_onsets <= p["offset"])]
    return {**common, "face_present_ms": face_ms, "blink_count": int(len(onsets)),
            "blink_rate_per_min": len(onsets) / (face_ms / 60000.0),
            "eyes_closed_fraction": float(vs[inside].mean()),
            "first_blink_latency_ms": float(onsets.min() - p["onset"]) if len(onsets) else None}, None


def heart_rows(p: dict, base: dict, hr, window_ms: float, rest_bpm: float | None,
               rest_reason: str | None) -> tuple[dict | None, dict | None]:
    """(row, refusal) for one presentation."""
    common = {**base, "stimulus_id": p["stimulus_id"], "presentation": p["presentation"],
              "duration_ms": p["offset"] - p["onset"]}
    if common["duration_ms"] < window_ms:
        return None, {**common, "measure": "heart", "reason": "stimulus_shorter_than_hr_window",
                      "detail": f"shown {common['duration_ms'] / 1000:.1f} s; each heart-rate value "
                                f"averages {window_ms / 1000:g} s"}
    ts, vs, src = hr
    half = window_ms / 2
    whole = (ts - half >= p["onset"]) & (ts + half <= p["offset"])
    if not whole.any():
        return None, {**common, "measure": "heart", "reason": "no_passing_windows",
                      "detail": "no heart-rate window inside the presentation passed the quality gates"}
    mean = float(vs[whole].mean())
    return {**common, "source": src, "reliability_tier": "unvalidated", "hr_bpm_mean": mean,
            "hr_windows": int(whole.sum()), "hr_rest_bpm": rest_bpm,
            "hr_delta_vs_rest_bpm": None if rest_bpm is None else mean - rest_bpm,
            "rest_refusal": rest_reason}, None


def rest_heart_rate(events: list[dict], hr, window_ms: float) -> tuple[float | None, str | None]:
    """Median passing heart rate inside the session's rest-fixation spans."""
    spans = [(e["onset_master_ts"], e["offset_master_ts"]) for e in events
             if e.get("event_type") == "fixation" and e.get("onset_master_ts") is not None
             and e.get("offset_master_ts") is not None]
    if not spans:
        return None, "no_rest_fixation"
    ts, vs, _ = hr
    half = window_ms / 2
    inside = np.zeros(len(ts), bool)
    for a, b in spans:
        inside |= (ts - half >= a) & (ts + half <= b)
    if not inside.any():
        return None, "no_passing_windows_at_rest"
    return float(np.median(vs[inside])), None


def per_stimulus_table(out: str | Path, sessions: list[dict[str, Any]], *,
                       pad_deg: float | None) -> list[dict[str, Any]]:
    """One row per stimulus for the cohort page: participant-first means.

    Each participant's presentations of a stimulus are averaged first, then
    participants are averaged, so someone who saw it three times counts once
    (as the epoch curves do). n is participants with a value, per measure.
    """
    by_stim: dict[str, dict[str, Any]] = {}

    def slot(stim):
        return by_stim.setdefault(stim, {"stimulus_id": stim, "vals": {}, "refusals": {}})

    measures = (("gaze", "share_on_stimulus"), ("blinks", "blink_rate_per_min"),
                ("blinks", "first_blink_latency_ms"), ("blinks", "eyes_closed_fraction"),
                ("heart", "hr_bpm_mean"), ("heart", "hr_delta_vs_rest_bpm"))
    for s in sessions:
        r = session_summary(out, s, pad_deg=pad_deg)
        pid = s.get("participant_id") or s["session_id"]
        for kind, field in measures:
            for row in r[kind]:
                v = row.get(field)
                if v is not None:
                    slot(row["stimulus_id"])["vals"].setdefault(field, {}).setdefault(pid, []).append(float(v))
        for ref in r["refusals"]:
            if ref.get("stimulus_id"):
                key = f"{ref.get('measure', 'gaze')}: {ref['reason']}"
                refs = slot(ref["stimulus_id"])["refusals"]
                refs[key] = refs.get(key, 0) + 1
    out_rows = []
    for stim, d in sorted(by_stim.items()):
        row = {"stimulus_id": stim, "refusals": d["refusals"]}
        for _, field in measures:
            per = [float(np.mean(v)) for v in d["vals"].get(field, {}).values()]
            row[field] = float(np.mean(per)) if per else None
            row[f"{field}_n"] = len(per)
        out_rows.append(row)
    return out_rows


def _in_rect(x, y, r) -> np.ndarray:
    return (x >= r["x0"]) & (x <= r["x1"]) & (y >= r["y0"]) & (y <= r["y1"])


def session_summary(out: str | Path, session: dict[str, Any], *, pad_deg: float | None,
                    aoi_root: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Per-presentation gaze and AOI rows for one session."""
    sid = session["session_id"]
    base = {"session_id": sid, "participant_id": session.get("participant_id"),
            "condition": session.get("condition")}
    events = read_session(out, sid, "events").to_pylist()
    shown, refused = presentations(events)
    try:
        t, gx, gy = _gaze(read_session(out, sid, "signals"))
    except FileNotFoundError:
        t = gx = gy = np.empty(0)
    fixations = [SimpleNamespace(x=_meta(e).get("x"), y=_meta(e).get("y"),
                                 onset_ts=e["onset_master_ts"], offset_ts=e["offset_master_ts"],
                                 kind="fixation")
                 for e in events if e.get("event_type") == "gaze_fixation"
                 and e.get("onset_master_ts") is not None and e.get("offset_master_ts") is not None]

    dpp = degrees_per_px(session)
    sets = _stimulus_sets(aoi_root or out)
    gaze_rows, aoi_rows, blinks, heart = [], [], [], []
    refusals = [{**base, **r} for r in refused]

    # Blinks and heart rate: only for sessions whose pipeline ran those stages;
    # a study that never measured heart rate gets no heart-rate refusals.
    try:
        signals = read_session(out, sid, "signals")
    except FileNotFoundError:
        signals = None
    active = _one_source(signals, BLINK_SOURCE_PREFIX, "blink.active") if signals is not None else None
    hr = _one_source(signals, CARDIAC_SOURCE_PREFIX, "cardiac.hr_bpm") if signals is not None else None
    for name, got in (("blinks", active), ("heart", hr)):
        if got and isinstance(got[0], str):
            refusals.append({**base, "measure": name, "reason": "ambiguous_source",
                             "detail": f"more than one {name} source: {got[1]}"})
    active = None if not active or isinstance(active[0], str) else active
    hr = None if not hr or isinstance(hr[0], str) else hr
    blink_onsets = np.asarray([e["onset_master_ts"] for e in events if e.get("event_type") == "blink"
                               and e.get("onset_master_ts") is not None], float)
    window_ms, rest_bpm, rest_reason = 0.0, None, None
    if hr:
        from cohort import hr_window_ms
        window_ms, _ = hr_window_ms(out, sid, hr[2])
        rest_bpm, rest_reason = rest_heart_rate(events, hr, window_ms)

    for p in shown:
        win = (t >= p["onset"]) & (t <= p["offset"])
        n = int(win.sum())
        on_stim = _in_rect(gx[win], gy[win], p["rect"]) if n else np.array([], bool)
        fx = [f for f in fixations if p["onset"] <= f.onset_ts <= p["offset"]]
        gaze_rows.append({**base, "stimulus_id": p["stimulus_id"],
                          "presentation": p["presentation"],
                          "duration_ms": p["offset"] - p["onset"], "gaze_samples": n,
                          "share_on_stimulus": float(on_stim.mean()) if n else None,
                          "n_fixations": len(fx)})
        if n == 0:
            refusals.append({**base, "stimulus_id": p["stimulus_id"], "reason": "no_gaze"})
        if active:
            row, ref = blink_rows(p, base, active, blink_onsets)
            blinks.append(row) if row else refusals.append(ref)
        if hr:
            row, ref = heart_rows(p, base, hr, window_ms, rest_bpm, rest_reason)
            heart.append(row) if row else refusals.append(ref)

        for aset in sets.get(p["stimulus_id"], []):
            stage_set = AOISet(aset.name, aset.version,
                               tuple(to_stage(a, p["rect"]) for a in aset.aois))
            if pad_deg is None:
                result_refusal, result = "no_aoi_pad_deg", None
            else:
                viewport = (float(p["stage_px"].get("width") or 1920),
                            float(p["stage_px"].get("height") or 1080))
                result = analyse(fx, stage_set, pad_deg=pad_deg, degrees_per_px=dpp,
                                 viewport_px=viewport, window_start_ms=p["onset"])
                result_refusal = result.refusal
            common = {**base, "stimulus_id": p["stimulus_id"], "aoi_set": aset.name,
                      "aoi_content_hash": aset.content_hash(), "pad_deg": pad_deg}
            if result_refusal:
                aoi_rows.append({**common, "refusal": result_refusal})
                continue
            for a in aset.aois:
                m = result.metrics[a.aoi_id]
                aoi_rows.append({**common, "aoi_id": a.aoi_id, "refusal": None,
                                 "n_fixations": m.n_fixations, "n_dwells": m.n_dwells,
                                 "total_dwell_ms": m.total_dwell_ms,
                                 "time_to_first_fixation_ms": m.entry_time_ms,
                                 "first_fixation_duration_ms": m.first_fixation_duration_ms})
    return {"gaze": gaze_rows, "aoi": aoi_rows, "blinks": blinks, "heart": heart, "refusals": refusals}


def _stimulus_sets(root: str | Path) -> dict[str, list[AOISet]]:
    """The newest version of every AOI set drawn on a stimulus, by stimulus."""
    out: dict[str, list[AOISet]] = {}
    seen: set[str] = set()
    for row in aoi_store.list_sets(root):
        if not row.get("stimulus_id") or row["name"] in seen:
            continue
        seen.add(row["name"])
        out.setdefault(row["stimulus_id"], []).append(aoi_store.load(root, row["name"]))
    return out


def heatmap(out: str | Path, sessions: Iterable[dict[str, Any]], stimulus_id: str, *,
            grid: tuple[int, int] = (64, 36), sigma_deg: float = DEFAULT_HEATMAP_SIGMA_DEG
            ) -> tuple[np.ndarray | None, int, list[dict[str, Any]]]:
    """Mean per-participant gaze density on one stimulus, in stimulus coordinates.

    Returns (density grid [rows=y, cols=x] summing to 1, participants used,
    refusals). None when nobody contributed.
    """
    from scipy.ndimage import gaussian_filter

    gw, gh = grid
    densities, refusals = [], []
    for s in sessions:
        sid = s["session_id"]
        dpp = degrees_per_px(s)
        shown, _ = presentations(read_session(out, sid, "events").to_pylist())
        mine = [p for p in shown if p["stimulus_id"] == stimulus_id]
        if not mine:
            continue
        if dpp is None:
            refusals.append({"session_id": sid, "stimulus_id": stimulus_id,
                             "reason": "no_geometry"})
            continue
        t, gx, gy = _gaze(read_session(out, sid, "signals"))
        hist = np.zeros((gh, gw))
        sigma_px = None
        for p in mine:
            r = p["rect"]
            win = (t >= p["onset"]) & (t <= p["offset"])
            u = (gx[win] - r["x0"]) / (r["x1"] - r["x0"])
            v = (gy[win] - r["y0"]) / (r["y1"] - r["y0"])
            keep = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
            np.add.at(hist, ((v[keep] * gh).astype(int), (u[keep] * gw).astype(int)), 1)
            stage_w = float(p["stage_px"].get("width") or 1920)
            stim_w_px = (r["x1"] - r["x0"]) * stage_w
            sigma_px = (sigma_deg / dpp) / stim_w_px * gw     # degrees -> grid cells
        if hist.sum() == 0:
            refusals.append({"session_id": sid, "stimulus_id": stimulus_id,
                             "reason": "no_gaze_on_stimulus"})
            continue
        smooth = gaussian_filter(hist, sigma=sigma_px, mode="constant")
        densities.append(smooth / smooth.sum())
    if not densities:
        return None, 0, refusals
    mean = np.mean(densities, axis=0)
    return mean / mean.sum(), len(densities), refusals


def heatmap_png(density: np.ndarray, path: str | Path,
                background: str | Path | None = None) -> None:
    """Colour-map a density grid; blend it over the stimulus image when given."""
    import cv2

    norm = (255 * density / density.max()).astype(np.uint8)
    if background is not None and Path(background).suffix.lower() in (".png", ".jpg", ".jpeg"):
        bg = cv2.imread(str(background))
        h, w = bg.shape[:2]
        heat = cv2.applyColorMap(cv2.resize(norm, (w, h), interpolation=cv2.INTER_CUBIC),
                                 cv2.COLORMAP_INFERNO)
        alpha = cv2.resize(density / density.max(), (w, h))[..., None] * 0.75
        img = (bg * (1 - alpha) + heat * alpha).astype(np.uint8)
    else:
        img = cv2.applyColorMap(cv2.resize(norm, (norm.shape[1] * 10, norm.shape[0] * 10),
                                           interpolation=cv2.INTER_CUBIC), cv2.COLORMAP_INFERNO)
    cv2.imwrite(str(path), img)

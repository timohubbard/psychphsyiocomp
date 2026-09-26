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
DEFAULT_HEATMAP_SIGMA_DEG = 1.0


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
    gaze_rows, aoi_rows = [], []
    refusals = [{**base, **r} for r in refused]

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
    return {"gaze": gaze_rows, "aoi": aoi_rows, "refusals": refusals}


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

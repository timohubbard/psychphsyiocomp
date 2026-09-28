"""Gaze drift: measured against crosses the participant was told to look at, and
corrected from them — adopted only if a late validation block says it helps.

A webcam gaze map is fitted once, at calibration, and then trusted for the
rest of the session while the participant slumps, leans and relaxes. Nothing
measured that until now: every stored study runs validation straight after
calibration, so its error is the map's error at minute one.

**Anchors.** Two things put the participant's eyes on a known point after
calibration: the cross between stimuli (logged as `fixation_cross` since
2026-09-28) and the rest cross (`fixation`). Both sit at the stage centre. The
first 300 ms of each is dropped (the saccade to it), long ones are cut into 5 s
pieces, and an anchor ABSTAINS unless most of its samples sit together and
within MAX_ANCHOR_DEG of the cross: a participant who looked away from the
cross is not evidence of where the map has drifted to.

**Correction.** The offset (cross minus median predicted gaze) at each anchor,
zero at the end of calibration, interpolated linearly in time and held after
the last anchor, is added to every prediction. It never reads a validation
point.

**Scoring.** Only on the LATE validation block (a second `validation` task at
the end of the study; ids `valid_late_*`). Anchors never include it, so the
score is out of sample. Adoption uses gaze_bench.RULE unchanged, with at least
`RULE.min_sessions_per_source` evaluable seeded sessions. Until sessions with a
late block exist, the verdict is "not evaluable", which is the honest answer.

This is a separate stage after the ridge fit, not an EstimatorConfig flag: the
pipeline applies nothing until the rule adopts it, and a flag the pipeline
ignored would be a switch that silently does nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np

SETTLE_MS = 300.0          # the saccade to a cross that just appeared
CHUNK_MS = 5000.0          # long crosses are cut into pieces this long
MIN_SAMPLES = 8
TIGHT_DEG = 2.0            # "together": within this of the anchor's median …
MIN_TIGHT_SHARE = 0.6      # … for at least this share of its samples
#: An anchor further off than this abstains: twice the padding at which
#: verify_gaze counts a fixation as on target. A steady look that far from the
#: cross is more likely a look at something else than drift. Found on
#: s_mucntzzh, whose gaze sat at (0.63, 0.85) for the whole rest minute while
#: the same map put the centre calibration point at (0.49, 0.49): 10-12 deg of
#: "drift" that was the participant looking elsewhere. Set before any late
#: block existed to score drift correction on, so it is not fitted to one.
MAX_ANCHOR_DEG = 9.0


@dataclass(frozen=True)
class AnchorWindow:
    start_ts: float
    end_ts: float
    x: float               # normalised stage coordinates of the cross
    y: float
    kind: str              # 'fixation_cross' | 'rest_fixation'


@dataclass
class Anchor:
    window: AnchorWindow
    t: float                               # master ms, the window's midpoint
    offset: tuple[float, float] | None     # target minus median prediction, normalised
    error_deg: float | None
    n: int
    abstain: str | None = None


@dataclass
class Drift:
    anchors: list[Anchor]
    t0: float                              # end of calibration: zero offset
    slope_deg_per_min: float | None
    used: list[Anchor] = field(default_factory=list)

    def apply(self, ts: np.ndarray, pred: np.ndarray) -> np.ndarray:
        """Predictions with the interpolated offset added; identity without anchors."""
        if not self.used:
            return pred.copy()
        at = np.array([self.t0] + [a.t for a in self.used])
        ox = np.array([0.0] + [a.offset[0] for a in self.used])
        oy = np.array([0.0] + [a.offset[1] for a in self.used])
        out = pred.copy()
        # Before calibration ended there is nothing to correct; np.interp holds
        # the end values outside the range, which is 0 before t0 and the last
        # anchor's offset after it.
        out[:, 0] += np.interp(ts, at, ox)
        out[:, 1] += np.interp(ts, at, oy)
        return out


def _meta(e: dict[str, Any]) -> dict[str, Any]:
    m = e.get("metadata")
    if isinstance(m, str):
        import json
        try:
            return json.loads(m) or {}
        except json.JSONDecodeError:
            return {}
    return m or {}


def anchor_windows(events: Iterable[dict[str, Any]]) -> list[AnchorWindow]:
    """Where the participant was told to look at a cross, on the master clock."""
    out = []
    for e in events:
        et = e.get("event_type")
        if et not in ("fixation_cross", "fixation"):
            continue
        on, off = e.get("onset_master_ts"), e.get("offset_master_ts")
        if on is None or off is None:
            continue
        m = _meta(e)
        x, y = float(m.get("x", 0.5)), float(m.get("y", 0.5))
        a = float(on) + SETTLE_MS
        while a < float(off):
            b = min(a + CHUNK_MS, float(off))
            if b - a >= CHUNK_MS / 5 or a == float(on) + SETTLE_MS:
                out.append(AnchorWindow(a, b, x, y, "fixation_cross" if et == "fixation_cross" else "rest_fixation"))
            a = b
    return sorted(out, key=lambda w: w.start_ts)


def measure(ts: np.ndarray, pred: np.ndarray, windows: list[AnchorWindow], *, t0: float,
            viewport: tuple[float, float], dpp: float) -> Drift:
    """Each anchor's offset (or why it abstained), and the drift slope."""
    scale = np.array([viewport[0] * dpp, viewport[1] * dpp])       # normalised -> degrees
    anchors = []
    for w in windows:
        if w.end_ts <= t0:
            continue
        sel = (ts >= w.start_ts) & (ts <= w.end_ts) & np.all(np.isfinite(pred), axis=1)
        p = pred[sel]
        if len(p) < MIN_SAMPLES:
            anchors.append(Anchor(w, (w.start_ts + w.end_ts) / 2, None, None, len(p), "too_few_samples"))
            continue
        med = np.median(p, axis=0)
        spread = np.hypot(*((p - med) * scale).T)
        if np.mean(spread <= TIGHT_DEG) < MIN_TIGHT_SHARE:
            anchors.append(Anchor(w, (w.start_ts + w.end_ts) / 2, None, None, len(p), "not_looking_steadily"))
            continue
        off = (w.x - med[0], w.y - med[1])
        err = float(np.hypot(off[0] * scale[0], off[1] * scale[1]))
        if err > MAX_ANCHOR_DEG:
            anchors.append(Anchor(w, (w.start_ts + w.end_ts) / 2, None, err, len(p), "looking_elsewhere"))
            continue
        anchors.append(Anchor(w, (w.start_ts + w.end_ts) / 2, off, err, len(p)))
    used = [a for a in anchors if a.offset is not None]
    slope = None
    if len(used) >= 2:
        mins = np.array([(a.t - t0) / 60000.0 for a in used])
        errs = np.array([a.error_deg for a in used])
        if np.ptp(mins) > 0:
            slope = float(np.polyfit(mins, errs, 1)[0])
    return Drift(anchors, t0, slope, used)


def late_error_deg(ts: np.ndarray, pred: np.ndarray, late_spans, *, viewport, dpp, trim: float) -> float | None:
    """Mean distance, in degrees, from each late target to the median prediction in its trimmed window."""
    errs = []
    for s in late_spans:
        a = s.start_ts + (s.end_ts - s.start_ts) * trim
        sel = (ts >= a) & (ts <= s.end_ts) & np.all(np.isfinite(pred), axis=1)
        if sel.sum() < 3:
            continue
        m = np.median(pred[sel], axis=0)
        errs.append(float(np.hypot((m[0] - s.x) * viewport[0] * dpp, (m[1] - s.y) * viewport[1] * dpp)))
    return float(np.mean(errs)) if errs else None


def is_late(span) -> bool:
    return str(span.stimulus_id).startswith("valid_late_")

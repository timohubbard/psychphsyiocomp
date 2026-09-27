"""Blinks and eye closure, from the face engine's eyeBlink blendshapes.

A derived stage, like the gaze estimator: it reads stored channels and writes
events and metrics under its own source, so a better detector re-runs over the
same data without touching the video. Nothing here needs the recording.

**The threshold is per person, not a constant.** On the four real sessions the
eyeBlink score of open eyes sits at 0.20-0.22 (median), but a blink's peak
varies — the 99th percentile ranged from 0.50 to 0.74 — and at 20 fps a
150 ms blink is three frames, whose average can stay under any fixed 0.5. A
fixed 0.5 found 4-10 blinks a minute where 15-20 is usual at rest. So the
"on" level is this session's open-eye baseline (the median) plus the larger of
a fixed rise and a multiple of the score's own spread (MAD), and the "off"
level is halfway back: hysteresis, so one blink is not counted twice as the
score wobbles near the line.

**Blink versus closure.** Eyes shut for longer than `max_blink_ms` are not a
blink; they are counted as a closure, separately. Blink rate is per minute of
FACE-PRESENT time (gaps longer than `max_gap_ms` are not counted), because a
participant who looked away for a minute did not blink zero times in it.

**Named for what it is.** `eyes_closed_fraction` is the share of face-present
time inside a detected blink or closure. It is NOT PERCLOS P80, which needs an
eyelid-closure measure calibrated to each eye's full aperture; a blendshape
score is not that, and borrowing the name would borrow its validation too.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

SOURCE = "blinks.derived@0.1.0+server"


@dataclass(frozen=True)
class BlinkParams:
    min_rise: float = 0.15          # on-level at least this far above the open-eye baseline
    mad_k: float = 6.0              # … or this many MADs, whichever is larger
    min_blink_ms: float = 40.0      # shorter than this is a flicker in the score, not a blink
    max_blink_ms: float = 500.0     # longer than this is a closure, not a blink
    # Two detections this close are one blink. A one-frame dip leaves a gap of
    # two frame intervals — 67 ms at 30 fps, 100 ms at 20 — so 60 merged
    # nothing at real frame rates; two genuine blinks are never 100 ms apart.
    merge_gap_ms: float = 100.0
    max_gap_ms: float = 250.0       # a longer gap in the samples is face-absent time

    def as_params(self) -> dict:
        return asdict(self)


@dataclass
class Detection:
    onset_ms: float
    offset_ms: float
    peak: float
    kind: str                        # 'blink' | 'closure'

    @property
    def duration_ms(self) -> float:
        return self.offset_ms - self.onset_ms


@dataclass
class BlinkResult:
    detections: list[Detection]
    on_level: float
    off_level: float
    baseline: float
    face_minutes: float
    metrics: dict[str, float]
    refusal: str | None = None


def closure_score(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Both eyes together: a blink closes both, a wink or a squint does not."""
    return np.minimum(left, right)


def detect(ts: np.ndarray, score: np.ndarray, params: BlinkParams = BlinkParams()) -> BlinkResult:
    """Blinks and closures in one session's closure score, on the master clock."""
    order = np.argsort(ts)
    ts, score = np.asarray(ts, float)[order], np.asarray(score, float)[order]
    ok = ~(np.isnan(ts) | np.isnan(score))
    ts, score = ts[ok], score[ok]
    if len(ts) < 30:
        return BlinkResult([], np.nan, np.nan, np.nan, 0.0, {}, refusal="too_few_samples")

    gaps = np.diff(ts)
    face_ms = float(np.sum(gaps[gaps <= params.max_gap_ms]))
    baseline = float(np.median(score))
    mad = float(np.median(np.abs(score - baseline)))
    on = baseline + max(params.min_rise, params.mad_k * 1.4826 * mad)
    off = baseline + (on - baseline) / 2

    raw: list[Detection] = []
    i, n = 0, len(ts)
    while i < n:
        if score[i] >= on:
            j = i
            # Walk back to where the score left the off-level, so the onset is
            # the start of the closing, not the moment it crossed the on-line.
            s = i
            while s > 0 and score[s - 1] >= off and ts[s] - ts[s - 1] <= params.max_gap_ms:
                s -= 1
            while j + 1 < n and score[j + 1] >= off and ts[j + 1] - ts[j] <= params.max_gap_ms:
                j += 1
            raw.append(Detection(float(ts[s]), float(ts[j]), float(score[s:j + 1].max()), "blink"))
            i = j + 1
        else:
            i += 1

    merged: list[Detection] = []
    for d in raw:
        if merged and d.onset_ms - merged[-1].offset_ms <= params.merge_gap_ms:
            merged[-1] = Detection(merged[-1].onset_ms, d.offset_ms, max(merged[-1].peak, d.peak), "blink")
        else:
            merged.append(d)

    # A single-frame detection has zero measured span; it lasted at least one
    # sample interval, which is what it is credited with.
    frame = float(np.median(gaps)) if len(gaps) else 0.0
    kept: list[Detection] = []
    for d in merged:
        span = max(d.duration_ms, frame)
        if span < params.min_blink_ms:
            continue
        d.offset_ms = d.onset_ms + span
        d.kind = "closure" if span > params.max_blink_ms else "blink"
        kept.append(d)

    blinks = [d for d in kept if d.kind == "blink"]
    closures = [d for d in kept if d.kind == "closure"]
    minutes = face_ms / 60000.0
    closed_ms = sum(d.duration_ms for d in kept)
    metrics = {
        "blink_rate_per_min": len(blinks) / minutes if minutes > 0 else float("nan"),
        "blink_count": float(len(blinks)),
        "blink_duration_median_ms": float(np.median([d.duration_ms for d in blinks])) if blinks else float("nan"),
        "eye_closure_count": float(len(closures)),
        "eyes_closed_fraction": closed_ms / face_ms if face_ms > 0 else float("nan"),
        "blink_on_level": on,
        "blink_baseline": baseline,
    }
    return BlinkResult(kept, on, off, baseline, minutes, metrics)


def active_series(ts: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """1 where a sample falls inside a blink or closure, else 0 — for epochs:
    the mean of this around an event is the blink probability over time."""
    out = np.zeros(len(ts))
    for d in detections:
        out[(ts >= d.onset_ms) & (ts <= d.offset_ms)] = 1.0
    return out


FACE_SOURCES = ("face.mediapipe_blendshapes@0.1.0+server-batch",
                "face.mediapipe_blendshapes@0.1.0+browser-live")
CHANNELS = frozenset({"blendshape.eyeBlinkLeft", "blendshape.eyeBlinkRight"})


def score_from_rows(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """(master_ts, closure score) from signal rows of one source."""
    left, right = {}, {}
    for r in rows:
        if r.get("master_ts") is None or r.get("value") is None:
            continue
        (left if r["channel"] == "blendshape.eyeBlinkLeft" else right)[r["master_ts"]] = r["value"]
    common = sorted(set(left) & set(right))
    return (np.asarray(common, float),
            closure_score(np.asarray([left[k] for k in common], float),
                          np.asarray([right[k] for k in common], float)))


def run_blinks(writer, params: BlinkParams = BlinkParams()) -> dict:
    """The pipeline stage: detect from this run's face rows, write under SOURCE.

    Prefers the server pass over the recording (every frame, one decoder) and
    falls back to the browser's live pass — the only one a features_in_browser
    session has. Either way the source used is in the params, so two sessions
    measured from different passes stay distinguishable.
    """
    from alignment import ClockSolution
    from engine_contract import Chunk, EventRow, QualityRow, SignalRow

    for src in FACE_SOURCES:
        ts, score = score_from_rows(writer.signal_rows(CHANNELS, src))
        if len(ts) >= 30:
            break
    else:
        return {"status": "refused", "refusal": "no_aligned_blendshapes"}
    res = detect(ts, score, params)
    if res.refusal:
        return {"status": "refused", "refusal": res.refusal}
    # Already on the master clock, so the identity solution is the honest one.
    master = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0,
                           uncertainty_ms=0.0, n_anchors=0)
    active = active_series(ts, res.detections)
    signals = tuple(SignalRow(stream="eyes", channel="blink.active", native_clock_id="performance.now",
                              native_ts=float(t), value=float(v), reliability_tier="moderate")
                    for t, v in zip(ts, active))
    events = tuple(EventRow(event_type="blink" if d.kind == "blink" else "eye_closure",
                            native_clock_id="performance.now", onset_native_ts=d.onset_ms,
                            offset_native_ts=d.offset_ms,
                            metadata={"duration_ms": round(d.duration_ms, 1), "peak": round(d.peak, 3)})
                   for d in res.detections)
    quality = tuple(QualityRow(stream="eyes", metric=m, window_start_native_ts=float(ts[0]),
                               window_end_native_ts=float(ts[-1]), value=float(v))
                    for m, v in res.metrics.items() if np.isfinite(v))
    writer.add_chunks([Chunk(signals=signals, events=events, quality=quality)], source=SOURCE,
                      params={**params.as_params(), "from_source": src}, solution=master)
    return {"status": "ok", "from_source": src, **{k: round(v, 3) for k, v in res.metrics.items()
                                                     if np.isfinite(v)}}


def main() -> int:
    """Read-only: blink metrics for stored sessions, from their saved blendshapes."""
    import argparse
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "packages" / "engine-contract" / "python"))
    import pyarrow as pa
    import pyarrow.compute as pc
    from store import list_sessions
    from tables import read_session

    ap = argparse.ArgumentParser(description="blink metrics from stored sessions — writes nothing")
    ap.add_argument("--data", type=Path, default=root / "out")
    ap.add_argument("--session", default=None)
    args = ap.parse_args()
    ids = [args.session] if args.session else [s["session_id"] for s in list_sessions(args.data)]
    print(f"\n  {'session':14} {'from':12} {'blinks':>6} {'per min':>8} {'median ms':>9} {'closures':>8} {'closed':>7}")
    for sid in ids:
        sig = read_session(args.data, sid, "signals")
        for src in FACE_SOURCES:
            t = sig.filter(pc.and_(pc.equal(sig["source"], src), pc.is_in(sig["channel"], value_set=pa.array(sorted(CHANNELS)))))
            ts, score = score_from_rows(t.select(["channel", "master_ts", "value"]).to_pylist())
            if len(ts) >= 30:
                break
        else:
            print(f"  {sid:14} no aligned blendshapes")
            continue
        m = detect(ts, score).metrics
        print(f"  {sid:14} {src.split('+')[1]:12} {int(m['blink_count']):>6} {m['blink_rate_per_min']:>8.1f} "
              f"{m['blink_duration_median_ms']:>9.0f} {int(m['eye_closure_count']):>8} {m['eyes_closed_fraction']:>7.1%}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

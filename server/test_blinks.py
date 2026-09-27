"""Blink detection, held to blinks planted in a synthetic eyeBlink score.

The score imitates what the real sessions showed: open eyes at ~0.2 with a
little noise, a blink rising to 0.5-0.7 for 100-300 ms, sampled at 20-30 Hz.
"""

from __future__ import annotations

import numpy as np
import pytest

from alignment import ClockSolution
from blinks import BlinkParams, closure_score, detect, run_blinks
from engine_contract import Chunk, SignalRow
from tables import CanonicalWriter, SessionContext, read_session


def series(minutes=2.0, fps=30.0, baseline=0.2, blinks=(), closures=(), gap=None, seed=0):
    rng = np.random.default_rng(seed)
    ts = np.arange(0, minutes * 60000, 1000 / fps)
    s = baseline + rng.normal(0, 0.015, len(ts))
    for at, dur, peak in blinks:
        inside = (ts >= at) & (ts <= at + dur)
        s[inside] = np.maximum(s[inside], peak)
    for at, dur in closures:
        s[(ts >= at) & (ts <= at + dur)] = 0.8
    if gap:
        keep = (ts < gap[0]) | (ts > gap[1])
        ts, s = ts[keep], s[keep]
    return ts, s


def test_planted_blinks_are_found_where_they_were_planted():
    planted = [(5000 + 4000 * i, 150, 0.6) for i in range(20)]
    res = detect(*series(blinks=planted))
    onsets = [d.onset_ms for d in res.detections if d.kind == "blink"]
    assert len(onsets) == 20
    assert all(abs(o - p[0]) <= 40 for o, p in zip(onsets, planted))
    assert res.metrics["blink_rate_per_min"] == pytest.approx(10, abs=0.3)


def test_the_threshold_follows_the_person_not_a_constant():
    """A face whose open eyes score 0.35 (the real range reached 0.3) would be
    a permanent blink under a fixed 0.3 and never blink under a fixed 0.7."""
    planted = [(5000 + 5000 * i, 150, 0.75) for i in range(10)]
    res = detect(*series(baseline=0.35, blinks=planted))
    assert sum(d.kind == "blink" for d in res.detections) == 10
    assert res.on_level > 0.35 + 0.1


def test_a_short_blink_at_20_fps_is_still_counted():
    """Three frames at 20 fps, peaking only at 0.45 — under a fixed 0.5."""
    planted = [(3000 + 3000 * i, 100, 0.45) for i in range(10)]
    res = detect(*series(fps=20, blinks=planted))
    assert sum(d.kind == "blink" for d in res.detections) == 10


def test_a_long_closure_is_not_a_blink():
    res = detect(*series(blinks=[(5000, 150, 0.6)], closures=[(20000, 1200)]))
    kinds = sorted(d.kind for d in res.detections)
    assert kinds == ["blink", "closure"]
    assert res.metrics["blink_count"] == 1 and res.metrics["eye_closure_count"] == 1


def test_a_wink_is_not_a_blink():
    ts, s = series()
    left = s.copy()
    left[(ts > 10000) & (ts < 10200)] = 0.8               # one eye only
    assert not detect(ts, closure_score(left, s)).detections


def test_a_double_peak_is_one_blink():
    ts, s = series()
    s[(ts > 10000) & (ts < 10080)] = 0.6
    s[(ts > 10110) & (ts < 10200)] = 0.6                  # dips for one frame in the middle
    assert len(detect(ts, s).detections) == 1


def test_time_without_a_face_is_not_counted_as_time_without_blinks():
    planted = [(5000 + 4000 * i, 150, 0.6) for i in range(10)]
    res = detect(*series(minutes=2, blinks=planted, gap=(60000, 120000)))
    assert res.face_minutes == pytest.approx(1.0, abs=0.02)
    assert res.metrics["blink_rate_per_min"] == pytest.approx(10, abs=0.5)


def test_too_little_data_is_refused():
    assert detect(np.arange(10.0), np.zeros(10)).refusal == "too_few_samples"


def test_the_pipeline_stage_writes_blinks_under_its_own_source(tmp_path):
    ts, s = series(blinks=[(5000 + 4000 * i, 150, 0.6) for i in range(10)])
    w = CanonicalWriter(tmp_path, SessionContext("s1", "p", "st"))
    w.set_session_metadata({})
    master = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0, uncertainty_ms=0.0, n_anchors=0)
    rows = [SignalRow(stream="face", channel=ch, native_clock_id="performance.now", native_ts=float(t),
                      value=float(v), reliability_tier="moderate")
            for t, v in zip(ts, s) for ch in ("blendshape.eyeBlinkLeft", "blendshape.eyeBlinkRight")]
    w.add_chunks([Chunk(signals=tuple(rows))], source="face.mediapipe_blendshapes@0.1.0+browser-live",
                 params={}, solution=master)
    got = run_blinks(w)
    w.close()
    assert got["status"] == "ok" and got["blink_count"] == 10
    assert got["from_source"].endswith("browser-live")
    ev = [e for e in read_session(tmp_path, "s1", "events").to_pylist() if e["event_type"] == "blink"]
    assert len(ev) == 10 and all(e["offset_master_ts"] > e["onset_master_ts"] for e in ev)
    q = {r["metric"] for r in read_session(tmp_path, "s1", "quality").to_pylist()}
    assert {"blink_rate_per_min", "eyes_closed_fraction"} <= q


def test_the_stage_refuses_without_blendshapes(tmp_path):
    w = CanonicalWriter(tmp_path, SessionContext("s1", "p", "st"))
    w.set_session_metadata({})
    assert run_blinks(w) == {"status": "refused", "refusal": "no_aligned_blendshapes"}

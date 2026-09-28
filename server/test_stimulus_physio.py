"""Blinks and heart rate per stimulus, and heart-rate epochs refused by name."""

from __future__ import annotations

import numpy as np
import pytest

from alignment import ClockSolution
from cohort import EpochSpec, epochs, hr_window_ms
from engine_contract import Chunk, EventRow, SignalRow
from stimulus_summary import session_summary
from study import validate_study
from tables import CanonicalWriter, SessionContext, read_session

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0, uncertainty_ms=0.0, n_anchors=0)
BLINKS = "blinks.derived@0.1.0+server"
CARDIAC = "cardiac.rppg_pos@0.1.0+server-batch"
RECT = {"x0": 0.1, "y0": 0.1, "x1": 0.5, "y1": 0.5}


def ev(kind, on, off, sid=None, meta=None):
    return EventRow(event_type=kind, native_clock_id="performance.now", onset_native_ts=float(on),
                    offset_native_ts=None if off is None else float(off), stimulus_id=sid, metadata=meta)


def stim(sid, on, off):
    return ev("stimulus", on, off, sid, {"rect_norm": RECT, "stage_px": {"width": 1000, "height": 1000},
                                          "presentation": f"p_{sid}"})


def write(out, sid="s1", *, stimuli, blinks=(), face_gap=None, hr=None, rest=None, total_ms=60000):
    w = CanonicalWriter(out, SessionContext(sid, "p1", "st"))
    w.set_session_metadata({})
    events = tuple(stim(*s) for s in stimuli) + ((ev("fixation", *rest, "fixation_1"),) if rest else ())
    w.add_chunks([Chunk(events=events)], source="runner@0.1.0", params={}, solution=MASTER)
    ts = np.arange(0.0, total_ms, 1000 / 30)
    if face_gap:
        ts = ts[(ts < face_gap[0]) | (ts > face_gap[1])]
    active = np.zeros(len(ts))
    for on, dur in blinks:
        active[(ts >= on) & (ts <= on + dur)] = 1.0
    w.add_chunks([Chunk(
        signals=tuple(SignalRow(stream="eyes", channel="blink.active", native_clock_id="performance.now",
                                native_ts=float(t), value=float(v), reliability_tier="moderate")
                      for t, v in zip(ts, active)),
        events=tuple(ev("blink", on, on + dur) for on, dur in blinks))],
        source=BLINKS, params={}, solution=MASTER)
    if hr is not None:
        w.add_chunks([Chunk(signals=tuple(
            SignalRow(stream="cardiac", channel="cardiac.hr_bpm", native_clock_id="performance.now",
                      native_ts=float(t), value=float(v), reliability_tier="unvalidated") for t, v in hr))],
            source=CARDIAC, params={}, solution=MASTER)
    w.close()
    return read_session(out, sid, "sessions").to_pylist()[0]


def test_blinks_are_counted_inside_the_presentation_only(tmp_path):
    row = write(tmp_path, stimuli=[("a", 10000, 20000)],
                blinks=[(5000, 150), (12000, 150), (15500, 200), (25000, 150)])
    r = session_summary(tmp_path, row, pad_deg=None)
    [b] = r["blinks"]
    assert b["blink_count"] == 2
    assert b["first_blink_latency_ms"] == pytest.approx(2000)
    assert b["blink_rate_per_min"] == pytest.approx(2 / (b["face_present_ms"] / 60000))
    assert 0 < b["eyes_closed_fraction"] < 0.1


def test_a_presentation_with_no_blink_has_no_latency_not_zero(tmp_path):
    row = write(tmp_path, stimuli=[("a", 10000, 20000)], blinks=[(30000, 150)])
    [b] = session_summary(tmp_path, row, pad_deg=None)["blinks"]
    assert b["blink_count"] == 0 and b["first_blink_latency_ms"] is None


def test_blink_rate_is_per_face_present_minute_and_refused_when_the_face_was_mostly_gone(tmp_path):
    row = write(tmp_path, stimuli=[("half", 10000, 20000), ("gone", 30000, 40000)],
                blinks=[(11000, 150)], face_gap=(14000, 18000))
    row2 = write(tmp_path / "b", stimuli=[("gone", 30000, 40000)], face_gap=(30500, 39000))
    r = session_summary(tmp_path, row, pad_deg=None)
    [b] = [x for x in r["blinks"] if x["stimulus_id"] == "half"]
    assert b["face_present_ms"] == pytest.approx(6000, abs=100)
    assert b["blink_rate_per_min"] == pytest.approx(10, rel=0.03)      # 1 blink in ~6 s, not in 10 s
    refused = session_summary(tmp_path / "b", row2, pad_deg=None)["refusals"]
    assert [x["reason"] for x in refused if x.get("measure") == "blinks"] == ["face_absent"]


def hr_series(bpm_at, start=5000, end=55000, step=2000):
    return [(t, bpm_at(t)) for t in range(start, end + 1, step)]


def test_heart_rate_uses_only_windows_wholly_inside_the_presentation(tmp_path):
    # 60 bpm before the stimulus, 90 during it: a window straddling onset would read in between.
    hr = hr_series(lambda t: 90.0 if 20000 <= t - 5000 and t + 5000 <= 40000 else 60.0)
    row = write(tmp_path, stimuli=[("long", 20000, 40000)], hr=hr)
    [h] = session_summary(tmp_path, row, pad_deg=None)["heart"]
    assert h["hr_bpm_mean"] == pytest.approx(90.0)
    assert h["hr_windows"] == 6                     # centres 25..35 s every 2 s
    assert h["reliability_tier"] == "unvalidated"


def test_a_stimulus_shorter_than_one_heart_rate_window_is_refused(tmp_path):
    row = write(tmp_path, stimuli=[("brief", 20000, 23000)], hr=hr_series(lambda t: 70.0))
    r = session_summary(tmp_path, row, pad_deg=None)
    assert not r["heart"]
    [ref] = [x for x in r["refusals"] if x.get("measure") == "heart"]
    assert ref["reason"] == "stimulus_shorter_than_hr_window" and "10 s" in ref["detail"]


def test_heart_rate_change_is_against_the_rest_fixation(tmp_path):
    hr = hr_series(lambda t: 80.0 if t > 30000 else 64.0)
    row = write(tmp_path, stimuli=[("long", 35000, 55000)], hr=hr, rest=(0, 25000))
    [h] = session_summary(tmp_path, row, pad_deg=None)["heart"]
    assert h["hr_rest_bpm"] == pytest.approx(64.0)
    assert h["hr_delta_vs_rest_bpm"] == pytest.approx(16.0)


def test_no_heart_rate_stage_means_no_heart_rate_rows_or_refusals(tmp_path):
    row = write(tmp_path, stimuli=[("a", 10000, 20000)])
    r = session_summary(tmp_path, row, pad_deg=None)
    assert r["heart"] == [] and not [x for x in r["refusals"] if x.get("measure") == "heart"]


def test_heart_rate_epochs_shorter_than_the_window_are_refused_by_name(tmp_path):
    row = write(tmp_path, stimuli=[("long", 20000, 40000)], hr=hr_series(lambda t: 70.0))
    short = EpochSpec("hr", "stimulus", ["cardiac.hr_bpm"], pre_ms=4000, post_ms=3000,
                      baseline_ms=(-4000, 0), max_gap_ms=2500)
    rows, refusals = epochs(tmp_path, [row], short)
    assert not rows and refusals[0]["reason"] == "hr_window_longer_than_epoch"
    tight = EpochSpec("hr", "stimulus", ["cardiac.hr_bpm"], pre_ms=4000, post_ms=12000,
                      baseline_ms=(-4000, 0))
    assert epochs(tmp_path, [row], tight)[1][0]["reason"] == "gap_limit_below_hr_step"
    ok = EpochSpec("hr", "stimulus", ["cardiac.hr_bpm"], pre_ms=4000, post_ms=12000,
                   baseline_ms=(-4000, 0), max_gap_ms=2500)
    rows, refusals = epochs(tmp_path, [row], ok)
    assert rows and not refusals


def test_the_heart_rate_window_comes_from_the_run_or_the_manifest(tmp_path):
    write(tmp_path, stimuli=[("a", 1000, 2000)], hr=hr_series(lambda t: 70.0))
    assert hr_window_ms(tmp_path, "s1", CARDIAC) == (10000.0, 2000.0)


def test_epoch_gap_settings_are_read_from_the_study_and_validated():
    d = {"name": "hr", "event_type": "stimulus", "channels": ["cardiac.hr_bpm"], "pre_ms": 4000,
         "post_ms": 12000, "baseline_ms": [-4000, 0], "max_gap_ms": 2500, "min_coverage": 0.8}
    spec = EpochSpec.from_study(d)
    assert spec.max_gap_ms == 2500 and spec.min_coverage == 0.8
    base = {"study_id": "x", "name": "X", "version": "1.0.0",
            "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk"},
            "consent_tiers": ["features_only"], "modalities": ["face"]}
    assert validate_study({**base, "analysis": {"epochs": [d]}}).ok
    bad = validate_study({**base, "analysis": {"epochs": [{**d, "max_gap_ms": 0, "min_coverage": 1.5}]}})
    text = " ".join(bad.reasons)
    assert "max_gap_ms must be" in text and "min_coverage must be" in text

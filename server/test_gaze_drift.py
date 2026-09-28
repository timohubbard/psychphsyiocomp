"""Gaze drift, on predictions with a drift planted in them."""

from __future__ import annotations

import numpy as np
import pytest

from gaze_bench import RULE, Unit, drift_decision
from gaze_drift import MAX_ANCHOR_DEG, anchor_windows, is_late, late_error_deg, measure
from gaze_stage import TargetSpan

VIEW, DPP = (1700.0, 1000.0), 0.025          # ~42 x 25 deg
T0 = 30000.0                                 # calibration ends here
CROSSES = [(T0 + 20000 * k, T0 + 20000 * k + 1500) for k in range(1, 10)]
LATE = [TargetSpan(f"valid_late_{i}", "validation_point", x, y, 215000 + 2000 * i, 216500 + 2000 * i)
        for i, (x, y) in enumerate([(0.3, 0.3), (0.7, 0.3), (0.5, 0.5), (0.3, 0.7), (0.7, 0.7)])]


def ev(kind, on, off, **meta):
    return {"event_type": kind, "onset_master_ts": on, "offset_master_ts": off, "metadata": meta}


def world(drift_end=(0.06, -0.04), noise=0.004, seed=0, look=None):
    """Predictions for a participant who looks at each cross and each late
    target, with a linear drift from nothing at calibration to `drift_end`."""
    rng = np.random.default_rng(seed)
    ts = np.arange(0.0, 230000.0, 1000 / 30)
    truth = np.full((len(ts), 2), 0.5)
    for s in LATE:
        truth[(ts >= s.start_ts) & (ts <= s.end_ts)] = (s.x, s.y)
    if look:
        for (a, b), where in zip(CROSSES, look):
            truth[(ts >= a) & (ts <= b)] = where
    frac = np.clip((ts - T0) / (ts[-1] - T0), 0, 1)[:, None]
    pred = truth - frac * np.array(drift_end) + rng.normal(0, noise, truth.shape)
    events = [ev("fixation_cross", a, b, x=0.5, y=0.5) for a, b in CROSSES]
    return ts, pred, events


def test_a_planted_drift_is_measured_and_corrected():
    ts, pred, events = world()
    d = measure(ts, pred, anchor_windows(events), t0=T0, viewport=VIEW, dpp=DPP)
    assert len(d.used) == len(CROSSES)
    assert d.slope_deg_per_min > 0
    before = late_error_deg(ts, pred, LATE, viewport=VIEW, dpp=DPP, trim=0.25)
    after = late_error_deg(ts, d.apply(ts, pred), LATE, viewport=VIEW, dpp=DPP, trim=0.25)
    assert before > 1.5                          # ~0.06 x 42 deg of horizontal drift by the end
    assert after < 0.3 * before


def test_no_drift_is_left_alone():
    ts, pred, events = world(drift_end=(0.0, 0.0))
    d = measure(ts, pred, anchor_windows(events), t0=T0, viewport=VIEW, dpp=DPP)
    before = late_error_deg(ts, pred, LATE, viewport=VIEW, dpp=DPP, trim=0.25)
    after = late_error_deg(ts, d.apply(ts, pred), LATE, viewport=VIEW, dpp=DPP, trim=0.25)
    assert abs(after - before) < 0.2


def test_the_correction_never_reads_a_validation_point():
    ts, pred, events = world()
    val = [ev("validation_point_sampling", s.start_ts, s.end_ts, x=s.x, y=s.y) for s in LATE]
    assert anchor_windows(events + val) == anchor_windows(events)
    assert all(is_late(s) for s in LATE)


def test_a_participant_looking_elsewhere_is_not_drift():
    # Steady, but at the lower right: the s_mucntzzh rest minute.
    ts, pred, events = world(look=[(0.65, 0.85)] * len(CROSSES))
    d = measure(ts, pred, anchor_windows(events), t0=T0, viewport=VIEW, dpp=DPP)
    assert not d.used
    assert {a.abstain for a in d.anchors} == {"looking_elsewhere"}
    assert all(a.error_deg > MAX_ANCHOR_DEG for a in d.anchors)


def test_an_unsteady_anchor_abstains():
    ts, pred, events = world()
    rng = np.random.default_rng(3)
    a, b = CROSSES[0]
    sel = (ts >= a) & (ts <= b)
    pred[sel] = rng.uniform(0.2, 0.8, (sel.sum(), 2))
    d = measure(ts, pred, anchor_windows(events), t0=T0, viewport=VIEW, dpp=DPP)
    assert d.anchors[0].abstain == "not_looking_steadily" and len(d.used) == len(CROSSES) - 1


def test_no_anchors_means_no_correction():
    ts, pred, _ = world()
    d = measure(ts, pred, [], t0=T0, viewport=VIEW, dpp=DPP)
    assert np.array_equal(d.apply(ts, pred), pred) and d.slope_deg_per_min is None


def test_the_settling_saccade_and_long_crosses_are_handled():
    w = anchor_windows([ev("fixation", 0.0, 60000.0), ev("fixation_cross", 70000.0, 71000.0, x=0.5, y=0.5)])
    rest = [x for x in w if x.kind == "rest_fixation"]
    assert rest[0].start_ts == 300.0                       # the saccade to the cross is dropped
    assert all(x.end_ts - x.start_ts <= 5000 for x in rest) and len(rest) == 12
    assert [x.kind for x in w][-1] == "fixation_cross"


def _unit(sid, seeded=True):
    return Unit(sid, "gaze.mediapipe_features@0.1.0+server-batch", seeded, np.zeros(1), np.zeros((1, 1)),
                (), [], VIEW, DPP, 30.0)


def test_drift_correction_is_not_evaluable_below_three_sessions():
    units = [_unit("a"), _unit("b")]
    scores = {u.label: {"evaluable": True, "before_deg": 3.0, "after_deg": 1.0, "gate_before": 0.6,
                        "gate_after": 1.0} for u in units}
    d = drift_decision(units, scores)
    assert d.verdict == "not_evaluable" and "needs 3" in d.reasons[0]


def test_drift_correction_is_judged_by_the_same_rule():
    units = [_unit(s) for s in "abc"] + [_unit("unseeded", seeded=False)]

    def sc(before, after, gb=0.6, ga=0.8):
        return {"evaluable": True, "before_deg": before, "after_deg": after, "gate_before": gb, "gate_after": ga}
    good = {u.label: sc(3.0, 2.0) for u in units}
    assert drift_decision(units, good).verdict == "adopt"
    one_bad = {**good, units[0].label: sc(2.0, 2.5)}
    d = drift_decision(units, one_bad)
    assert d.verdict == "reject" and "worse on a" in d.reasons[0]
    assert RULE.min_sessions_per_source == 3

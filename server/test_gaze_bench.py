"""The gaze benchmark's rule, and the estimator variants it judges.

The rule is tested on made-up numbers because its job is to be predictable: a
reader should be able to say from the thresholds alone what it will do with any
table, before seeing one.
"""

from __future__ import annotations

import numpy as np
import pytest

from gaze_bench import RULE, Lever, Score, Unit, decide
from gaze_stage import (EstimatorConfig, TargetSpan, fit_grouped, fit_session, frame_rows,
                        loo_bias_corrected)


def unit(sid, source="server-batch", seeded=True):
    z = np.zeros((1, 1))
    return Unit(sid, f"gaze.mediapipe_features@0.1.0+{source}", seeded, np.zeros(1), z, ("c",), [],
                (1920.0, 1080.0), 0.03, 30.0)


def s(primary, secondary=None, gate=1.0):
    return Score(primary, primary if secondary is None else secondary, gate, 0.9)


LEVER = Lever("x", EstimatorConfig(use_pose=False), "h", "lower")


def run(base_vals, lever_vals, units=None, lever=LEVER, sec=None, gates=None):
    units = units or [unit(f"s{i}") for i in range(len(base_vals))]
    base = {u.label: s(b) for u, b in zip(units, base_vals)}
    mine = {u.label: s(v, None if sec is None else sec[i], 1.0 if gates is None else gates[i])
            for i, (u, v) in enumerate(zip(units, lever_vals))}
    return decide(lever, units, base, mine)


def test_a_clear_gain_everywhere_is_adopted():
    d = run([2.0, 2.5, 3.0], [1.6, 2.1, 2.6])
    assert d.verdict == "adopt", d.reasons
    assert d.mean_gain_deg == pytest.approx(0.4)


def test_one_session_getting_clearly_worse_is_a_rejection():
    d = run([2.0, 2.5, 3.0], [1.2, 1.7, 3.2])
    assert d.verdict == "reject"
    assert any("worse on s2" in r for r in d.reasons)


def test_a_small_gain_is_not_enough():
    d = run([2.0, 2.5, 3.0], [1.9, 2.4, 2.9])
    assert d.verdict == "reject" and any("mean gain" in r for r in d.reasons)


def test_the_secondary_figure_must_agree():
    d = run([2.0, 2.5, 3.0], [1.6, 2.1, 2.6], sec=[2.5, 3.0, 3.5])
    assert d.verdict == "reject" and any("leave-one-target-out" in r for r in d.reasons)


def test_a_falling_gate_is_a_rejection_even_with_lower_error():
    d = run([2.0, 2.5, 3.0], [1.6, 2.1, 2.6], gates=[1.0, 0.8, 1.0])
    assert d.verdict == "reject" and any("gate" in r for r in d.reasons)


def test_an_unseeded_session_does_not_vote():
    """A fixed presentation order lets drifting channels stand in for elapsed
    time, so that session's verdict on a lever is confounded."""
    us = [unit("s0"), unit("s1"), unit("s2"), unit("fixed", seeded=False)]
    d = run([2.0, 2.5, 3.0, 1.0], [1.6, 2.1, 2.6, 9.0], units=us)
    assert d.verdict == "adopt" and "fixed" not in d.per_session_delta


def test_two_sources_of_one_session_are_one_vote():
    us = [unit("a", "server-batch"), unit("a", "browser-live"), unit("b"), unit("c")]
    d = run([2.0, 3.0, 2.5, 3.0], [1.6, 3.4, 2.1, 2.6], units=us)
    assert set(d.per_session_delta) == {"a", "b", "c"}
    assert d.per_session_delta["a"] == pytest.approx(0.0)


def test_a_swept_value_must_beat_the_default_everywhere():
    swept = Lever("t", EstimatorConfig(trim_fraction=0.1), "h", "lower", sweep="trim")
    d = run([2.0, 2.5, 3.0], [1.4, 1.9, 3.05], lever=swept)
    assert d.verdict == "reject" and any("every session" in r for r in d.reasons)


def test_a_source_scoped_lever_with_too_few_sessions_is_only_a_candidate():
    scoped = Lever("b", EstimatorConfig(use_pose=False), "h", "lower", scope="browser")
    us = [unit("a", "browser-live"), unit("b", "browser-live")]
    d = run([3.0, 4.0], [2.0, 3.0], units=us, lever=scoped)
    assert d.verdict == "candidate"
    assert any(f"needs {RULE.min_sessions_per_source}" in r for r in d.reasons)


# ---------------------------------------------------------------------------
# the estimator variants
# ---------------------------------------------------------------------------

def test_a_bias_correction_never_uses_the_point_it_corrects():
    """Raising one point's own error must move its corrected figure by exactly
    that much — none of it may be subtracted away by its own contribution."""
    rng = np.random.default_rng(0)
    targets = rng.random((5, 2))
    pred = targets + 0.05 + rng.normal(0, 0.01, (5, 2))
    before = loo_bias_corrected(pred, targets)
    bumped = pred.copy()
    bumped[2] += 0.3
    after = loo_bias_corrected(bumped, targets)
    np.testing.assert_allclose(after[2] - before[2], [0.3, 0.3])
    # …while the other points' corrections do see it, because it IS their evidence.
    assert not np.allclose(after[0], before[0])


def test_alpha_is_chosen_by_holding_out_whole_targets():
    """With per-frame rows, frames of a held-out target's neighbours are near
    copies of it; leaving one frame out would reward memorising targets."""
    rng = np.random.default_rng(1)
    centres = rng.random((13, 2))
    offsets = rng.normal(0, 0.08, (13, 2))            # per-target error, shared by its frames
    rows, ys, groups = [], [], []
    for g, (c, o) in enumerate(zip(centres, offsets)):
        for _ in range(20):
            feats = np.concatenate([c + o, rng.normal(0, 1, 6)]) + rng.normal(0, 0.002, 8)
            rows.append(feats)
            ys.append(c)
            groups.append(g)
    X, y, groups = np.array(rows), np.array(ys), np.array(groups)
    _, alpha = fit_grouped(X, y, groups)
    # Frame-level evaluation would pick the smallest alpha (every frame has a
    # twin in training); target-level must not.
    assert alpha > 1e-3


def test_frame_rows_keep_each_frame_with_its_own_target():
    ts = np.arange(0, 100, 1.0)
    X = ts[:, None].repeat(3, axis=1)
    spans = [TargetSpan("a", "calibration_point", 0.1, 0.2, 0, 40),
             TargetSpan("b", "calibration_point", 0.9, 0.8, 50, 90)]
    F, y, g, kept = frame_rows(ts, X, spans, trim_fraction=0.25)
    assert len(kept) == 2 and set(g) == {0, 1}
    assert np.all(y[g == 0] == [0.1, 0.2]) and np.all(y[g == 1] == [0.9, 0.8])
    assert F[g == 0, 0].min() >= 10  # trimmed: the first quarter of a's window is gone


def test_the_default_config_is_the_shipped_estimator():
    """Passing no config and passing the default give the same fit, to the bit."""
    rng = np.random.default_rng(2)
    grid = [(x, y) for x in (0.1, 0.5, 0.9) for y in (0.1, 0.5, 0.9)] + [(0.3, 0.3), (0.7, 0.3), (0.3, 0.7), (0.7, 0.7)]
    val = [(0.2, 0.2), (0.8, 0.2), (0.45, 0.55), (0.2, 0.8), (0.8, 0.8)]
    ts, X, spans, t = [], [], [], 0.0
    for kind, pts in (("calibration_point", grid), ("validation_point", val)):
        for i, (x, y) in enumerate(pts):
            spans.append(TargetSpan(f"{kind}{i}", kind, x, y, t, t + 1000))
            for k in range(30):
                ts.append(t + k * 33.0)
                X.append([x * 0.3, y * 0.2, x * 0.3, y * 0.2, 0, 0, 0] + list(rng.normal(0, 0.003, 7)[:0]))
            t += 1500
    X = np.array(X) + rng.normal(0, 0.003, (len(X), 7))
    ch = ["eye.left_iris_dx", "eye.left_iris_dy", "eye.right_iris_dx", "eye.right_iris_dy",
          "head_pose.yaw", "head_pose.pitch", "head_pose.roll"]
    kw = dict(viewport_px=(1920, 1080), degrees_per_px=0.03, channels=ch)
    a = fit_session(np.array(ts), X, spans, **kw)
    b = fit_session(np.array(ts), X, spans, config=EstimatorConfig(), **kw)
    assert a.validation.average_offset_deg == b.validation.average_offset_deg
    assert a.alpha == b.alpha

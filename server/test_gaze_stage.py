"""Tests for the gaze estimator stage — the join that cannot live in an engine."""

from __future__ import annotations

import numpy as np
import pytest

from gaze_stage import (
    IRIS_CHANNELS,
    POSE_CHANNELS,
    QUALITY_CHANNELS,
    TargetSpan,
    design_from_channels,
    effective_rate,
    expand_features,
    feature_matrix,
    fit_session,
    pool_spans,
    target_spans,
)

CHANNELS = list(IRIS_CHANNELS) + list(QUALITY_CHANNELS) + list(POSE_CHANNELS)


def rows_at(ts: float, values: dict[str, float]):
    return [{"channel": c, "master_ts": ts, "value": v} for c, v in values.items()]


def full(ts: float, base: float = 0.0):
    return rows_at(ts, {c: base + i * 0.01 for i, c in enumerate(CHANNELS)})


# ---------------------------------------------------------------------------
# target spans
# ---------------------------------------------------------------------------

def _ev(etype, onset, offset, x=None, y=None, sid="s1"):
    meta = {"x": x, "y": y} if x is not None else None
    return {"event_type": etype, "onset_master_ts": onset,
            "offset_master_ts": offset, "stimulus_id": sid, "metadata": meta}


def test_reads_the_sampling_window_not_the_outer_target_window():
    """The outer event opens when the dot APPEARS; the sampling one opens after
    the saccade allowance. Pooling from the outer window would include frames
    where the participant was still looking at the previous target."""
    events = [
        _ev("calibration_point", 1000, 3000, 0.1, 0.1),
        _ev("calibration_point_sampling", 1800, 3000, 0.1, 0.1),
    ]
    spans = target_spans(events)
    assert len(spans) == 1
    assert spans[0].start_ts == 1800


def test_calibration_and_validation_are_distinguished():
    spans = target_spans([
        _ev("calibration_point_sampling", 0, 100, 0.1, 0.1),
        _ev("validation_point_sampling", 200, 300, 0.2, 0.2),
    ])
    assert {s.kind for s in spans} == {"calibration_point", "validation_point"}


def test_an_unaligned_event_is_skipped_not_guessed():
    """A NULL master_ts means alignment refused. Inventing a span would put
    frames from the wrong moment under the wrong target."""
    assert target_spans([_ev("calibration_point_sampling", None, 3000, 0.1, 0.1)]) == []
    assert target_spans([_ev("calibration_point_sampling", 1800, None, 0.1, 0.1)]) == []


def test_events_without_coordinates_are_skipped():
    assert target_spans([_ev("calibration_point_sampling", 0, 100)]) == []


def test_json_encoded_metadata_is_parsed():
    """Metadata survives the Parquet round-trip as a JSON string."""
    e = _ev("calibration_point_sampling", 0, 100)
    e["metadata"] = '{"x": 0.3, "y": 0.7}'
    spans = target_spans([e])
    assert spans[0].x == 0.3 and spans[0].y == 0.7


# ---------------------------------------------------------------------------
# feature matrix
# ---------------------------------------------------------------------------

def test_pivots_long_rows_into_a_matrix():
    rows = full(0.0) + full(33.3)
    ts, X = feature_matrix(rows, CHANNELS)
    assert ts.shape == (2,)
    assert X.shape == (2, len(CHANNELS))


def test_incomplete_timestamps_are_dropped_not_imputed():
    """A frame with a closed eye genuinely produced no iris feature. Imputing
    one invents evidence rather than admitting its absence."""
    rows = full(0.0) + rows_at(33.3, {IRIS_CHANNELS[0]: 0.5})
    ts, X = feature_matrix(rows, CHANNELS)
    assert len(ts) == 1


def test_rows_without_master_ts_are_dropped():
    rows = full(0.0)
    rows.append({"channel": CHANNELS[0], "master_ts": None, "value": 1.0})
    ts, _ = feature_matrix(rows, CHANNELS)
    assert len(ts) == 1


def test_channel_order_is_the_requested_order_not_discovery_order():
    """A silently permuted feature vector does not raise, it just fits worse."""
    rows = list(reversed(full(0.0)))
    _, X = feature_matrix(rows, CHANNELS)
    expected = [i * 0.01 for i in range(len(CHANNELS))]
    assert np.allclose(X[0], expected)


# ---------------------------------------------------------------------------
# pooling
# ---------------------------------------------------------------------------

def _series(n, start=0.0, step=10.0, value_fn=lambda i: i * 1.0):
    rows = []
    for i in range(n):
        rows += rows_at(start + i * step, {c: value_fn(i) for c in CHANNELS})
    return rows


def test_pooling_trims_the_settling_period():
    """The eye is still settling at the start of the dwell window, so including
    those frames biases every target toward the previous one."""
    ts, X = feature_matrix(_series(20, value_fn=lambda i: 0.0 if i < 5 else 10.0), CHANNELS)
    span = TargetSpan("s", "calibration_point", 0.5, 0.5, 0.0, 190.0)
    Xp, _, kept = pool_spans(ts, X, [span], trim_fraction=0.25)
    assert len(kept) == 1
    assert Xp[0, 0] == pytest.approx(10.0), "settling frames leaked into the pool"


def test_pooling_uses_a_median_so_a_blink_cannot_drag_it():
    def vals(i):
        return 99.0 if i == 10 else 1.0
    ts, X = feature_matrix(_series(20, value_fn=vals), CHANNELS)
    span = TargetSpan("s", "calibration_point", 0.5, 0.5, 0.0, 190.0)
    Xp, _, _ = pool_spans(ts, X, [span])
    assert Xp[0, 0] == pytest.approx(1.0)


def test_a_target_with_too_few_frames_is_dropped_not_pooled():
    ts, X = feature_matrix(_series(2), CHANNELS)
    span = TargetSpan("s", "calibration_point", 0.5, 0.5, 0.0, 10.0)
    _, _, kept = pool_spans(ts, X, [span], min_frames=3)
    assert kept == []


# ---------------------------------------------------------------------------
# feature expansion
# ---------------------------------------------------------------------------

def test_expansion_adds_squares_and_products():
    X = np.arange(8.0).reshape(2, 4)
    out = expand_features(X, [0, 1], [])
    # 2 linear + (x0^2, x0*x1, x1^2)
    assert out.shape == (2, 5)
    assert out[0, 2] == pytest.approx(X[0, 0] ** 2)
    assert out[0, 3] == pytest.approx(X[0, 0] * X[0, 1])


def test_pose_is_appended_linearly_not_expanded():
    X = np.arange(10.0).reshape(1, 10)
    out = expand_features(X, [0, 1], [7, 8, 9])
    assert out.shape == (1, 2 + 3 + 3)


def test_design_excludes_the_drifting_quality_channels():
    """The measured leak: with a fixed stimulus order, eyelid aperture and
    inter-ocular distance stand in for elapsed time, which stands in for target
    position. That model scored BEST by leave-one-out (2.62 deg) and WORST on
    held-out targets (5.04 deg)."""
    # Tested by perturbation rather than by comparing values: the quadratic
    # terms are products of the iris columns, so any fixed set of inputs can
    # produce a product that coincides with a quality channel's value by
    # accident and prove nothing either way.
    X = np.arange(float(len(CHANNELS))).reshape(1, -1)
    baseline = design_from_channels(X, CHANNELS)

    for c in QUALITY_CHANNELS:
        perturbed = X.copy()
        perturbed[0, CHANNELS.index(c)] += 1000.0
        assert np.allclose(design_from_channels(perturbed, CHANNELS), baseline), (
            f"{c} changed the design matrix, so the estimator can see it"
        )

    # And it does still see the channels it is supposed to.
    for c in IRIS_CHANNELS + POSE_CHANNELS:
        perturbed = X.copy()
        perturbed[0, CHANNELS.index(c)] += 1000.0
        assert not np.allclose(design_from_channels(perturbed, CHANNELS), baseline), (
            f"{c} is invisible to the estimator"
        )


def test_design_without_iris_channels_is_an_error():
    with pytest.raises(ValueError):
        design_from_channels(np.zeros((1, 3)), list(POSE_CHANNELS))


# ---------------------------------------------------------------------------
# fitting a session
# ---------------------------------------------------------------------------

def _synthetic_session(n_cal=13, n_val=5, noise=0.0, seed=0):
    """A session where iris offset maps linearly to target position."""
    rng = np.random.default_rng(seed)
    grid = [(x, y) for y in (0.1, 0.5, 0.9) for x in (0.1, 0.5, 0.9)][:n_cal]
    while len(grid) < n_cal:
        grid.append((rng.random(), rng.random()))
    vals = [(0.2, 0.2), (0.8, 0.2), (0.45, 0.55), (0.2, 0.8), (0.8, 0.8)][:n_val]

    rows, spans, t = [], [], 0.0
    for kind, targets in (("calibration_point", grid), ("validation_point", vals)):
        for k, (tx, ty) in enumerate(targets):
            start = t
            for _ in range(12):
                v = {
                    "eye.left_iris_dx": (tx - 0.5) * 0.8 + rng.normal(0, noise),
                    "eye.left_iris_dy": (ty - 0.5) * 0.6 + rng.normal(0, noise),
                    "eye.right_iris_dx": (tx - 0.5) * 0.78 + rng.normal(0, noise),
                    "eye.right_iris_dy": (ty - 0.5) * 0.62 + rng.normal(0, noise),
                    "eye.left_openness": 0.3, "eye.right_openness": 0.3,
                    "eye.inter_ocular_px": 220.0,
                    "head_pose.yaw": 0.0, "head_pose.pitch": 0.0, "head_pose.roll": 0.0,
                }
                rows += rows_at(t, v)
                t += 33.3
            spans.append(TargetSpan(f"{kind}_{k}", kind, tx, ty, start, t - 33.3))
            t += 100.0
    return rows, spans


def test_fits_and_scores_a_clean_session():
    rows, spans = _synthetic_session()
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=0.0236, channels=CHANNELS)

    assert fit.refusal is None
    assert fit.n_calibration_targets == 13
    assert fit.n_validation_targets == 5
    assert fit.validation.average_offset_deg < 1.0


def test_validation_targets_are_never_fitted_on():
    """Scoring on fitted coordinates measures memorisation, and ridge with a
    small alpha can memorise 13 points almost exactly."""
    rows, spans = _synthetic_session()
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=0.0236, channels=CHANNELS)

    fitted = {(s.x, s.y) for s in spans if s.kind == "calibration_point"}
    scored = {(s.x, s.y) for s in spans if s.kind == "validation_point"}
    assert not (fitted & scored), "the synthetic session overlaps; the test proves nothing"
    assert fit.n_validation_targets == len(scored)


def test_too_few_calibration_targets_refuses_rather_than_fitting():
    rows, spans = _synthetic_session(n_cal=3)
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=None, channels=CHANNELS)
    assert fit.refusal == "insufficient_calibration"
    assert fit.model is None


def test_no_validation_targets_refuses_to_report_accuracy():
    """A model with no held-out score is not a model with a good score."""
    rows, spans = _synthetic_session(n_val=0)
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=None, channels=CHANNELS)
    assert fit.refusal == "no_validation"
    assert fit.validation is None


def test_angular_error_is_absent_without_geometry():
    rows, spans = _synthetic_session()
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=None, channels=CHANNELS)
    assert fit.validation.average_offset_deg is None
    assert fit.validation.average_offset_px > 0


def test_reported_rate_is_the_feature_rate_not_one_sample_per_target():
    """§5.3's 5Hz threshold is evaluated against this, so it has to be the rate
    at which gaze was measurable — not the number of pooled targets."""
    rows, spans = _synthetic_session()
    ts, X = feature_matrix(rows, CHANNELS)
    fit = fit_session(ts, X, spans, viewport_px=(1707, 1067),
                      degrees_per_px=0.0236, channels=CHANNELS)
    assert fit.validation.samples_per_sec > 10.0


def test_effective_rate_handles_degenerate_input():
    assert effective_rate(np.array([])) == 0.0
    assert effective_rate(np.array([5.0])) == 0.0

"""Tests for the ridge gaze estimator and the validation metrics.

Pure maths over synthetic features, deliberately: the point of separating the
estimator from the feature engine is that the part which can be silently wrong
runs in a test suite rather than only on a webcam.
"""

from __future__ import annotations

import numpy as np
import pytest

from gaze_ridge import (
    MIN_SAMPLING_RATE_HZ,
    GateCriteria,
    RidgeGaze,
    ValidationResult,
    gate,
    validate,
)

RNG = np.random.default_rng(0)

#: The 13-point grid the capture page actually presents (web/src/sequence.js).
CALIB = np.array([
    [0.1, 0.1], [0.5, 0.1], [0.9, 0.1],
    [0.1, 0.5], [0.5, 0.5], [0.9, 0.5],
    [0.1, 0.9], [0.5, 0.9], [0.9, 0.9],
    [0.3, 0.3], [0.7, 0.3],
    [0.3, 0.7], [0.7, 0.7],
])


def synth_features(targets, noise=0.0, rng=RNG):
    """Plausible eye features for someone looking at each target.

    Iris offset moves with gaze, head pose drifts slowly, and one feature is
    pure noise — a stand-in for the channels that will inevitably be in the
    real vector without carrying signal.
    """
    t = np.asarray(targets, dtype=float)
    n = len(t)
    drift = np.linspace(-3, 3, n)
    return np.column_stack([
        (t[:, 0] - 0.5) * 0.8 + rng.normal(0, noise, n),   # left iris dx
        (t[:, 1] - 0.5) * 0.6 + rng.normal(0, noise, n),   # left iris dy
        (t[:, 0] - 0.5) * 0.78 + rng.normal(0, noise, n),  # right iris dx
        (t[:, 1] - 0.5) * 0.62 + rng.normal(0, noise, n),  # right iris dy
        drift,                                             # head yaw, degrees
        drift * 0.4,                                       # head pitch
        rng.normal(0, 1, n),                               # uninformative
    ])


# ---------------------------------------------------------------------------
# fitting
# ---------------------------------------------------------------------------

def test_recovers_a_clean_linear_mapping():
    X = synth_features(CALIB)
    m = RidgeGaze(alpha=1e-6).fit(X, CALIB)
    err = np.hypot(*(m.predict(X) - CALIB).T)
    assert err.mean() < 0.01, f"mean training error {err.mean():.4f} in screen fractions"


def test_predicts_held_out_points_it_never_saw():
    """The only claim that matters: generalisation, not memorisation."""
    train = CALIB
    held_out = np.array([[0.2, 0.2], [0.8, 0.8], [0.45, 0.55]])

    m, alpha, _ = RidgeGaze.fit_with_loocv(synth_features(train), train)
    pred = m.predict(synth_features(held_out))

    err = np.hypot(*(pred - held_out).T)
    assert err.mean() < 0.05, f"held-out error {err.mean():.4f} at alpha={alpha}"


def test_standardisation_makes_units_irrelevant():
    """Head pose in degrees and iris offset in eye-widths differ by ~100x.

    Without standardisation ridge would penalise them at wildly different
    effective strengths purely because of the units they arrived in. Rescaling
    one column must not change what the model predicts.
    """
    X = synth_features(CALIB)
    a = RidgeGaze(alpha=1.0).fit(X, CALIB).predict(X)

    X2 = X.copy()
    X2[:, 4] *= 1000.0          # yaw in millidegrees, say
    b = RidgeGaze(alpha=1.0).fit(X2, CALIB).predict(X2)

    assert np.allclose(a, b, atol=1e-6)


def test_constant_feature_does_not_blow_up():
    """A channel that never varies has zero spread and would divide to infinity."""
    X = synth_features(CALIB)
    X[:, 6] = 4.2
    pred = RidgeGaze(alpha=1.0).fit(X, CALIB).predict(X)
    assert np.all(np.isfinite(pred))


def test_intercept_is_not_penalised():
    """Shrinking the intercept pulls predictions toward the screen's top-left
    corner rather than toward the data, which is not a prior anyone holds."""
    X = synth_features(CALIB)
    heavy = RidgeGaze(alpha=1e6).fit(X, CALIB).predict(X)

    # With the slopes crushed, predictions should collapse to the mean target,
    # not to (0, 0).
    assert np.allclose(heavy.mean(axis=0), CALIB.mean(axis=0), atol=0.02)
    assert np.hypot(*heavy.mean(axis=0)) > 0.3, "collapsed toward the origin"


def test_regularisation_beats_least_squares_on_noisy_data():
    """The reason ridge is the floor rather than plain least squares.

    13 points against 7 features is a regime where OLS interpolates the noise
    and generalises badly. This is that claim, measured.
    """
    train_X = synth_features(CALIB, noise=0.05, rng=np.random.default_rng(1))
    held_out = np.array([[0.2, 0.2], [0.8, 0.8], [0.45, 0.55], [0.2, 0.8], [0.8, 0.2]])
    test_X = synth_features(held_out, noise=0.05, rng=np.random.default_rng(2))

    ols = RidgeGaze(alpha=1e-10).fit(train_X, CALIB)
    ridged, _, _ = RidgeGaze.fit_with_loocv(train_X, CALIB)

    e_ols = np.hypot(*(ols.predict(test_X) - held_out).T).mean()
    e_ridge = np.hypot(*(ridged.predict(test_X) - held_out).T).mean()

    assert e_ridge < e_ols, f"ridge {e_ridge:.4f} did not beat OLS {e_ols:.4f}"


def test_loocv_picks_more_regularisation_for_noisier_data():
    clean, a_clean, _ = RidgeGaze.fit_with_loocv(
        synth_features(CALIB, noise=0.002, rng=np.random.default_rng(3)), CALIB)
    noisy, a_noisy, _ = RidgeGaze.fit_with_loocv(
        synth_features(CALIB, noise=0.15, rng=np.random.default_rng(4)), CALIB)

    assert a_noisy > a_clean, f"noisy chose {a_noisy}, clean chose {a_clean}"


def test_predict_before_fit_is_an_error():
    with pytest.raises(RuntimeError):
        RidgeGaze().predict(synth_features(CALIB))


def test_mismatched_shapes_are_rejected():
    X = synth_features(CALIB)
    with pytest.raises(ValueError):
        RidgeGaze().fit(X, CALIB[:5])
    with pytest.raises(ValueError):
        RidgeGaze().fit(X, CALIB[:, 0])


# ---------------------------------------------------------------------------
# validation metrics
# ---------------------------------------------------------------------------

VIEWPORT = (1440.0, 900.0)


def _ts(n, hz=30.0):
    return np.arange(n) * (1000.0 / hz)


def test_perfect_prediction_scores_perfectly():
    r = validate(CALIB, CALIB, _ts(len(CALIB)),
                 viewport_px=VIEWPORT, roi_radius_px=100)
    assert r.average_offset_px == pytest.approx(0.0)
    assert r.percent_in_roi == 1.0
    assert r.n_targets == 13


def test_offset_is_measured_in_real_pixels():
    pred = CALIB + np.array([0.05, 0.0])          # 5% of 1440px = 72px
    r = validate(CALIB, pred, _ts(len(CALIB)),
                 viewport_px=VIEWPORT, roi_radius_px=100)
    assert r.average_offset_px == pytest.approx(72.0)


def test_percent_in_roi_counts_what_it_says():
    pred = CALIB.copy()
    pred[:4, 0] += 0.2                            # 288px off — well outside
    r = validate(CALIB, pred, _ts(len(CALIB)),
                 viewport_px=VIEWPORT, roi_radius_px=100)
    assert r.percent_in_roi == pytest.approx(9 / 13)


def test_degrees_require_geometry_and_are_none_without_it():
    """§5.1: viewing distance was mean 47.3cm, SD 8.9, across 1,153 people.

    A degree figure computed from a nominal distance is a pixel count wearing a
    unit, so the angular metric has to be absent rather than approximated.
    """
    pred = CALIB + np.array([0.05, 0.0])
    without = validate(CALIB, pred, _ts(len(CALIB)),
                       viewport_px=VIEWPORT, roi_radius_px=100)
    assert without.average_offset_deg is None
    assert without.average_offset_px > 0, "the pixel figure is always available"

    with_geom = validate(CALIB, pred, _ts(len(CALIB)),
                         viewport_px=VIEWPORT, roi_radius_px=100,
                         degrees_per_px=0.0236)
    assert with_geom.average_offset_deg == pytest.approx(72.0 * 0.0236)


def test_sampling_rate_uses_the_span_actually_covered():
    """§2.1 measured 9-39 fps jittering across home setups, so dividing by a
    nominal duration rather than the observed span is not a rounding choice."""
    r = validate(CALIB, CALIB, _ts(len(CALIB), hz=12.0),
                 viewport_px=VIEWPORT, roi_radius_px=100)
    assert r.samples_per_sec == pytest.approx(12.0, rel=0.1)


def test_empty_input_is_an_error_not_a_zero():
    with pytest.raises(ValueError):
        validate(np.empty((0, 2)), np.empty((0, 2)), np.empty(0),
                 viewport_px=VIEWPORT, roi_radius_px=100)


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

def _result(**kw) -> ValidationResult:
    base = dict(average_offset_px=50.0, average_offset_deg=1.2,
                percent_in_roi=0.9, samples_per_sec=25.0,
                n_samples=100, n_targets=5)
    base.update(kw)
    return ValidationResult(**base)


def test_gate_passes_a_good_block():
    ok, reasons = gate(_result(), GateCriteria(max_offset_deg=2.0, min_percent_in_roi=0.8))
    assert ok and reasons == []


def test_gate_names_every_failure_rather_than_the_first():
    """The pattern §5.1 records is a gate with forced RETRY, not exclusion —
    so the participant has to be told everything that needs fixing at once."""
    ok, reasons = gate(
        _result(average_offset_deg=5.0, percent_in_roi=0.2, samples_per_sec=3.0),
        GateCriteria(max_offset_deg=2.0, min_percent_in_roi=0.8),
    )
    assert not ok
    assert len(reasons) == 3, reasons


def test_gate_refuses_an_angular_criterion_without_geometry():
    """Silently falling back to a pixel threshold would apply a criterion the
    researcher never preregistered."""
    ok, reasons = gate(_result(average_offset_deg=None),
                       GateCriteria(max_offset_deg=2.0))
    assert not ok
    assert reasons == ["no_geometry_for_angular_criterion"]


def test_sampling_rate_floor_matches_the_published_threshold():
    # §5.3: 5 Hz, applied in a published study, excluded 18 of 220.
    assert GateCriteria().min_samples_per_sec == MIN_SAMPLING_RATE_HZ == 5.0


def test_default_criteria_assert_no_accuracy_threshold():
    """§5.3: jsPsych publishes none, so neither do we.

    A default here would invent a standard that does not exist and hide the
    choice from the person who has to defend it in a methods section.
    """
    c = GateCriteria()
    assert c.max_offset_deg is None
    assert c.max_offset_px is None

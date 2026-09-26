"""Tests for the gaze feature engine's pure maths.

Named distinctly from the facial engine's test_engine.py on purpose: two test
files sharing a basename without packages collide during collection, and two
modules named `engine` on sys.path resolve to whichever was inserted last.
That is why media probing moved into the contract package.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from engine_contract.loader import load_engine_module

# Loaded by engine_id, never by sys.path order — see conftest.py.
_engine = load_engine_module("gaze.mediapipe_features")
FEATURE_CHANNELS = _engine.FEATURE_CHANNELS
LEFT_EYE_INNER = _engine.LEFT_EYE_INNER
LEFT_EYE_LOWER = _engine.LEFT_EYE_LOWER
LEFT_EYE_OUTER = _engine.LEFT_EYE_OUTER
LEFT_EYE_UPPER = _engine.LEFT_EYE_UPPER
LEFT_IRIS_CENTRE = _engine.LEFT_IRIS_CENTRE
MIN_OPENNESS = _engine.MIN_OPENNESS
RELIABILITY = _engine.RELIABILITY
RIGHT_EYE_INNER = _engine.RIGHT_EYE_INNER
RIGHT_EYE_LOWER = _engine.RIGHT_EYE_LOWER
RIGHT_EYE_OUTER = _engine.RIGHT_EYE_OUTER
RIGHT_EYE_UPPER = _engine.RIGHT_EYE_UPPER
RIGHT_IRIS_CENTRE = _engine.RIGHT_IRIS_CENTRE
euler_from_matrix = _engine.euler_from_matrix
eye_features = _engine.eye_features
features_from_landmarks = _engine.features_from_landmarks


def P(x, y):
    return np.array([float(x), float(y)])


# ---------------------------------------------------------------------------
# normalised iris offset
# ---------------------------------------------------------------------------

def test_centred_iris_reads_as_zero_offset():
    dx, dy, _ = eye_features(P(50, 50), P(40, 50), P(60, 50), P(50, 45), P(50, 55))
    assert dx == pytest.approx(0.0)
    assert dy == pytest.approx(0.0)


def test_offset_is_measured_in_eye_widths():
    # Iris 5px right of centre in a 20px-wide eye is a quarter of an eye width.
    dx, _, _ = eye_features(P(55, 50), P(40, 50), P(60, 50), P(50, 45), P(50, 55))
    assert dx == pytest.approx(0.25)


def test_the_same_gaze_at_a_different_distance_gives_the_same_feature():
    """The entire reason for normalising.

    An unnormalised pixel offset encodes how much of the frame the face fills
    far more strongly than where the participant is looking — so the model would
    learn seating position and call it gaze.
    """
    near = eye_features(P(55, 50), P(40, 50), P(60, 50), P(50, 45), P(50, 55))
    far = eye_features(P(52.5, 50), P(45, 50), P(55, 50), P(50, 47.5), P(50, 52.5))
    assert near[0] == pytest.approx(far[0])
    assert near[2] == pytest.approx(far[2])


def test_corner_order_does_not_matter():
    """Which corner is nasal differs between the two eyes.

    If order mattered, getting it wrong for one eye would produce a model that
    is subtly and consistently wrong rather than obviously broken.
    """
    a = eye_features(P(55, 50), P(40, 50), P(60, 50), P(50, 45), P(50, 55))
    b = eye_features(P(55, 50), P(60, 50), P(40, 50), P(50, 45), P(50, 55))
    assert a == b


def test_degenerate_eye_yields_nan_not_a_division_by_zero():
    dx, dy, openness = eye_features(P(50, 50), P(50, 50), P(50, 50), P(50, 45), P(50, 55))
    assert math.isnan(dx) and math.isnan(dy) and math.isnan(openness)


def test_openness_is_aperture_over_width():
    _, _, openness = eye_features(P(50, 50), P(40, 50), P(60, 50), P(50, 46), P(50, 54))
    assert openness == pytest.approx(8.0 / 20.0)


def test_a_closed_eye_falls_below_the_gate():
    _, _, openness = eye_features(P(50, 50), P(40, 50), P(60, 50), P(50, 50), P(50, 50.5))
    assert openness < MIN_OPENNESS


# ---------------------------------------------------------------------------
# assembling a frame's features
# ---------------------------------------------------------------------------

class FakeLandmark:
    """MediaPipe returns x and y each divided by their OWN axis length."""

    def __init__(self, x, y):
        self.x = x
        self.y = y


def landmark_set(width=1280, height=720, iris_shift_px=0.0):
    pts = [FakeLandmark(0.5, 0.5) for _ in range(478)]

    def put(i, x_px, y_px):
        pts[i] = FakeLandmark(x_px / width, y_px / height)

    # Subject-right eye sits image-left, matching MediaPipe's convention.
    put(RIGHT_EYE_OUTER, 500, 360)
    put(RIGHT_EYE_INNER, 560, 360)
    put(RIGHT_EYE_UPPER, 530, 348)
    put(RIGHT_EYE_LOWER, 530, 372)
    put(RIGHT_IRIS_CENTRE, 530 + iris_shift_px, 360)

    put(LEFT_EYE_INNER, 720, 360)
    put(LEFT_EYE_OUTER, 780, 360)
    put(LEFT_EYE_UPPER, 750, 348)
    put(LEFT_EYE_LOWER, 750, 372)
    put(LEFT_IRIS_CENTRE, 750 + iris_shift_px, 360)
    return pts


def test_features_are_computed_in_pixels_not_normalised_units():
    """MediaPipe divides x and y by different axis lengths.

    On a 16:9 frame that turns a circle into an ellipse, so a vertical offset
    would not mean the same thing as an equal horizontal one. Scaling back to
    pixels before measuring any distance is what restores the aspect ratio —
    without it the openness ratio is wrong by 16/9 and the error changes with
    frame shape.
    """
    wide = features_from_landmarks(landmark_set(1280, 720), 1280, 720)
    tall = features_from_landmarks(landmark_set(720, 1280), 720, 1280)

    # Same physical geometry described on two differently-shaped frames.
    assert wide["eye.left_openness"] == pytest.approx(tall["eye.left_openness"])
    assert wide["eye.inter_ocular_px"] == pytest.approx(tall["eye.inter_ocular_px"])


def test_inter_ocular_distance_is_the_iris_separation():
    f = features_from_landmarks(landmark_set(), 1280, 720)
    assert f["eye.inter_ocular_px"] == pytest.approx(220.0)


def test_iris_shift_moves_both_eyes_together():
    """Both eyes look the same way; a feature set where they disagree by
    construction would let the estimator fit noise."""
    f = features_from_landmarks(landmark_set(iris_shift_px=12.0), 1280, 720)
    assert f["eye.left_iris_dx"] == pytest.approx(12.0 / 60.0)
    assert f["eye.right_iris_dx"] == pytest.approx(12.0 / 60.0)


def test_too_few_landmarks_returns_none_rather_than_indexing_past_the_end():
    """The 468-point model has no iris points at all."""
    assert features_from_landmarks([FakeLandmark(0.5, 0.5)] * 468, 1280, 720) is None
    assert features_from_landmarks(None, 1280, 720) is None


def test_every_declared_feature_channel_is_produced_or_is_head_pose():
    f = features_from_landmarks(landmark_set(), 1280, 720)
    produced = set(f) | {"head_pose.yaw", "head_pose.pitch", "head_pose.roll"}
    assert set(FEATURE_CHANNELS) <= produced


def test_every_channel_declares_a_reliability_tier():
    """§2.2's per-channel floors are a schema field, not a UI convention."""
    for ch in FEATURE_CHANNELS:
        assert ch in RELIABILITY, f"{ch} has no reliability tier"


def test_vertical_iris_channels_are_tiered_below_horizontal():
    """Vertical eye movement has a fraction of the horizontal range and is
    partly occluded by the lid, so the same pixel noise is a far larger share
    of the signal. Tiering them identically would overstate the vertical."""
    order = {"low": 0, "moderate": 1, "high": 2}
    assert order[RELIABILITY["eye.left_iris_dy"]] < order[RELIABILITY["eye.left_iris_dx"]]
    assert order[RELIABILITY["eye.right_iris_dy"]] < order[RELIABILITY["eye.right_iris_dx"]]


# ---------------------------------------------------------------------------
# head pose must match the facial engine exactly
# ---------------------------------------------------------------------------

def test_a_nod_reads_as_pitch_not_roll():
    """The Y-X-Z convention, pinned here as it is in the facial engine.

    Under the aerospace Z-Y-X ordering a pure X-rotation decomposes into roll,
    so a nod would be reported as a head tilt — and the same video would give
    different head pose depending on which engine processed it.
    """
    a = math.radians(20)
    rx = np.array([
        [1, 0, 0, 0],
        [0, math.cos(a), -math.sin(a), 0],
        [0, math.sin(a), math.cos(a), 0],
        [0, 0, 0, 1],
    ])
    yaw, pitch, roll = euler_from_matrix(rx)
    # Sign matches the facial engine's own parametrised test, which asserts
    # pitch == deg for a pure X-rotation. Agreement between the two is the
    # property under test, so the expected value is taken from there rather
    # than re-derived independently.
    assert pitch == pytest.approx(20.0, abs=1e-6)
    assert yaw == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


def test_a_head_turn_reads_as_yaw():
    a = math.radians(30)
    ry = np.array([
        [math.cos(a), 0, math.sin(a), 0],
        [0, 1, 0, 0],
        [-math.sin(a), 0, math.cos(a), 0],
        [0, 0, 0, 1],
    ])
    yaw, pitch, roll = euler_from_matrix(ry)
    assert yaw == pytest.approx(30.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


def test_non_square_matrix_is_rejected():
    with pytest.raises(ValueError):
        euler_from_matrix(np.eye(3))


# ---------------------------------------------------------------------------
# the browser placement computes the same thing — ../browser/features.test.mjs
# ---------------------------------------------------------------------------

def test_the_golden_fixture_is_what_this_engine_computes():
    """The JS suite asserts the browser port reproduces these expected values;
    this asserts they are still what the server engine produces. Together they
    pin the two placements to each other."""
    import json
    from pathlib import Path
    from types import SimpleNamespace

    golden = json.loads((Path(__file__).resolve().parents[1] / "fixtures"
                         / "landmarks_golden.json").read_text(encoding="utf-8"))
    for i, f in enumerate(golden["frames"]):
        lm = [SimpleNamespace(x=x, y=y) for x, y in f["landmarks"]]
        got = features_from_landmarks(lm, golden["width_px"], golden["height_px"])
        if f["expected"] is None:
            assert got is None, f"frame {i}"
            continue
        assert set(got) == set(f["expected"]), f"frame {i}"
        for ch, v in f["expected"].items():
            assert got[ch] == pytest.approx(v, abs=1e-12), f"frame {i} {ch}"

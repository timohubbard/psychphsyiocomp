"""Tests for HMM fixation classification.

The central claim these have to actually measure, not assert: joint decoding
degrades more gracefully under noise than a per-sample threshold. §4.1 puts
threshold detectors at ~90-92% on static stimuli and ~68-70% under real head
movement at the same 30 Hz, which is the regime a webcam pipeline lives in.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from fixations import (
    FIXATION,
    SACCADE,
    HMMParams,
    angular_velocity,
    classify,
    viterbi,
)

VIEWPORT = (1707.0, 1067.0)
DPP = 0.0236          # measured from a real session: ~42 px/deg
HZ = 30.0


def synth_trace(segments, noise_deg=0.0, seed=0):
    """Build a gaze trace from (duration_ms, x, y) fixation targets.

    Saccades are the transitions between them — one sample wide at 30 Hz, which
    is the realistic case and the one thresholds handle worst.
    """
    rng = np.random.default_rng(seed)
    ts, xs, ys = [], [], []
    t = 0.0
    noise_frac_x = noise_deg / (VIEWPORT[0] * DPP)
    noise_frac_y = noise_deg / (VIEWPORT[1] * DPP)

    for dur, x, y in segments:
        n = max(1, int(dur / (1000.0 / HZ)))
        for _ in range(n):
            ts.append(t)
            xs.append(x + rng.normal(0, noise_frac_x))
            ys.append(y + rng.normal(0, noise_frac_y))
            t += 1000.0 / HZ
    return np.array(ts), np.array(xs), np.array(ys)


TRACE = [(400, 0.2, 0.2), (400, 0.8, 0.2), (400, 0.5, 0.8), (400, 0.2, 0.5)]


# ---------------------------------------------------------------------------
# velocity
# ---------------------------------------------------------------------------

def test_velocity_is_angular_not_pixel():
    """§5.1 measured viewing distance at mean 47.3cm, SD 8.9 across 1,153
    people, so a px/s threshold is not comparable between participants."""
    ts = np.array([0.0, 33.3])
    x = np.array([0.5, 0.5 + 100 / VIEWPORT[0]])   # 100 px right
    y = np.array([0.5, 0.5])

    speed, _ = angular_velocity(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    expected = (100 * DPP) / (33.3 / 1000.0)
    assert speed[0] == pytest.approx(expected, rel=1e-6)


def test_velocity_refuses_without_geometry():
    with pytest.raises(ValueError):
        angular_velocity(np.array([0.0, 33.3]), np.array([0.5, 0.6]),
                         np.array([0.5, 0.5]), viewport_px=VIEWPORT,
                         degrees_per_px=None)


# ---------------------------------------------------------------------------
# transitions scale with sampling rate
# ---------------------------------------------------------------------------

def test_transition_probability_tracks_the_sampling_interval():
    """§2.1 measured 9-39 fps across home setups. A matrix tuned at one rate
    would silently change behaviour at another."""
    p = HMMParams()
    slow = p.transition_matrix(1000.0 / 10)
    fast = p.transition_matrix(1000.0 / 40)
    assert slow[FIXATION, SACCADE] > fast[FIXATION, SACCADE]


def test_transition_rows_stay_probabilities():
    p = HMMParams()
    for dt in (5.0, 33.3, 111.0, 500.0):
        m = p.transition_matrix(dt)
        assert np.allclose(m.sum(axis=1), 1.0)
        assert (m >= 0).all() and (m <= 1).all()


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------

def test_finds_the_fixations_that_were_put_there():
    ts, x, y = synth_trace(TRACE)
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)

    assert r.refusal is None
    assert r.n_fixations == 4, [(e.kind, round(e.duration_ms)) for e in r.events]
    assert r.median_fixation_ms == pytest.approx(400, abs=80)


def test_fixation_centroids_land_on_the_targets():
    ts, x, y = synth_trace(TRACE)
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    fix = [e for e in r.events if e.kind == "fixation"]

    for ev, (_, tx, ty) in zip(fix, TRACE):
        assert ev.x == pytest.approx(tx, abs=0.02)
        assert ev.y == pytest.approx(ty, abs=0.02)


def test_saccade_amplitude_is_the_distance_actually_travelled():
    ts, x, y = synth_trace([(300, 0.2, 0.5), (300, 0.8, 0.5)])
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    sacc = [e for e in r.events if e.kind == "saccade"]

    assert len(sacc) == 1
    expected = 0.6 * VIEWPORT[0] * DPP
    assert sacc[0].amplitude_deg == pytest.approx(expected, rel=0.25)


def test_a_still_eye_produces_one_fixation_and_no_saccades():
    ts, x, y = synth_trace([(1000, 0.5, 0.5)])
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    assert r.n_fixations == 1
    assert r.n_saccades == 0


def test_refuses_without_geometry_rather_than_classifying_in_pixels():
    """Fixation counts that are not comparable across a study are not worth
    having, since comparison is the only use for them."""
    ts, x, y = synth_trace(TRACE)
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=None)
    assert r.refusal == "no_geometry"
    assert r.events == []


def test_refuses_a_trace_too_short_to_have_a_velocity():
    r = classify([0.0], [0.5], [0.5], viewport_px=VIEWPORT, degrees_per_px=DPP)
    assert r.refusal == "too_few_samples"


def test_events_tile_the_trace_without_gaps_or_overlaps():
    """Every sample belongs to exactly one event, or downstream dwell-time
    sums silently disagree with the recording length."""
    ts, x, y = synth_trace(TRACE)
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)

    assert sum(e.n_samples for e in r.events) == len(ts)
    for a, b in zip(r.events, r.events[1:]):
        assert b.onset_ts >= a.offset_ts


# ---------------------------------------------------------------------------
# the reason this is an HMM and not a threshold
# ---------------------------------------------------------------------------

def _threshold_fixation_count(ts, x, y, deg_per_s=30.0):
    """I-VT, for comparison. Classifies each sample independently."""
    speed, _ = angular_velocity(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    labels = (speed > deg_per_s).astype(int)
    return 1 + int(np.sum(np.diff(labels) != 0)) // 2


def test_hmm_is_more_stable_than_a_velocity_threshold_under_noise():
    """The measured claim, not an asserted one.

    A threshold classifies each sample alone, so one noisy sample becomes a
    one-sample saccade and the fixation count inflates without bound as noise
    rises. Joint decoding assigns a sample to the state that best explains it
    given its neighbours, so isolated noise is absorbed.
    """
    truth = len(TRACE)
    hmm_err, ivt_err = [], []

    for seed in range(8):
        ts, x, y = synth_trace(TRACE, noise_deg=1.2, seed=seed)
        hmm_err.append(abs(classify(ts, x, y, viewport_px=VIEWPORT,
                                    degrees_per_px=DPP).n_fixations - truth))
        ivt_err.append(abs(_threshold_fixation_count(ts, x, y) - truth))

    assert np.mean(hmm_err) < np.mean(ivt_err), (
        f"HMM {np.mean(hmm_err):.1f} vs I-VT {np.mean(ivt_err):.1f} mean count error"
    )


def test_a_spike_within_the_sessions_own_noise_does_not_split_a_fixation():
    """The concrete mechanism behind the previous test.

    "Isolated" has to mean isolated RELATIVE TO THIS SESSION. The velocity
    scales are estimated per session, so on a synthetically noiseless trace the
    fixation scale collapses to ~0.001 deg/s and a 1.4 deg excursion genuinely
    is movement — the classifier is right to say so, and a test asserting
    otherwise would be demanding that it ignore real data. On a trace with
    ordinary webcam jitter, the same spike is absorbed.
    """
    for noise_deg in (0.3, 0.6, 1.0):
        ts, x, y = synth_trace([(700, 0.5, 0.5)], noise_deg=noise_deg, seed=3)
        x = x.copy()
        x[10] += 60 / VIEWPORT[0]      # one sample ~1.4 deg away, then back

        r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
        assert r.n_fixations == 1, (
            f"noise {noise_deg} deg: {[(e.kind, e.n_samples) for e in r.events]}")


def test_a_one_sample_saccade_still_reports_its_amplitude():
    """At webcam rates most saccades occupy a single sample, and displacement
    within one sample is zero by definition — so measuring across the saccade's
    own samples reported every fast saccade as having no amplitude."""
    ts, x, y = synth_trace([(300, 0.2, 0.5), (300, 0.8, 0.5)])
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    sacc = [e for e in r.events if e.kind == "saccade"]

    assert sacc and sacc[0].n_samples == 1, "expected the one-sample case"
    assert sacc[0].amplitude_deg > 1.0


def test_a_sustained_move_is_still_detected_as_a_saccade():
    """Robustness must not become deafness: the model has to keep hearing real
    saccades, or it would trivially pass the noise test by never firing."""
    ts, x, y = synth_trace([(400, 0.15, 0.5), (400, 0.85, 0.5)])
    r = classify(ts, x, y, viewport_px=VIEWPORT, degrees_per_px=DPP)
    assert r.n_saccades >= 1


# ---------------------------------------------------------------------------
# viterbi itself
# ---------------------------------------------------------------------------

def test_viterbi_labels_clear_velocities_correctly():
    speed = np.array([2.0, 2.0, 2.0, 200.0, 2.0, 2.0, 2.0])
    dt = np.full(len(speed), 1000.0 / HZ)
    states = viterbi(speed, dt, HMMParams())
    assert states[0] == FIXATION and states[-1] == FIXATION
    assert states[3] == SACCADE


def test_viterbi_on_an_empty_sequence_returns_empty():
    assert len(viterbi(np.empty(0), np.empty(0), HMMParams())) == 0


def test_zero_velocity_does_not_produce_negative_infinity():
    """A genuinely stationary sample has zero measured speed, and log(0) would
    make both states impossible and let the prior decide alone."""
    speed = np.zeros(6)
    dt = np.full(6, 1000.0 / HZ)
    states = viterbi(speed, dt, HMMParams())
    assert set(states) <= {FIXATION, SACCADE}
    assert (states == FIXATION).all()

"""Tests for the respiration signal-processing core.

The central claims these have to measure rather than assert: that keeping motion
profiles separate beats averaging them up front (§2.4's one surviving
algorithmic finding), and that the pipeline refuses to produce a breathing rate
it cannot defend.
"""

from __future__ import annotations

import numpy as np
import pytest

from respiration import (
    GRID,
    MIN_PERIODICITY,
    RESP_BAND_HZ,
    WAVEFORM_RATE_HZ,
    assess_confidence,
    bandpass,
    estimate_rate,
    fuse_profiles,
    periodicity_index,
    resample,
)

FPS = 30.0


def breathing(bpm=15.0, seconds=30.0, fps=FPS, phase=0.0, amp=1.0):
    t = np.arange(int(seconds * fps)) / fps
    return amp * np.sin(2 * np.pi * (bpm / 60.0) * t + phase)


# ---------------------------------------------------------------------------
# the band
# ---------------------------------------------------------------------------

def test_the_band_matches_the_one_imotions_uses():
    """§2.4 describes chest-motion tracking band-passed to ~7.5-30 cycles/min."""
    lo_cpm, hi_cpm = RESP_BAND_HZ[0] * 60, RESP_BAND_HZ[1] * 60
    assert lo_cpm == pytest.approx(7.5)
    assert hi_cpm == pytest.approx(30.0)


def test_a_breathing_rhythm_survives_the_filter():
    x = breathing(bpm=15)
    out = bandpass(x, FPS)
    assert np.corrcoef(out, x)[0, 1] > 0.95


def test_a_slow_postural_drift_is_removed():
    """Someone slowly leaning forward puts a ramp under the signal, and a ramp
    has energy at every frequency including inside the band."""
    t = np.arange(int(30 * FPS)) / FPS
    drift = 5.0 * t / t.max()
    out = bandpass(drift, FPS)
    assert np.std(out) < 0.05 * np.std(drift)


def test_a_head_nod_above_the_band_is_removed():
    fast = breathing(bpm=120)          # 2 Hz, well above 0.5
    assert np.std(bandpass(fast, FPS)) < 0.1 * np.std(fast)


def test_the_filter_is_zero_phase():
    """A causal filter delays by a frequency-dependent amount, which would move
    every inhale onset relative to the stimulus that supposedly caused it —
    consistently, and invisibly."""
    x = breathing(bpm=15, seconds=40)
    out = bandpass(x, FPS)

    lags = range(-15, 16)
    best = max(lags, key=lambda k: np.corrcoef(x, np.roll(out, k))[0, 1])
    assert best == 0, f"peak correlation at lag {best}, not zero"


def test_a_short_input_returns_zeros_rather_than_raising():
    assert np.allclose(bandpass(np.array([1.0, 2.0]), FPS), 0.0)


# ---------------------------------------------------------------------------
# periodicity
# ---------------------------------------------------------------------------

def test_a_breathing_cell_scores_far_above_a_static_one():
    rng = np.random.default_rng(0)
    assert periodicity_index(breathing(), FPS) > 0.8
    assert periodicity_index(rng.normal(0, 1, 900), FPS) < 0.2


def test_a_broadband_gesture_does_not_look_periodic():
    """An arm moving through frame is large in amplitude and unlike breathing."""
    rng = np.random.default_rng(1)
    burst = np.zeros(900)
    burst[400:460] = rng.normal(0, 5, 60)
    assert periodicity_index(burst, FPS) < MIN_PERIODICITY


def test_periodicity_ignores_a_linear_trend():
    t = np.arange(900) / FPS
    assert periodicity_index(breathing() + 3 * t, FPS) > 0.7


# ---------------------------------------------------------------------------
# fusion — §2.4's one surviving algorithmic finding
# ---------------------------------------------------------------------------

def test_multiple_profiles_beat_a_single_combined_profile():
    """The finding this whole design rests on.

    §2.4: of six chest/abdomen motion-extraction combinations, those using
    MULTIPLE 1D or 2D motion profiles outperform single-combined-1D-profile
    approaches. Averaging the grid up front is the obvious implementation and
    the specific thing the evidence says not to do — here it is measured rather
    than asserted.

    The grid is realistic: a few cells carry the breath, most carry noise, and
    one carries a strong artefact.
    """
    rng = np.random.default_rng(2)
    truth = breathing(bpm=15, seconds=40)
    n = len(truth)

    cells = []
    for i in range(16):
        if i in (5, 6, 9):                       # chest cells
            cells.append(truth * 1.0 + rng.normal(0, 0.4, n))
        elif i == 1:                             # a bright artefact
            cells.append(rng.normal(0, 4.0, n))
        else:                                    # background
            cells.append(rng.normal(0, 0.8, n))
    cells = np.vstack(cells)

    fused = fuse_profiles(cells, FPS)
    naive = bandpass(cells.mean(axis=0), FPS)    # the single combined profile
    reference = bandpass(truth, FPS)

    r_fused = abs(np.corrcoef(fused.waveform, reference)[0, 1])
    r_naive = abs(np.corrcoef(naive, reference)[0, 1])

    assert r_fused > r_naive, f"fused {r_fused:.3f} did not beat naive {r_naive:.3f}"
    assert r_fused > 0.8


def test_out_of_phase_cells_add_instead_of_cancelling():
    """Chest rise and shoulder rotation are not in phase. A cell moving down
    while another moves up will cancel it, and that — not noise — is the actual
    reason naive averaging loses the signal."""
    up = breathing(bpm=15, seconds=40)
    down = breathing(bpm=15, seconds=40, phase=np.pi)

    fused = fuse_profiles(np.vstack([up, down]), FPS)
    naive = bandpass((up + down) / 2, FPS)

    assert np.std(fused.waveform) > 0.5
    assert np.std(naive) < 0.01, "the two cells should cancel when naively averaged"


def test_only_periodic_cells_contribute():
    rng = np.random.default_rng(3)
    truth = breathing(seconds=40)
    cells = np.vstack([truth] + [rng.normal(0, 1, len(truth)) for _ in range(6)])

    fused = fuse_profiles(cells, FPS, top_k=4)
    assert 0 in fused.cells_used
    assert len(fused.cells_used) <= 4


def test_a_grid_with_no_breathing_refuses_rather_than_returning_noise():
    rng = np.random.default_rng(4)
    cells = rng.normal(0, 1, (16, 900))
    fused = fuse_profiles(cells, FPS)

    assert fused.refusal == "no_periodic_cells"
    assert np.allclose(fused.waveform, 0.0)


def test_the_grid_is_declared_and_more_than_one_cell():
    assert GRID[0] * GRID[1] > 1


# ---------------------------------------------------------------------------
# rate — and its refusal
# ---------------------------------------------------------------------------

def test_a_clean_waveform_yields_the_rate_that_was_put_in():
    r = estimate_rate(bandpass(breathing(bpm=15, seconds=60), FPS), FPS)
    assert r.confident is True
    assert r.bpm == pytest.approx(15, abs=1.5)


def test_the_two_estimators_must_agree_or_no_number_is_returned():
    """The FFT peak and inter-breath timing fail differently: a spectral peak
    survives missed breaths but is pulled by any in-band artefact, while
    inter-peak timing tracks individual breaths but is wrecked by one spurious
    peak. §2.4 is unambiguous that no bpm figure from this class of method
    survived adversarial checking, so disagreement is an expected outcome and
    should look like one."""
    rng = np.random.default_rng(5)
    # Two breathing rates superimposed: the spectrum picks one, the crossings
    # see something else.
    messy = breathing(bpm=10, seconds=60) + breathing(bpm=22, seconds=60) \
        + rng.normal(0, 0.3, int(60 * FPS))

    r = estimate_rate(bandpass(messy, FPS), FPS)
    if not r.confident:
        assert r.bpm is None
        assert "disagree" in r.reason
    else:
        # If they happen to agree, they must agree for a real reason.
        assert r.agreement <= 2.0


def test_too_few_breaths_is_refused():
    r = estimate_rate(bandpass(breathing(bpm=15, seconds=6), FPS), FPS)
    assert r.confident is False
    assert r.bpm is None


def test_a_flat_waveform_is_refused():
    r = estimate_rate(np.zeros(600), FPS)
    assert r.confident is False
    assert r.bpm is None


# ---------------------------------------------------------------------------
# confidence is non-negotiable
# ---------------------------------------------------------------------------

def _good_fusion():
    return fuse_profiles(np.vstack([breathing(seconds=40)] * 3), FPS)


def test_a_good_segment_is_usable():
    c = assess_confidence(_good_fusion(), effective_fps=30.0,
                          roi_luminance=120.0, gross_motion=0.5)
    assert c.usable is True
    assert c.reasons == []


def test_gross_motion_makes_a_segment_unusable():
    c = assess_confidence(_good_fusion(), effective_fps=30.0,
                          roi_luminance=120.0, gross_motion=9.0)
    assert c.usable is False
    assert c.motion_artifact is True


def test_a_frame_rate_too_low_for_the_band_is_refused():
    c = assess_confidence(_good_fusion(), effective_fps=1.5,
                          roi_luminance=120.0, gross_motion=0.5)
    assert c.usable is False
    assert any("fps" in r for r in c.reasons)


def test_the_luminance_fairness_floor_applies_here_too():
    """§2.5's floor is about who the measurement works for, and this is another
    camera-based physiological measurement."""
    c = assess_confidence(_good_fusion(), effective_fps=30.0,
                          roi_luminance=14.0, gross_motion=0.5)
    assert c.usable is False
    assert any("luminance" in r for r in c.reasons)


def test_every_failure_is_named():
    c = assess_confidence(_good_fusion(), effective_fps=1.0,
                          roi_luminance=5.0, gross_motion=99.0)
    assert len(c.reasons) >= 3


# ---------------------------------------------------------------------------
# output grid
# ---------------------------------------------------------------------------

def test_resampling_preserves_the_rhythm():
    x = bandpass(breathing(bpm=15, seconds=60), FPS)
    out, dt_ms = resample(x, FPS)

    assert dt_ms == pytest.approx(1000.0 / WAVEFORM_RATE_HZ)
    r = estimate_rate(out, WAVEFORM_RATE_HZ)
    assert r.bpm == pytest.approx(15, abs=1.5)


def test_the_output_rate_is_well_above_the_band():
    """So inhale-onset timing is not quantised by the output grid."""
    assert WAVEFORM_RATE_HZ > RESP_BAND_HZ[1] * 20

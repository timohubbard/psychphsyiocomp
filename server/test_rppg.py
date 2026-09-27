"""The rPPG maths, held to pulses planted in synthetic skin-colour traces.

The pulse is planted the way blood volume changes skin colour — a small
modulation strongest in green (relative strengths 0.33 : 0.77 : 0.53 in
R : G : B, the pulsatile vector POS is built on) — on top of the things that
defeat naive methods: slow lighting drift, a lighting flicker at a
heart-rate-like frequency, sensor noise, and irregular frame times.
"""

from __future__ import annotations

import numpy as np
import pytest

from rppg import analyse, heart_rate_windows, pos, spectrum_peak, uniform

SKIN = np.array([180.0, 140.0, 120.0])       # R, G, B
PULSE = np.array([0.33, 0.77, 0.53])


def trace(bpm=72.0, seconds=60.0, fps=30.0, *, amp=0.004, noise=0.25, flicker_hz=None,
          flicker=0.0, jitter_ms=0.0, luma=120.0, seed=0):
    rng = np.random.default_rng(seed)
    ts = np.arange(0, seconds * 1000, 1000 / fps)
    if jitter_ms:
        ts = np.sort(ts + rng.uniform(-jitter_ms, jitter_ms, len(ts)))
    t = ts / 1000
    light = 1 + 0.05 * np.sin(2 * np.pi * 0.05 * t)                 # slow drift, all channels
    if flicker_hz:
        light *= 1 + flicker * np.sin(2 * np.pi * flicker_hz * t)   # common-mode flicker
    pulse = 1 + amp * np.outer(np.sin(2 * np.pi * (bpm / 60) * t), PULSE)
    rgb = SKIN * light[:, None] * pulse + rng.normal(0, noise, (len(t), 3))
    return ts, rgb, np.full(len(t), luma)


def rates(ts, rgb, luma, **kw):
    _, windows = analyse(ts, rgb, luma, **kw)
    return windows


def test_a_planted_pulse_is_recovered_in_every_window():
    w = rates(*trace(72))
    assert len(w) >= 20
    assert all(x.passed for x in w), [x.reason for x in w if not x.passed]
    assert all(abs(x.hr_bpm - 72) <= 2 for x in w), [round(x.hr_bpm, 1) for x in w]


@pytest.mark.parametrize("bpm", [50, 90, 130])
def test_across_the_range_of_resting_and_raised_rates(bpm):
    w = rates(*trace(bpm, seed=bpm))
    assert np.median([x.hr_bpm for x in w if x.passed]) == pytest.approx(bpm, abs=2)


def test_a_lighting_flicker_at_a_heart_like_rate_is_not_read_as_the_pulse():
    """Common-mode: equal in R, G and B. POS projects it out; a green-channel
    method would report 90 bpm here."""
    w = rates(*trace(72, flicker_hz=1.5, flicker=0.02))
    assert np.median([x.hr_bpm for x in w if x.passed]) == pytest.approx(72, abs=2)
    g = trace(72, flicker_hz=1.5, flicker=0.02)[1][:, 1]
    f0, _ = spectrum_peak(g - g.mean(), 30.0)
    assert f0 * 60 == pytest.approx(90, abs=3)          # …which is what green alone would say


def test_noise_alone_is_refused_rather_than_given_a_rate():
    ts, rgb, luma = trace(72, amp=0.0, noise=1.0)
    w = rates(ts, rgb, luma)
    assert np.mean([x.passed for x in w]) <= 0.1
    assert {x.reason for x in w if not x.passed} == {"low_snr"}


def test_a_dark_skin_region_is_refused():
    """§2.5: the skin-tone error gap closes at luminance >= 30; below it, no rate."""
    w = rates(*trace(72, luma=22))
    assert not any(x.passed for x in w)
    assert {x.reason for x in w} == {"too_dark"}


def test_irregular_frame_times_are_resampled_not_trusted():
    w = rates(*trace(72, fps=24, jitter_ms=12))
    assert np.median([x.hr_bpm for x in w if x.passed]) == pytest.approx(72, abs=2)


def test_a_gap_splits_the_trace_rather_than_being_interpolated_across():
    ts, rgb, luma = trace(72)
    keep = (ts < 20000) | (ts > 21000)
    segs = uniform(ts[keep], rgb[keep])
    assert len(segs) == 2
    assert segs[0][0][-1] < 20000 and segs[1][0][0] > 21000


def test_pos_ignores_the_skin_tone_itself():
    """Normalising each window by its own mean: the same pulse on darker skin
    (lower levels, same relative modulation) gives the same waveform shape."""
    ts, rgb, _ = trace(72, noise=0.0)
    a = pos(rgb)
    b = pos(rgb * 0.4)
    assert np.corrcoef(a[60:-60], b[60:-60])[0, 1] > 0.999


def test_snr_separates_a_pulse_from_noise():
    rng = np.random.default_rng(3)
    t = np.arange(300) / 30
    _, clean = spectrum_peak(np.sin(2 * np.pi * 1.2 * t) + 0.2 * rng.normal(size=300))
    _, noise = spectrum_peak(rng.normal(size=300))
    assert clean > 5 and noise < 0

"""Tests for clock alignment.

The load-bearing behaviour here is the refusal: when there is no evidence
linking a clock to the master, master_ts must be NULL and the reason recorded.
A zero-offset guess would look aligned and be wrong by an unknown amount, which
is strictly worse than a visible NULL.
"""

from __future__ import annotations

import math

import pytest

from alignment import (
    MIN_UNCERTAINTY_MS,
    SINGLE_ANCHOR_UNCERTAINTY_MS,
    AlignmentError,
    Anchor,
    ClockRegistry,
    detect_clapper_in_luma,
)

MASTER = "performance.now"
VIDEO = "video_pts"


def _registry() -> ClockRegistry:
    return ClockRegistry(master_clock_id=MASTER)


# ---------------------------------------------------------------------------
# refusing to align
# ---------------------------------------------------------------------------

def test_unanchored_clock_is_refused_not_guessed():
    reg = _registry()
    reg.register_clock(VIDEO)
    sol = reg.solve(VIDEO)

    assert not sol.aligned
    assert sol.unaligned_reason is not None
    assert VIDEO in sol.unaligned_reason
    assert "NULL" in sol.unaligned_reason


def test_unaligned_solution_yields_null_timestamps():
    """to_master must return (None, None) — never (native_ts, something)."""
    reg = _registry()
    sol = reg.solve(VIDEO)
    master_ts, unc = sol.to_master(1234.5)
    assert master_ts is None
    assert unc is None


def test_master_clock_maps_to_itself_exactly():
    sol = _registry().solve(MASTER)
    assert sol.aligned
    assert sol.offset_ms == 0.0
    assert sol.rate == 1.0
    assert sol.uncertainty_ms == 0.0
    ts, unc = sol.to_master(999.0)
    assert ts == 999.0 and unc == 0.0


# ---------------------------------------------------------------------------
# single anchor: offset only
# ---------------------------------------------------------------------------

def test_single_anchor_recovers_offset():
    reg = _registry()
    # Video PTS 0 coincided with performance.now 5000 -> offset +5000
    reg.add_anchor(Anchor(VIDEO, 0.0, MASTER, 5000.0, uncertainty_ms=33.0, label="clapper"))
    sol = reg.solve(VIDEO)

    assert sol.aligned
    assert sol.n_anchors == 1
    assert abs(sol.offset_ms - 5000.0) < 1e-6
    assert sol.rate == 1.0, "drift is not estimable from one anchor"

    ts, unc = sol.to_master(1000.0)
    assert abs(ts - 6000.0) < 1e-6
    assert unc >= 33.0


def test_single_anchor_uncertainty_is_not_optimistic():
    """One anchor cannot justify a sub-10ms claim.

    §3.3: browser display timing alone varies ~11.5ms (Chrome) to ~30ms
    (Safari), so reporting the anchor's own precision would overstate it.
    """
    reg = _registry()
    reg.add_anchor(Anchor(VIDEO, 0.0, MASTER, 100.0, uncertainty_ms=0.001))
    sol = reg.solve(VIDEO)
    assert sol.uncertainty_ms >= SINGLE_ANCHOR_UNCERTAINTY_MS


def test_anchor_direction_does_not_matter():
    """Callers should not have to remember which clock goes first."""
    forward = _registry()
    forward.add_anchor(Anchor(VIDEO, 0.0, MASTER, 5000.0, uncertainty_ms=33.0))

    reversed_ = _registry()
    reversed_.add_anchor(Anchor(MASTER, 5000.0, VIDEO, 0.0, uncertainty_ms=33.0))

    assert abs(forward.solve(VIDEO).offset_ms - reversed_.solve(VIDEO).offset_ms) < 1e-6


# ---------------------------------------------------------------------------
# multiple anchors: offset + drift
# ---------------------------------------------------------------------------

def test_two_anchors_recover_clock_drift():
    """Consumer clocks differ by tens of ppm; a long session accumulates skew."""
    reg = _registry()
    true_rate, true_offset = 1.0002, 5000.0  # 200 ppm fast
    for native in (0.0, 600_000.0):  # 10 minutes apart
        reg.add_anchor(
            Anchor(VIDEO, native, MASTER, native * true_rate + true_offset,
                   uncertainty_ms=10.0)
        )
    sol = reg.solve(VIDEO)

    assert sol.n_anchors == 2
    assert abs(sol.rate - true_rate) < 1e-6
    assert abs(sol.offset_ms - true_offset) < 1e-3

    # Extrapolating past the last anchor must still track the true mapping.
    ts, _ = sol.to_master(900_000.0)
    assert abs(ts - (900_000.0 * true_rate + true_offset)) < 1e-3


def test_disagreeing_anchors_widen_the_error_bar():
    """Residual spread IS the uncertainty, whatever each anchor claimed.

    If the observations disagree with the fitted line, reporting the best
    individual anchor's precision would be a lie about the fit.
    """
    reg = _registry()
    # Three anchors that cannot lie on one line; each claims to be precise.
    reg.add_anchor(Anchor(VIDEO, 0.0, MASTER, 1000.0, uncertainty_ms=1.0))
    reg.add_anchor(Anchor(VIDEO, 1000.0, MASTER, 2100.0, uncertainty_ms=1.0))
    reg.add_anchor(Anchor(VIDEO, 2000.0, MASTER, 2950.0, uncertainty_ms=1.0))
    sol = reg.solve(VIDEO)

    assert sol.aligned
    assert sol.uncertainty_ms > 10.0, (
        f"inconsistent anchors should widen uncertainty, got {sol.uncertainty_ms}"
    )


def test_consistent_anchors_keep_uncertainty_tight_but_floored():
    reg = _registry()
    for native in (0.0, 1000.0, 2000.0, 3000.0):
        reg.add_anchor(Anchor(VIDEO, native, MASTER, native + 500.0, uncertainty_ms=2.0))
    sol = reg.solve(VIDEO)

    assert abs(sol.rate - 1.0) < 1e-9
    assert abs(sol.offset_ms - 500.0) < 1e-9
    # Perfect residuals, but never claim better than the platform floor.
    assert sol.uncertainty_ms >= MIN_UNCERTAINTY_MS


def test_degenerate_anchors_at_one_timestamp_fall_back_to_offset():
    """Two observations at the same native time cannot determine drift."""
    reg = _registry()
    reg.add_anchor(Anchor(VIDEO, 100.0, MASTER, 600.0, uncertainty_ms=5.0))
    reg.add_anchor(Anchor(VIDEO, 100.0, MASTER, 620.0, uncertainty_ms=5.0))
    sol = reg.solve(VIDEO)

    assert sol.aligned
    assert sol.rate == 1.0, "must not invent a drift estimate from zero spread"
    assert math.isfinite(sol.offset_ms)


def test_negative_uncertainty_is_a_programming_error():
    with pytest.raises(AlignmentError):
        _registry().add_anchor(Anchor(VIDEO, 0.0, MASTER, 0.0, uncertainty_ms=-1.0))


def test_solve_all_covers_every_registered_clock():
    reg = _registry()
    reg.register_clock(VIDEO)
    reg.register_clock("audiocontext")
    reg.add_anchor(Anchor(VIDEO, 0.0, MASTER, 100.0, uncertainty_ms=20.0))

    sols = reg.solve_all()
    assert set(sols) == {MASTER, VIDEO, "audiocontext"}
    assert sols[VIDEO].aligned
    # AudioContext has its own clock and no anchor — §3.3's exact trap.
    assert not sols["audiocontext"].aligned


# ---------------------------------------------------------------------------
# clapper detection
# ---------------------------------------------------------------------------

def _flat_luma(n=60, value=100.0, start=0.0, step=33.3):
    return [(start + i * step, value) for i in range(n)]


def test_clapper_found_in_a_clear_flash():
    series = _flat_luma()
    series[30] = (series[30][0], 240.0)  # the flash
    found = detect_clapper_in_luma(series)

    assert found is not None
    ts, unc = found
    assert abs(ts - series[30][0]) < 1e-6
    assert unc >= MIN_UNCERTAINTY_MS


def test_no_clapper_in_flat_luminance_returns_none():
    """A real outcome, not a failure — the caller must then leave it unaligned."""
    assert detect_clapper_in_luma(_flat_luma()) is None


def test_clapper_uncertainty_matches_the_frame_interval():
    """We cannot localise a flash more precisely than the sampling grid."""
    series = _flat_luma(step=33.3)
    series[20] = (series[20][0], 250.0)
    _, unc = detect_clapper_in_luma(series)
    assert 30.0 < unc < 40.0, f"expected ~one frame at 30fps, got {unc}"


def test_gentle_drift_is_not_mistaken_for_a_flash():
    """Someone adjusting a lamp mid-session must not read as a sync marker."""
    series = [(i * 33.3, 100.0 + i * 0.5) for i in range(60)]
    assert detect_clapper_in_luma(series, z_threshold=4.0) is None


def test_too_few_samples_returns_none():
    assert detect_clapper_in_luma([(0.0, 100.0), (33.0, 250.0)]) is None


def test_noise_alone_does_not_trigger_detection():
    import random
    rng = random.Random(0)
    series = [(i * 33.3, 100.0 + rng.gauss(0, 3)) for i in range(120)]
    assert detect_clapper_in_luma(series, z_threshold=4.0) is None

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
    detect_clappers_in_luma,
    match_clappers,
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


def _with_flash(series, at, rise, span=6):
    """Insert a realistic clapper: a sharp-edged plateau of `span` frames.

    A real 200ms flash at 30fps is SIX frames, not one. These tests previously
    modelled it as a single frame jumping from 100 to 240 — a contrast no real
    room produces, since a camera already exposed for a lit room has little
    headroom left when the screen turns white. That fiction let the detector be
    tuned to require a 15-luma rise, and the first real capture's flash (+8.5
    luma, a clean 7-frame plateau) was rejected — leaving every server-side row
    with a NULL master_ts and the session unalignable.
    """
    out = list(series)
    for k in range(at, min(len(out), at + span)):
        out[k] = (out[k][0], out[k][1] + rise)
    return out


# ---------------------------------------------------------------------------
# the shape of a real flash
# ---------------------------------------------------------------------------

def test_clapper_found_in_a_realistic_flash():
    """+8 luma on a bright baseline — the magnitude actually observed."""
    series = _with_flash(_flat_luma(value=185.0), at=30, rise=8.0)
    found = detect_clapper_in_luma(series)

    assert found is not None, "a real-magnitude flash must be detectable"
    ts, unc = found
    assert abs(ts - series[30][0]) < 1e-6, "must report the first bright frame"
    assert unc >= MIN_UNCERTAINTY_MS


def test_clapper_still_found_when_it_is_dramatic():
    """The easy case must not regress while fixing the hard one."""
    series = _with_flash(_flat_luma(value=100.0), at=30, rise=140.0)
    found = detect_clapper_in_luma(series)
    assert found is not None
    assert abs(found[0] - series[30][0]) < 1e-6


def test_detector_reports_flash_onset_not_plateau_middle():
    """The anchor is the instant the screen turned white."""
    series = _with_flash(_flat_luma(value=185.0), at=25, rise=9.0, span=8)
    ts, _ = detect_clapper_in_luma(series)
    assert abs(ts - series[25][0]) < 1e-6


# ---------------------------------------------------------------------------
# what must NOT be mistaken for a flash
# ---------------------------------------------------------------------------

def test_no_clapper_in_flat_luminance_returns_none():
    """A real outcome, not a failure — the caller must then leave it unaligned."""
    assert detect_clapper_in_luma(_flat_luma()) is None


def test_gentle_drift_is_not_mistaken_for_a_flash():
    """Someone adjusting a lamp mid-session must not read as a sync marker."""
    series = [(i * 33.3, 100.0 + i * 0.5) for i in range(60)]
    assert detect_clapper_in_luma(series) is None


def test_slow_bump_of_flash_magnitude_is_rejected():
    """The exact false positive found in the first real capture.

    Auto-exposure settling produced a +4 luma rise over ~13 frames that decayed
    again — a genuine pulse of comparable size to the flash, and it scored just
    as high until edge sharpness was required. A screen turning white cannot
    take a dozen frames to do it.
    """
    series = _flat_luma(n=120, value=185.0)
    for k in range(40, 53):          # gradual rise
        series[k] = (series[k][0], 185.0 + 4.0 * (k - 40) / 12)
    for k in range(53, 71):          # gradual decay
        series[k] = (series[k][0], 189.0 - 4.0 * (k - 53) / 17)
    assert detect_clapper_in_luma(series) is None


def test_too_few_samples_returns_none():
    assert detect_clapper_in_luma([(0.0, 100.0), (33.0, 250.0)]) is None


def test_noise_alone_does_not_trigger_detection():
    import random
    rng = random.Random(0)
    series = [(i * 33.3, 100.0 + rng.gauss(0, 3)) for i in range(120)]
    assert detect_clapper_in_luma(series) is None


def test_step_change_that_never_returns_is_not_a_flash():
    """A stimulus background going from dark to light is a new steady state."""
    series = [(i * 33.3, 100.0 if i < 40 else 130.0) for i in range(120)]
    assert detect_clapper_in_luma(series) is None


# ---------------------------------------------------------------------------
# uncertainty and multiplicity
# ---------------------------------------------------------------------------

def test_clapper_uncertainty_matches_the_frame_interval():
    """We cannot localise a flash more precisely than the sampling grid."""
    series = _with_flash(_flat_luma(step=33.3, value=185.0), at=20, rise=9.0)
    _, unc = detect_clapper_in_luma(series)
    assert 30.0 < unc < 40.0, f"expected ~one frame at 30fps, got {unc}"


def test_both_bookend_clappers_are_found():
    """Two anchors are what let the aligner fit a RATE, not just an offset.

    Consumer clocks routinely differ by tens of ppm, which accumulates to real
    skew across a long session — so finding only the first flash silently
    reduces the alignment to an offset.
    """
    series = _flat_luma(n=300, value=185.0)
    series = _with_flash(series, at=30, rise=9.0)
    series = _with_flash(series, at=240, rise=7.0)

    found = detect_clappers_in_luma(series)
    assert len(found) == 2, f"expected both bookends, got {len(found)}"

    onsets = sorted(f[0] for f in found)
    assert abs(onsets[0] - series[30][0]) < 1e-6
    assert abs(onsets[1] - series[240][0]) < 1e-6


def test_one_flash_yields_one_detection_not_a_run():
    """Overlapping matched-filter windows are the same event, not several."""
    series = _with_flash(_flat_luma(n=120, value=185.0), at=50, rise=9.0, span=7)
    assert len(detect_clappers_in_luma(series)) == 1


# ---------------------------------------------------------------------------
# pairing drawn flashes with detected ones
# ---------------------------------------------------------------------------
# Real M0 pilot: recording_start 11849 ms, clappers drawn at 125435 and
# 241726, and the video flash landed 29 ms after its expected position.

REC, E1, E2 = 11849.0, 125435.0, 241726.0


def _cand(video_ts, score=10.0):
    return (video_ts, 33.0, score)


def test_both_clappers_are_matched_and_both_become_anchors():
    """The second clapper used to be ignored, so the rate fit two bookend
    clappers exist for never happened."""
    matched, why = match_clappers([E1, E2], REC,
                                  [_cand(E1 - REC + 29), _cand(E2 - REC + 31)])
    assert why is None
    assert [m[1] for m in matched] == [E1, E2]


def test_a_brighter_closing_flash_is_not_paired_with_the_opening_event():
    """The old rule took the strongest detection and paired it with the FIRST
    clapper. A brighter closing flash shifted every video row by the whole
    session, reported as aligned."""
    matched, why = match_clappers([E1, E2], REC,
                                  [_cand(E2 - REC + 30, score=50.0),
                                   _cand(E1 - REC + 30, score=9.0)])
    assert why is None
    for video_ts, master_ts, _ in matched:
        assert abs((master_ts - REC) - video_ts) < 100


def test_a_flash_nowhere_near_where_one_was_drawn_is_refused():
    """Measured: on a fake-camera session the strongest 'flash' sat 92 s from
    any drawn flash and was accepted as an anchor."""
    matched, why = match_clappers([11635.0, 250616.0], 778.0, [_cand(102697.0)])
    assert matched == []
    assert "92" in why or "91" in why


def test_one_flash_found_of_two_still_anchors_the_offset():
    matched, why = match_clappers([E1, E2], REC, [_cand(E1 - REC + 29)])
    assert why is None and len(matched) == 1


def test_matched_flashes_with_the_wrong_spacing_are_refused():
    matched, why = match_clappers([E1, E2], REC,
                                  [_cand(E1 - REC + 29), _cand(E2 - REC + 900)])
    assert matched == []
    assert "inconsistent" in why


def test_without_recording_start_a_lone_flash_for_a_lone_event_is_accepted():
    """Older bundles: the unambiguous case still aligns."""
    matched, why = match_clappers([1000.0], None, [_cand(400.0)])
    assert why is None and matched == [(400.0, 1000.0, 33.0)]


def test_without_recording_start_a_pair_is_accepted_only_on_matching_spacing():
    good, why = match_clappers([E1, E2], None,
                               [_cand(5000.0), _cand(5000.0 + (E2 - E1) + 20), _cand(9000.0)])
    assert why is None and [m[0] for m in good] == [5000.0, 5000.0 + (E2 - E1) + 20]
    bad, why = match_clappers([E1, E2], None, [_cand(5000.0), _cand(9000.0)])
    assert bad == [] and "ambiguous" in why


def test_a_refusal_reason_reaches_the_unaligned_stream():
    reg = ClockRegistry(master_clock_id="m")
    reg.refuse("video_pts", "flash not where drawn")
    sol = reg.solve("video_pts")
    assert not sol.aligned
    assert "flash not where drawn" in sol.unaligned_reason

"""Tests for inter-engine agreement and within-participant relative proportions."""

from __future__ import annotations

import numpy as np
import pytest

from agreement import (
    PUBLISHED_INTER_ENGINE_R,
    comparison_kind,
    agreement_for_channel,
    channel_agreement,
    condition_contrast,
    relative_proportion,
    summarise,
)

A = "face.enginea@0.1.0+server-batch"
B = "face.engineb@0.1.0+server-batch"


def rows(channel: str, source: str, ts, values):
    return [{"channel": channel, "source": source, "master_ts": float(t),
             "value": float(v)} for t, v in zip(ts, values)]


# ---------------------------------------------------------------------------
# the single-source verdict
# ---------------------------------------------------------------------------

def test_one_engine_gives_an_explicit_verdict_not_an_empty_result():
    """§2.2's whole warning is that a single engine's output looks exactly as
    confident as a corroborated one. An empty result reads as "nothing to
    report"; "no disagreement measured" and "no disagreement" are different
    claims, and only one of them is true.
    """
    r = agreement_for_channel(rows("au.AU12", A, range(50), np.random.rand(50)), "au.AU12")
    assert len(r) == 1
    assert r[0].verdict == "single_source"
    assert r[0].r is None


def test_the_single_source_message_names_the_published_spread():
    """A reader needs to know what magnitude of disagreement is normal."""
    r = agreement_for_channel(rows("au.AU12", A, range(50), np.random.rand(50)), "au.AU12")[0]
    assert "0.37" in r.detail and "0.75" in r.detail


def test_a_channel_with_no_rows_is_still_a_verdict():
    assert agreement_for_channel([], "au.AU12")[0].verdict == "single_source"


# ---------------------------------------------------------------------------
# agreement between two sources
# ---------------------------------------------------------------------------

def test_identical_series_agree_perfectly():
    ts = np.arange(100) * 33.0
    v = np.sin(ts / 300.0)
    data = rows("au.AU12", A, ts, v) + rows("au.AU12", B, ts, v)

    a = channel_agreement(data, "au.AU12", A, B)
    assert a.verdict == "ok"
    assert a.r == pytest.approx(1.0, abs=1e-9)


def test_a_noisy_second_engine_lowers_the_correlation():
    rng = np.random.default_rng(0)
    ts = np.arange(200) * 33.0
    v = np.sin(ts / 300.0)
    data = (rows("au.AU12", A, ts, v)
            + rows("au.AU12", B, ts, v + rng.normal(0, 0.8, len(v))))

    a = channel_agreement(data, "au.AU12", A, B)
    assert a.verdict == "ok"
    assert 0.0 < a.r < 0.9


def test_sources_sampled_at_different_rates_are_still_comparable():
    """The engines run at different strides by design — AU inference at 2 Hz
    against blendshapes at 30 Hz — so this is the ordinary case, not an edge."""
    ts_fast = np.arange(300) * 11.0
    ts_slow = np.arange(50) * 66.0
    f = lambda t: np.sin(t / 400.0)  # noqa: E731

    data = rows("au.AU12", A, ts_fast, f(ts_fast)) + rows("au.AU12", B, ts_slow, f(ts_slow))
    a = channel_agreement(data, "au.AU12", A, B)

    assert a.verdict == "ok"
    assert a.r > 0.99
    # Resampled onto the SPARSER grid, so the overlap cannot exceed it.
    assert a.n_overlapping <= len(ts_slow)


def test_a_constant_channel_is_degenerate_not_zero_correlation():
    """AU20 does exactly this in practice: the detector emits a flat 0.0.
    Reporting r = 0 would read as 'the engines disagree completely', when the
    truth is that one of them said nothing at all."""
    ts = np.arange(60) * 33.0
    data = rows("au.AU20", A, ts, np.zeros(60)) + rows("au.AU20", B, ts, np.random.rand(60))

    a = channel_agreement(data, "au.AU20", A, B)
    assert a.verdict == "degenerate"
    assert a.r is None
    assert "not zero" in a.detail


def test_non_overlapping_time_ranges_are_reported_as_such():
    data = (rows("au.AU12", A, np.arange(50) * 33.0, np.random.rand(50))
            + rows("au.AU12", B, 100000 + np.arange(50) * 33.0, np.random.rand(50)))
    assert channel_agreement(data, "au.AU12", A, B).verdict == "no_overlap"


def test_a_missing_source_is_no_overlap_not_a_crash():
    data = rows("au.AU12", A, np.arange(50) * 33.0, np.random.rand(50))
    assert channel_agreement(data, "au.AU12", A, B).verdict == "no_overlap"


def test_all_source_pairs_are_compared():
    ts = np.arange(60) * 33.0
    v = np.sin(ts / 300.0)
    C = "face.enginec@0.1.0+server-batch"
    data = (rows("au.AU12", A, ts, v) + rows("au.AU12", B, ts, v)
            + rows("au.AU12", C, ts, v))

    assert len(agreement_for_channel(data, "au.AU12")) == 3  # 3 choose 2


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------

def test_summary_counts_single_source_channels_separately():
    ts = np.arange(60) * 33.0
    v = np.sin(ts / 300.0)
    both = agreement_for_channel(
        rows("au.AU12", A, ts, v) + rows("au.AU12", B, ts, v), "au.AU12")
    alone = agreement_for_channel(rows("au.AU04", A, ts, v), "au.AU04")

    s = summarise(both + alone)
    assert s["n_measured"] == 1
    assert s["n_single_source"] == 1
    assert s["published_range"] == PUBLISHED_INTER_ENGINE_R


def test_summary_of_nothing_measured_reports_none_not_zero():
    s = summarise(agreement_for_channel([], "au.AU12"))
    assert s["between_engines"]["median_r"] is None
    assert s["between_engines"]["min_r"] is None


# ---------------------------------------------------------------------------
# what two sources actually differ in
# ---------------------------------------------------------------------------

def test_placement_and_engine_comparisons_are_distinguished():
    """Getting this wrong is worse than not computing a correlation at all.

    On a real session the SAME engine across browser-live and server-batch
    agreed at median r = 0.83. Read against §2.2's inter-ENGINE benchmark of
    0.37-0.75 that looks like unusually good agreement between engines — when
    no two engines were involved. Two placements of one model over the same
    pixels should agree closely, so a low r there is a placement bug.
    """
    assert comparison_kind("face.x@0.1.0+browser-live",
                           "face.x@0.1.0+server-batch") == "placements"
    assert comparison_kind("face.x@0.1.0+server-batch",
                           "face.y@0.1.0+server-batch") == "engines"
    assert comparison_kind("face.x@0.1.0+server-batch",
                           "face.x@0.2.0+server-batch") == "versions"


def test_the_summary_keeps_the_kinds_apart():
    """Pooling them produces a median that answers neither question."""
    ts = np.arange(60) * 33.0
    v = np.sin(ts / 300.0)

    placements = channel_agreement(
        rows("b.x", "face.x@0.1.0+browser-live", ts, v)
        + rows("b.x", "face.x@0.1.0+server-batch", ts, v),
        "b.x", "face.x@0.1.0+browser-live", "face.x@0.1.0+server-batch")
    engines = channel_agreement(
        rows("b.y", "face.x@0.1.0+server-batch", ts, v)
        + rows("b.y", "face.y@0.1.0+server-batch", ts, v * 0.5 + 0.1),
        "b.y", "face.x@0.1.0+server-batch", "face.y@0.1.0+server-batch")

    s = summarise([placements, engines])
    assert s["between_placements"]["n"] == 1
    assert s["between_engines"]["n"] == 1


def test_the_published_benchmark_is_labelled_as_applying_to_engines_only():
    s = summarise([])
    assert "between_engines" in s and "published_range" in s


# ---------------------------------------------------------------------------
# relative within-participant proportions
# ---------------------------------------------------------------------------

def test_relative_proportion_is_a_percentile_rank():
    rel = relative_proportion([10.0, 20.0, 30.0, 40.0, 50.0])
    assert rel[0] == pytest.approx(0.0)
    assert rel[-1] == pytest.approx(1.0)
    assert rel[2] == pytest.approx(0.5)


def test_relative_proportion_survives_a_scale_change():
    """The property that makes it robust across detectors. Two engines putting
    the same face at different absolute levels still agree about which moments
    were the most active."""
    raw = np.array([0.1, 0.4, 0.2, 0.9, 0.3])
    assert np.allclose(relative_proportion(raw), relative_proportion(raw * 3.7 + 1.2))


def test_a_flat_channel_maps_to_the_middle_not_an_arbitrary_order():
    """AU20 emits a constant. Ranking identical values by index would invent an
    ordering and make a dead channel look like it varied."""
    assert np.allclose(relative_proportion([0.0] * 10), 0.5)


def test_ties_share_a_rank():
    rel = relative_proportion([1.0, 1.0, 2.0, 2.0])
    assert rel[0] == rel[1]
    assert rel[2] == rel[3]


def test_relative_proportion_handles_degenerate_input():
    assert len(relative_proportion([])) == 0
    assert relative_proportion([5.0])[0] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# condition contrast — the shape a result should take
# ---------------------------------------------------------------------------

def test_a_contrast_detects_a_real_within_participant_difference():
    """§2.2: report relative, within-participant, condition-contrast claims
    ("more brow-furrow during X than Y"), never absolute state claims."""
    rng = np.random.default_rng(1)
    low = rng.normal(0.2, 0.05, 100)
    high = rng.normal(0.6, 0.05, 100)

    c = condition_contrast(high, low)
    assert c["comparable"] is True
    assert c["relative_difference"] > 0.4


def test_a_contrast_of_identical_conditions_is_near_zero():
    rng = np.random.default_rng(2)
    a = rng.normal(0.4, 0.1, 200)
    b = rng.normal(0.4, 0.1, 200)
    assert abs(condition_contrast(a, b)["relative_difference"]) < 0.15


def test_the_contrast_is_unchanged_by_a_detector_wide_rescale():
    """The claim has to survive swapping the engine, which is the entire reason
    for preferring it to an absolute count."""
    rng = np.random.default_rng(3)
    a = rng.normal(0.6, 0.05, 100)
    b = rng.normal(0.2, 0.05, 100)

    plain = condition_contrast(a, b)["relative_difference"]
    rescaled = condition_contrast(a * 2.5 + 0.3, b * 2.5 + 0.3)["relative_difference"]
    assert plain == pytest.approx(rescaled)


def test_an_empty_condition_is_not_comparable():
    c = condition_contrast([], [1.0, 2.0])
    assert c["comparable"] is False
    assert "no samples" in c["reason"]


# ---------------------------------------------------------------------------
# barely moved is not the same as disagreed
# ---------------------------------------------------------------------------

def test_a_channel_that_barely_moved_is_not_reported_as_disagreement():
    """The exact case found on a real session.

    `blendshape.jawRight` correlated at r = 0.065 between two placements of the
    SAME engine on the SAME pixels — alarming, until its mean turned out to be
    0.0003 with sd 0.010. The participant never moved their jaw sideways. Both
    engines correctly reported nothing, and correlating two near-zero noise
    series gives approximately zero. Calling that a disagreement invents a
    measurement problem out of a movement that never happened.
    """
    rng = np.random.default_rng(7)
    ts = np.arange(200) * 33.0
    data = (rows("b.jawRight", A, ts, rng.normal(0.0003, 0.002, 200))
            + rows("b.jawRight", B, ts, rng.normal(0.0003, 0.002, 200)))

    a = channel_agreement(data, "b.jawRight", A, B)
    assert a.verdict == "low_variance"
    assert a.r is None
    assert "nothing happened" in a.detail


def test_a_channel_that_did_move_is_still_correlated():
    """The gate must not swallow real disagreement along with real stillness."""
    rng = np.random.default_rng(8)
    ts = np.arange(200) * 33.0
    v = np.sin(ts / 300.0) * 0.3 + 0.5
    data = (rows("b.browDown", A, ts, v)
            + rows("b.browDown", B, ts, v + rng.normal(0, 0.02, 200)))

    a = channel_agreement(data, "b.browDown", A, B)
    assert a.verdict == "ok"
    assert a.r > 0.9


def test_the_spread_is_reported_so_a_reader_can_judge():
    """A correlation cannot be read without knowing how much moved."""
    ts = np.arange(100) * 33.0
    v = np.sin(ts / 300.0)
    data = rows("b.x", A, ts, v) + rows("b.x", B, ts, v)

    a = channel_agreement(data, "b.x", A, B)
    assert a.sd_a is not None and a.sd_b is not None
    assert a.sd_a > 0.5


def test_the_variance_floor_is_overridable_for_other_units():
    """Head pose is in degrees, gaze in screen fractions. A floor tuned for
    0..1 intensity channels is wrong for both."""
    rng = np.random.default_rng(9)
    ts = np.arange(200) * 33.0
    v = rng.normal(0, 0.005, 200)
    data = rows("h.yaw", A, ts, v) + rows("h.yaw", B, ts, v)

    assert channel_agreement(data, "h.yaw", A, B).verdict == "low_variance"
    assert channel_agreement(data, "h.yaw", A, B, min_sd=0.0001).verdict == "ok"


def test_summary_counts_low_variance_separately():
    """Folding these into 'measured' would drag the median toward zero with
    channels that had nothing to say."""
    rng = np.random.default_rng(10)
    ts = np.arange(200) * 33.0
    flat = rows("b.flat", A, ts, rng.normal(0, 0.001, 200)) + \
        rows("b.flat", B, ts, rng.normal(0, 0.001, 200))

    s = summarise(agreement_for_channel(flat, "b.flat"))
    assert s["n_low_variance"] == 1
    assert s["n_measured"] == 0

"""Tests for AOI definition, padding, and the Holmqvist-taxonomy metrics."""

from __future__ import annotations

import pytest

from aoi import AOI, AOIMetrics, AOISet, analyse, from_calibration_grid, hit, pad_fraction

VIEWPORT = (1707.0, 1067.0)
DPP = 0.0236          # ~42 px/deg, measured from a real session


class Fix:
    """Minimal stand-in for a classified fixation event."""

    kind = "fixation"

    def __init__(self, x, y, onset, offset):
        self.x, self.y = x, y
        self.onset_ts, self.offset_ts = onset, offset


LEFT = AOI("left", "rect", (0.0, 0.0, 0.4, 1.0), label="left panel")
RIGHT = AOI("right", "rect", (0.6, 0.0, 1.0, 1.0), label="right panel")
SET = AOISet(name="two_panels", version="1", aois=(LEFT, RIGHT))


# ---------------------------------------------------------------------------
# definitions and provenance
# ---------------------------------------------------------------------------

def test_shapes_validate_their_coordinate_count():
    with pytest.raises(ValueError):
        AOI("a", "rect", (0.0, 0.0, 1.0))
    with pytest.raises(ValueError):
        AOI("a", "circle", (0.5, 0.5))
    with pytest.raises(ValueError):
        AOI("a", "polygon", (0.0, 0.0, 1.0, 1.0))


def test_editing_a_boundary_changes_the_content_hash():
    """§4.2: the same gaze data moved 77% -> 88% -> 93% purely from refining the
    same AOI definitions. A hit rate is only interpretable alongside the
    boundaries that produced it, so the identity has to follow the geometry —
    not a version string someone has to remember to bump.
    """
    a = AOISet("s", "1", (AOI("x", "rect", (0.0, 0.0, 0.5, 0.5)),))
    b = AOISet("s", "1", (AOI("x", "rect", (0.0, 0.0, 0.55, 0.5)),))
    assert a.content_hash() != b.content_hash()


def test_hash_is_stable_under_reordering():
    """Two sets with the same boundaries are the same definition."""
    a = AOISet("s", "1", (LEFT, RIGHT))
    b = AOISet("s", "1", (RIGHT, LEFT))
    assert a.content_hash() == b.content_hash()


def test_provenance_carries_everything_needed_to_reproduce_a_hit_rate():
    p = SET.provenance()
    assert {"aoi_set", "aoi_version", "aoi_content_hash", "n_aois"} <= set(p)


# ---------------------------------------------------------------------------
# padding
# ---------------------------------------------------------------------------

def test_padding_converts_degrees_to_a_screen_fraction():
    # 4 deg at 42 px/deg is ~169 px, which on a 1707 px axis is ~10%.
    f = pad_fraction(4.0, DPP, VIEWPORT[0])
    assert f == pytest.approx((4.0 / DPP) / 1707.0, rel=1e-9)
    assert 0.09 < f < 0.11


def test_padding_refuses_without_geometry():
    with pytest.raises(ValueError):
        pad_fraction(4.0, None, VIEWPORT[0])


def test_a_fixation_just_outside_a_box_still_counts_once_padded():
    """§4.2: don't use pixel-tight boxes. A fixation estimated a degree off a
    button was still a fixation on that button."""
    box = AOI("b", "rect", (0.4, 0.4, 0.6, 0.6))
    just_outside = (0.63, 0.5)

    assert not hit(*just_outside, box)
    pad_x = pad_fraction(4.0, DPP, VIEWPORT[0])
    pad_y = pad_fraction(4.0, DPP, VIEWPORT[1])
    assert hit(*just_outside, box, pad_x=pad_x, pad_y=pad_y)


def test_padding_is_anisotropic_because_the_screen_is_not_square():
    """The same angular budget is a different fraction of each axis."""
    assert pad_fraction(4.0, DPP, VIEWPORT[0]) != pad_fraction(4.0, DPP, VIEWPORT[1])


# ---------------------------------------------------------------------------
# hit testing
# ---------------------------------------------------------------------------

def test_rect_hit_testing():
    assert hit(0.2, 0.5, LEFT)
    assert not hit(0.5, 0.5, LEFT)


def test_rect_coordinates_may_be_given_in_either_corner_order():
    a = AOI("a", "rect", (0.2, 0.2, 0.8, 0.8))
    b = AOI("b", "rect", (0.8, 0.8, 0.2, 0.2))
    assert hit(0.5, 0.5, a) and hit(0.5, 0.5, b)


def test_circle_hit_testing():
    c = AOI("c", "circle", (0.5, 0.5, 0.1))
    assert hit(0.55, 0.5, c)
    assert not hit(0.7, 0.5, c)


def test_polygon_hit_testing():
    tri = AOI("t", "polygon", (0.1, 0.1, 0.9, 0.1, 0.5, 0.9))
    assert hit(0.5, 0.3, tri)
    assert not hit(0.1, 0.8, tri)


def test_polygon_padding_grows_the_shape():
    tri = AOI("t", "polygon", (0.3, 0.3, 0.7, 0.3, 0.5, 0.7))
    outside = (0.5, 0.78)
    assert not hit(*outside, tri)
    assert hit(*outside, tri, pad_x=0.12, pad_y=0.12)


# ---------------------------------------------------------------------------
# metrics — the Holmqvist distinctions
# ---------------------------------------------------------------------------

def _trace():
    """left, left, right, left again — so first/second pass differ."""
    return [
        Fix(0.2, 0.5, 1000, 1300),    # left  300ms
        Fix(0.25, 0.5, 1400, 1600),   # left  200ms  (same dwell)
        Fix(0.8, 0.5, 1700, 2100),    # right 400ms
        Fix(0.2, 0.5, 2200, 2500),    # left  300ms  (second pass)
    ]


def test_fixation_count_and_dwell_count_are_different_measures():
    """Four fixations in one visit is one dwell. §4.1 treats these as distinct
    constructs, and conflating them would inflate visit counts."""
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    left = r.metrics["left"]
    assert left.n_fixations == 3
    assert left.n_dwells == 2


def test_total_dwell_time_sums_every_visit():
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.metrics["left"].total_dwell_ms == pytest.approx(300 + 200 + 300)


def test_first_fixation_duration_is_the_first_one_only():
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.metrics["left"].first_fixation_duration_ms == pytest.approx(300)
    assert r.metrics["right"].first_fixation_duration_ms == pytest.approx(400)


def test_entry_time_is_a_latency_not_a_duration():
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.metrics["left"].entry_time_ms == pytest.approx(0)
    assert r.metrics["right"].entry_time_ms == pytest.approx(700)


def test_first_and_second_pass_dwells_are_separate():
    """Re-reading is the phenomenon these two measures exist to distinguish."""
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    left = r.metrics["left"]
    assert left.first_pass_dwell_ms == pytest.approx(700)     # 1000 -> 1700
    assert left.second_pass_dwell_ms == pytest.approx(300)    # 2200 -> 2500


def test_an_aoi_never_looked_at_reports_none_not_zero():
    """A zero entry time would read as 'looked at immediately'."""
    never = AOISet("s", "1", (AOI("ghost", "rect", (0.45, 0.0, 0.55, 0.02)),))
    r = analyse(_trace(), never, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    m = r.metrics["ghost"]
    assert m.n_fixations == 0
    assert m.entry_time_ms is None
    assert m.first_fixation_duration_ms is None


def test_hit_rate_counts_fixations_landing_in_any_aoi():
    trace = _trace() + [Fix(0.5, 0.5, 2600, 2900)]   # the gap between panels
    r = analyse(trace, SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.n_fixations == 5
    assert r.n_hits == 4
    assert r.hit_rate == pytest.approx(4 / 5)


def test_padding_moves_the_hit_rate_which_is_the_whole_point():
    """§4.2's finding, reproduced: the same gaze data gives a different hit rate
    under different boundaries, so the padding must be reported with it."""
    trace = _trace() + [Fix(0.5, 0.5, 2600, 2900)]
    tight = analyse(trace, SET, pad_deg=0.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    padded = analyse(trace, SET, pad_deg=4.5, degrees_per_px=DPP, viewport_px=VIEWPORT)

    assert padded.hit_rate > tight.hit_rate
    assert padded.provenance["pad_deg"] == 4.5
    assert tight.provenance["pad_deg"] == 0.0


def test_overlapping_aois_both_get_credit():
    """Assigning a fixation to one winning AOI would bury the overlap, and a
    researcher who drew nested regions usually meant them to nest."""
    outer = AOI("outer", "rect", (0.0, 0.0, 1.0, 1.0))
    inner = AOI("inner", "rect", (0.1, 0.4, 0.3, 0.6))
    s = AOISet("nested", "1", (outer, inner))

    r = analyse([Fix(0.2, 0.5, 0, 300)], s, pad_deg=0.0,
                degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.metrics["outer"].n_fixations == 1
    assert r.metrics["inner"].n_fixations == 1
    assert r.hit_rate == 1.0


def test_saccades_are_ignored():
    """Dwell time is a property of fixations; counting saccades would inflate it."""
    class Sacc:
        kind = "saccade"
        x = y = None
        onset_ts = offset_ts = 0

    r = analyse(_trace() + [Sacc()], SET, pad_deg=0.0,
                degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.n_fixations == 4


def test_entry_time_is_measured_from_the_analysis_window_not_the_first_fixation():
    """Latency to an AOI means latency from stimulus onset."""
    r = analyse(_trace(), SET, pad_deg=0.0, degrees_per_px=DPP,
                viewport_px=VIEWPORT, window_start_ms=0.0)
    assert r.metrics["left"].entry_time_ms == pytest.approx(1000)


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------

def test_refuses_without_geometry():
    """A pixel pad is a different angular tolerance for every participant, so
    hit rates computed that way are not comparable across a study."""
    r = analyse(_trace(), SET, pad_deg=4.0, degrees_per_px=None, viewport_px=VIEWPORT)
    assert r.refusal == "no_geometry"
    assert r.metrics == {}
    assert r.provenance["aoi_set"] == "two_panels"


def test_refuses_with_no_fixations():
    r = analyse([], SET, pad_deg=4.0, degrees_per_px=DPP, viewport_px=VIEWPORT)
    assert r.refusal == "no_fixations"


def test_negative_padding_is_an_error():
    with pytest.raises(ValueError):
        analyse(_trace(), SET, pad_deg=-1.0, degrees_per_px=DPP, viewport_px=VIEWPORT)


# ---------------------------------------------------------------------------
# the calibration-grid diagnostic
# ---------------------------------------------------------------------------

def test_calibration_grid_builds_one_aoi_per_target():
    grid = [[0.1, 0.1], [0.5, 0.5], [0.9, 0.9]]
    s = from_calibration_grid(grid)
    assert len(s.aois) == 3
    assert all(a.shape == "circle" for a in s.aois)
    assert s.provenance()["aoi_set"] == "calibration_grid"


# ---------------------------------------------------------------------------
# AOIs drawn on a stimulus
# ---------------------------------------------------------------------------

from aoi import to_stage  # noqa: E402

_PANELS = (AOI("left", "rect", (0.1, 0.2, 0.4, 0.8)), AOI("dot", "circle", (0.7, 0.5, 0.1)))


def test_a_screen_set_hashes_exactly_as_before_stimuli_existed():
    """Pinned: computed by the formula before stimulus_id was added, and
    unchanged after. Every result already recorded references these hashes."""
    assert AOISet("panels", "1", _PANELS).content_hash() == "501a06a0da43d659"


def test_the_stimulus_is_part_of_a_sets_identity():
    screen = AOISet("panels", "1", _PANELS)
    on_a = AOISet("panels", "1", _PANELS, stimulus_id="scene_left")
    on_b = AOISet("panels", "1", _PANELS, stimulus_id="scene_right")
    assert len({screen.content_hash(), on_a.content_hash(), on_b.content_hash()}) == 3
    assert on_a.provenance()["stimulus_id"] == "scene_left"
    assert "stimulus_id" not in screen.provenance()


def test_to_stage_places_a_rect_where_the_stimulus_was_shown():
    rect = {"x0": 0.1, "y0": 0.2, "x1": 0.9, "y1": 0.6}     # 0.8 wide, 0.4 tall
    got = to_stage(AOI("a", "rect", (0.0, 0.0, 0.5, 1.0)), rect)
    assert got.coords == pytest.approx((0.1, 0.2, 0.5, 0.6))


def test_to_stage_maps_polygon_pairs_and_scales_a_circle_by_width():
    rect = {"x0": 0.25, "y0": 0.25, "x1": 0.75, "y1": 0.5}
    poly = to_stage(AOI("p", "polygon", (0, 0, 1, 0, 0, 1)), rect)
    assert poly.coords == pytest.approx((0.25, 0.25, 0.75, 0.25, 0.25, 0.5))
    circ = to_stage(AOI("c", "circle", (0.5, 0.5, 0.2)), rect)
    assert circ.coords == pytest.approx((0.5, 0.375, 0.1))


def test_a_degenerate_stimulus_rect_is_refused():
    with pytest.raises(ValueError):
        to_stage(_PANELS[0], {"x0": 0.5, "y0": 0.1, "x1": 0.5, "y1": 0.9})

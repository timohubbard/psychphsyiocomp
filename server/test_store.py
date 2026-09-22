"""Tests for the read side — what the researcher UI asks the tables."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from alignment import Anchor, ClockRegistry
from engine_contract import Chunk, QualityRow, SignalRow
from store import channel_series, list_sessions, session_detail
from tables import CanonicalWriter, SessionContext

MASTER = "performance.now"
VIDEO = "video_pts"


@pytest.fixture
def populated(tmp_path):
    """One session with two sources, quality rows, and a gaze metric."""
    ctx = SessionContext(session_id="s001", participant_id="p001", study_id="demo")
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({
        "created_utc": "2026-09-22T10:00:00.000Z",
        "screen": {"width_px": 1707, "height_px": 1067, "device_pixel_ratio": 1.5},
        "achieved_fps": 29.9,
        "clock": {"master_clock_id": MASTER, "measured_resolution_ms": 0.005},
        "geometry": {"ok": True, "viewing_distance_mm": 474.9, "px_per_mm": 5.1,
                     "geometry_method": "virtual_chinrest", "geometry_error_mm": 55.0,
                     "precision_mm": 27.7, "reason": None},
    })

    reg = ClockRegistry(master_clock_id=MASTER)
    reg.add_anchor(Anchor(VIDEO, 1000.0, MASTER, 1000.0, uncertainty_ms=32.0, label="c"))
    sol = reg.solve(VIDEO)

    face = tuple(SignalRow(stream="face", channel="blendshape.jawOpen",
                           native_clock_id=VIDEO, native_ts=1000.0 + i * 33.0,
                           value=0.1 * i, reliability_tier="moderate")
                 for i in range(20))
    gaze = tuple(SignalRow(stream="gaze", channel="gaze.x",
                           native_clock_id=VIDEO, native_ts=1000.0 + i * 33.0,
                           value=0.5, reliability_tier="moderate")
                 for i in range(20))
    quality = (
        QualityRow(stream="face", metric="achieved_fps",
                   window_start_native_ts=1000.0, window_end_native_ts=6000.0, value=29.9),
        QualityRow(stream="gaze", metric="gaze_average_offset_deg",
                   window_start_native_ts=1000.0, window_end_native_ts=6000.0, value=1.65),
    )

    w.add_chunks([Chunk(signals=face, quality=quality)],
                 source="face.x@0.1.0+server-batch", params={}, solution=sol)
    w.add_chunks([Chunk(signals=gaze)],
                 source="gaze.ridge@0.1.0+server-fit", params={}, solution=sol)
    w.add_run(run_id="r1", manifest=_manifest(), source="face.x@0.1.0+server-batch",
              params={}, eligibility=_eligible(), solution=sol,
              media_sha256="0" * 64, started=datetime.now(timezone.utc))
    w.close()
    return tmp_path


def _manifest():
    from engine_contract import (EngineLicense, EngineManifest, EngineOutputs,
                                 EngineProvenance, InputSpec)
    return EngineManifest(
        engine_id="face.x", version="0.1.0", modality="face", runtime="python-cpu",
        placement="server-batch", inputs=[InputSpec(kind="video")], params_schema={},
        outputs=EngineOutputs(signals=[], events=[], quality=[]),
        license=EngineLicense(spdx="Apache-2.0", commercial_use="yes", url="http://x"),
        provenance=EngineProvenance(),
    )


def _eligible():
    from engine_contract import Eligibility
    return Eligibility(eligible=True, reasons=(), detail=None)


# ---------------------------------------------------------------------------
# listing
# ---------------------------------------------------------------------------

def test_lists_a_processed_session(populated):
    rows = list_sessions(populated)
    assert len(rows) == 1
    r = rows[0]
    assert r["session_id"] == "s001"
    assert r["participant_id"] == "p001"
    assert r["n_sources"] == 2


def test_an_empty_root_lists_nothing_rather_than_raising(tmp_path):
    assert list_sessions(tmp_path) == []
    assert list_sessions(tmp_path / "does-not-exist") == []


def test_session_metrics_are_flattened_onto_the_summary_row(populated):
    """A researcher scanning the list is looking for gaze accuracy; making them
    open each session to find it defeats the list."""
    r = list_sessions(populated)[0]
    assert r["gaze_average_offset_deg"] == pytest.approx(1.65)


def test_alignment_fraction_is_a_headline_field(populated):
    """Unaligned rows cannot be compared against anything, so this decides
    whether the rest of the row means anything at all."""
    assert list_sessions(populated)[0]["aligned"] == 1.0


def test_unaligned_rows_are_visible_in_the_fraction(tmp_path):
    ctx = SessionContext(session_id="s002", participant_id="p", study_id="d")
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({})
    # No anchor: the clock cannot be solved, so master_ts stays NULL.
    sol = ClockRegistry(master_clock_id=MASTER).solve(VIDEO)
    rows = tuple(SignalRow(stream="face", channel="c", native_clock_id=VIDEO,
                           native_ts=float(i), value=1.0, reliability_tier="low")
                 for i in range(5))
    w.add_chunks([Chunk(signals=rows)], source="e@1+server-batch", params={}, solution=sol)
    w.close()

    assert list_sessions(tmp_path)[0]["aligned"] == 0.0


# ---------------------------------------------------------------------------
# detail
# ---------------------------------------------------------------------------

def test_detail_summarises_channels_per_source(populated):
    d = session_detail(populated, "s001")
    keys = {(c["channel"], c["source"]) for c in d["channels"]}
    assert ("blendshape.jawOpen", "face.x@0.1.0+server-batch") in keys
    assert ("gaze.x", "gaze.ridge@0.1.0+server-fit") in keys


def test_detail_separates_windowed_from_session_scoped_metrics(populated):
    """A one-per-session figure plotted as a time series would imply it was
    measured repeatedly."""
    d = session_detail(populated, "s001")
    windowed = {q["metric"] for q in d["quality"]}
    assert "achieved_fps" in windowed
    assert "gaze_average_offset_deg" not in windowed
    assert "gaze_average_offset_deg" in d["session_metrics"]


def test_detail_carries_licence_for_audit(populated):
    """Licence travels with the run so a historical session stays auditable
    after the engine package is upgraded or removed."""
    d = session_detail(populated, "s001")
    assert d["runs"][0]["license_spdx"] == "Apache-2.0"


def test_missing_session_raises_not_found(populated):
    with pytest.raises(FileNotFoundError):
        session_detail(populated, "nope")


# ---------------------------------------------------------------------------
# series
# ---------------------------------------------------------------------------

def test_series_returns_sorted_points(populated):
    s = channel_series(populated, "s001", "blendshape.jawOpen")
    ts = [p[0] for p in s["points"]]
    assert ts == sorted(ts)
    assert s["n_total"] == 20


def test_series_filters_by_source(populated):
    s = channel_series(populated, "s001", "gaze.x",
                       source="gaze.ridge@0.1.0+server-fit")
    assert s["n_total"] == 20
    assert all(p[1] == 0.5 for p in s["points"])


def test_series_decimates_by_stride_not_by_averaging(populated):
    """Averaging would smooth away the brief events — blinks, saccades — that
    someone scanning a trace is looking for."""
    s = channel_series(populated, "s001", "blendshape.jawOpen", max_points=5)
    assert s["stride"] == 4
    assert len(s["points"]) == 5
    # Values are original samples, not means of neighbours.
    originals = {round(0.1 * i, 10) for i in range(20)}
    assert all(round(p[1], 10) in originals for p in s["points"])


def test_series_for_an_unknown_channel_is_empty_not_an_error(populated):
    s = channel_series(populated, "s001", "nope.nope")
    assert s["points"] == [] and s["n_total"] == 0


# ---------------------------------------------------------------------------
# quality grouped by the engine that emitted it
# ---------------------------------------------------------------------------

@pytest.fixture
def colliding(tmp_path):
    """Two engines emitting the SAME metric name with different values.

    `mean_luminance` is emitted by three of this project's engines already, and
    `usable_fraction` is a name any engine could reasonably pick. This is the
    case a flat metric namespace gets wrong.
    """
    ctx = SessionContext(session_id="s002", participant_id="p002", study_id="demo")
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({"created_utc": "2026-09-22T10:00:00.000Z",
                            "clock": {"master_clock_id": MASTER}})

    reg = ClockRegistry(master_clock_id=MASTER)
    reg.add_anchor(Anchor(VIDEO, 1000.0, MASTER, 1000.0, uncertainty_ms=32.0, label="c"))
    sol = reg.solve(VIDEO)

    def chunk(stream, value):
        return Chunk(
            signals=(SignalRow(stream=stream, channel=f"{stream}.v",
                               native_clock_id=VIDEO, native_ts=1000.0, value=0.0,
                               reliability_tier="low"),),
            quality=(QualityRow(stream=stream, metric="mean_luminance",
                                window_start_native_ts=1000.0,
                                window_end_native_ts=6000.0, value=value),))

    w.add_chunks([chunk("face", 138.0)],
                 source="face.mediapipe_blendshapes@0.1.0+server-batch",
                 params={}, solution=sol)
    w.add_chunks([chunk("resp", 42.0)],
                 source="resp.motion_profiles@0.1.0+server-batch",
                 params={}, solution=sol)
    w.close()
    return tmp_path


def test_the_same_metric_from_two_engines_does_not_collide(colliding):
    eq = session_detail(colliding, "s002")["engine_quality"]
    assert eq["face"]["metrics"]["mean_luminance"] == 138.0
    assert eq["resp"]["metrics"]["mean_luminance"] == 42.0


def test_engine_quality_is_keyed_by_modality_not_engine_id(colliding):
    """A researcher asks about respiration, not about which engine implements
    it. Swapping the engine should not move where the UI looks."""
    eq = session_detail(colliding, "s002")["engine_quality"]
    assert set(eq) == {"face", "resp"}
    assert eq["resp"]["sources"] == ["resp.motion_profiles@0.1.0+server-batch"]


def test_engine_quality_is_empty_rather_than_absent_without_quality(tmp_path):
    ctx = SessionContext(session_id="s003", participant_id="p", study_id="d")
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({"created_utc": "2026-09-22T10:00:00.000Z",
                            "clock": {"master_clock_id": MASTER}})
    w.close()
    assert session_detail(tmp_path, "s003")["engine_quality"] == {}

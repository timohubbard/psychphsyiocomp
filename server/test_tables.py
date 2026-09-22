"""Tests for the canonical Parquet writer.

Includes the M0 gate: one Parquet file containing two ``source`` values for the
same channel in the same session, plottable against each other.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pyarrow.parquet as pq
import pytest

from alignment import Anchor, ClockRegistry
from engine_contract import (
    Chunk,
    Eligibility,
    EngineLicense,
    EngineManifest,
    EngineOutputs,
    EngineProvenance,
    EventRow,
    QualityRow,
    SignalRow,
)
from tables import (
    EVENTS_SCHEMA,
    QUALITY_SCHEMA,
    RUNS_SCHEMA,
    SIGNALS_SCHEMA,
    CanonicalWriter,
    SessionContext,
    params_hash,
    read_session,
)

MASTER = "performance.now"
VIDEO = "video_pts"


@pytest.fixture
def ctx():
    return SessionContext(session_id="s001", participant_id="p001", study_id="m0")


@pytest.fixture
def manifest():
    return EngineManifest(
        engine_id="face.mediapipe_blendshapes",
        version="0.1.0",
        modality="face",
        runtime="python-cpu",
        placement="server-batch",
        inputs=[],
        params_schema={},
        outputs=EngineOutputs(),
        license=EngineLicense(
            spdx="Apache-2.0", commercial_use="yes",
            url="https://github.com/google-ai-edge/mediapipe",
        ),
        provenance=EngineProvenance(),
    )


def _chunk(channel="blendshape.mouthSmileLeft", clock=VIDEO, n=5, start=0.0, step=33.3):
    return Chunk(
        signals=tuple(
            SignalRow(
                stream="face", channel=channel, native_clock_id=clock,
                native_ts=start + i * step, value=0.1 * i,
                reliability_tier="moderate",
            )
            for i in range(n)
        ),
        events=(
            EventRow(
                event_type="face_lost", native_clock_id=clock,
                onset_native_ts=start, offset_native_ts=start + step,
            ),
        ),
        quality=(
            QualityRow(
                stream="face", metric="achieved_fps",
                window_start_native_ts=start,
                window_end_native_ts=start + n * step, value=30.0,
            ),
        ),
    )


def _aligned_solution(offset=5000.0):
    reg = ClockRegistry(master_clock_id=MASTER)
    reg.add_anchor(Anchor(VIDEO, 0.0, MASTER, offset, uncertainty_ms=33.0))
    return reg.solve(VIDEO)


def _unaligned_solution():
    return ClockRegistry(master_clock_id=MASTER).solve(VIDEO)


# ---------------------------------------------------------------------------
# params_hash
# ---------------------------------------------------------------------------

def test_params_hash_is_order_independent():
    assert params_hash({"a": 1, "b": 2}) == params_hash({"b": 2, "a": 1})


def test_params_hash_distinguishes_different_params():
    """Re-running with different params must append distinguishably."""
    assert params_hash({"conf": 0.5}) != params_hash({"conf": 0.7})


# ---------------------------------------------------------------------------
# alignment propagation
# ---------------------------------------------------------------------------

def test_aligned_rows_carry_master_ts_and_uncertainty(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1+server-batch", params={},
                 solution=_aligned_solution(offset=5000.0))
    w.close()

    tbl = read_session(tmp_path, "s001", "signals").to_pylist()
    assert tbl
    for row in tbl:
        assert row["master_ts"] == pytest.approx(row["native_ts"] + 5000.0)
        assert row["master_ts_uncertainty_ms"] is not None
        assert row["master_ts_uncertainty_ms"] >= 33.0


def test_unaligned_rows_have_null_master_ts_not_a_guess(tmp_path, ctx):
    """The whole point of the refusal path, verified end to end.

    A zero-offset fallback would land master_ts == native_ts and look plausible
    while being wrong by an unknown amount.
    """
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1+server-batch", params={},
                 solution=_unaligned_solution())
    w.close()

    rows = read_session(tmp_path, "s001", "signals").to_pylist()
    assert rows
    for row in rows:
        assert row["master_ts"] is None, "unaligned must be NULL, never a guess"
        assert row["master_ts_uncertainty_ms"] is None
        assert row["native_ts"] is not None, "native_ts is always authoritative"


def test_unaligned_events_also_null_both_ends(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1", params={}, solution=_unaligned_solution())
    w.close()

    ev = read_session(tmp_path, "s001", "events").to_pylist()
    assert ev
    for e in ev:
        assert e["onset_master_ts"] is None
        assert e["offset_master_ts"] is None
        assert e["onset_native_ts"] is not None


def test_run_row_records_why_alignment_failed(tmp_path, ctx, manifest):
    """A NULL master_ts must be explainable after the fact."""
    sol = _unaligned_solution()
    w = CanonicalWriter(tmp_path, ctx)
    w.add_run(
        run_id="r1", manifest=manifest, source="e@1", params={},
        eligibility=Eligibility(eligible=True), solution=sol,
        media_sha256="abc", started=datetime.now(timezone.utc),
    )
    w.close()

    runs = pq.read_table(tmp_path / "session_id=s001" / "runs.parquet").to_pylist()
    assert len(runs) == 1
    assert runs[0]["unaligned_reason"] is not None
    assert VIDEO in runs[0]["unaligned_reason"]
    assert runs[0]["clock_offset_ms"] is None, "must not record a bogus offset"


def test_run_row_carries_licence_for_later_audit(tmp_path, ctx, manifest):
    """Licensing must stay auditable after the engine package is upgraded."""
    w = CanonicalWriter(tmp_path, ctx)
    w.add_run(
        run_id="r1", manifest=manifest, source="e@1", params={},
        eligibility=Eligibility(eligible=True), solution=_aligned_solution(),
        media_sha256=None, started=datetime.now(timezone.utc),
    )
    w.close()

    run = pq.read_table(tmp_path / "session_id=s001" / "runs.parquet").to_pylist()[0]
    assert run["license_spdx"] == "Apache-2.0"
    assert run["license_commercial_use"] == "yes"


def test_ineligible_run_records_reasons(tmp_path, ctx, manifest):
    w = CanonicalWriter(tmp_path, ctx)
    w.add_run(
        run_id="r1", manifest=manifest, source="e@1", params={},
        eligibility=Eligibility(
            eligible=False, reasons=("fps_below_min",), detail="3.0 fps < 5 fps"
        ),
        solution=_aligned_solution(), media_sha256=None,
        started=datetime.now(timezone.utc), status="ineligible",
    )
    w.close()

    run = pq.read_table(tmp_path / "session_id=s001" / "runs.parquet").to_pylist()[0]
    assert run["eligible"] is False
    assert "fps_below_min" in run["ineligible_reasons"]
    assert run["status"] == "ineligible"


# ---------------------------------------------------------------------------
# THE M0 GATE
# ---------------------------------------------------------------------------

def test_m0_gate_two_sources_for_one_channel_in_one_session(tmp_path, ctx):
    """M0 success criterion.

    Open one Parquet file, see two `source` values for the same channel in the
    same session, and plot them against each other. This is what proves the
    browser/server duality and re-run-as-append semantics actually work.
    """
    browser = "face.mediapipe_blendshapes@0.1.0+browser-live"
    server = "face.mediapipe_blendshapes@0.1.0+server-batch"
    channel = "blendshape.mouthSmileLeft"

    w = CanonicalWriter(tmp_path, ctx)
    # Browser stamps against performance.now, so it is already on master.
    w.add_chunks(
        [_chunk(channel=channel, clock=MASTER)],
        source=browser, params={"min_face_detection_confidence": 0.5},
        solution=ClockRegistry(master_clock_id=MASTER).solve(MASTER),
    )
    # Server stamps against video PTS and is aligned via the clapper anchor.
    w.add_chunks(
        [_chunk(channel=channel, clock=VIDEO)],
        source=server, params={"min_face_detection_confidence": 0.5},
        solution=_aligned_solution(offset=0.0),
    )
    w.close()

    rows = read_session(tmp_path, "s001", "signals").to_pylist()
    same_channel = [r for r in rows if r["channel"] == channel]
    sources = {r["source"] for r in same_channel}

    assert sources == {browser, server}, f"expected both placements, got {sources}"

    # Both must be expressed on the master clock, or they are not comparable —
    # which is the entire point of the exercise.
    for r in same_channel:
        assert r["master_ts"] is not None

    # And they must be joinable: same channel, same session, differing only by
    # source. That is what makes a scatter plot of one against the other valid.
    browser_ts = sorted(r["master_ts"] for r in same_channel if r["source"] == browser)
    server_ts = sorted(r["master_ts"] for r in same_channel if r["source"] == server)
    assert browser_ts == pytest.approx(server_ts)


def test_rerun_appends_rather_than_replaces(tmp_path, ctx):
    """Two params_hashes for one source must coexist, not overwrite."""
    src = "face.mediapipe_blendshapes@0.1.0+server-batch"
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source=src, params={"conf": 0.5},
                 solution=_aligned_solution())
    w.add_chunks([_chunk()], source=src, params={"conf": 0.7},
                 solution=_aligned_solution())
    w.close()

    rows = read_session(tmp_path, "s001", "signals").to_pylist()
    hashes = {r["params_hash"] for r in rows}
    assert len(hashes) == 2, "re-run with different params must be distinguishable"


# ---------------------------------------------------------------------------
# schema and layout
# ---------------------------------------------------------------------------

def test_schema_is_explicit_not_inferred(tmp_path, ctx):
    """An inferred schema drifts the moment a column is all-null."""
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1", params={}, solution=_unaligned_solution())
    w.close()

    tbl = read_session(tmp_path, "s001", "signals")
    # master_ts is entirely null here; it must still be float64, not null-typed.
    assert tbl.schema.field("master_ts").type == SIGNALS_SCHEMA.field("master_ts").type
    assert tbl.schema.field("value").type == SIGNALS_SCHEMA.field("value").type


def test_empty_tables_still_written_with_schema(tmp_path, ctx):
    """Downstream readers should get a schema, not a missing-file error."""
    CanonicalWriter(tmp_path, ctx).close()
    session_dir = tmp_path / "session_id=s001"

    for name, schema in (
        ("signals", SIGNALS_SCHEMA), ("events", EVENTS_SCHEMA),
        ("quality", QUALITY_SCHEMA), ("runs", RUNS_SCHEMA),
    ):
        path = session_dir / f"{name}.parquet"
        assert path.exists(), f"{name}.parquet missing"
        tbl = pq.read_table(path)
        assert tbl.num_rows == 0
        assert tbl.schema.names == schema.names


def test_partitioned_by_session_and_stream(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1", params={}, solution=_aligned_solution())
    w.close()

    assert (tmp_path / "session_id=s001" / "stream=face" / "signals.parquet").exists()
    assert (tmp_path / "session_id=s001" / "stream=face" / "quality.parquet").exists()


def test_categorical_values_land_in_value_text(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks(
        [Chunk(signals=(SignalRow(
            stream="face", channel="expression.label", native_clock_id=VIDEO,
            native_ts=0.0, value="smile", reliability_tier="low",
        ),))],
        source="e@1", params={}, solution=_aligned_solution(),
    )
    w.close()

    row = read_session(tmp_path, "s001", "signals").to_pylist()[0]
    assert row["value"] is None
    assert row["value_text"] == "smile"


def test_reliability_tier_survives_the_round_trip(tmp_path, ctx):
    """§2.2's per-AU floor is enforced structurally, so it must persist."""
    w = CanonicalWriter(tmp_path, ctx)
    w.add_chunks([_chunk()], source="e@1", params={}, solution=_aligned_solution())
    w.close()

    rows = read_session(tmp_path, "s001", "signals").to_pylist()
    assert all(r["reliability_tier"] == "moderate" for r in rows)


def test_read_session_rejects_unknown_session(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_session(tmp_path, "nope")


# ---------------------------------------------------------------------------
# sessions table — screen geometry
#
# The reason this table exists separately from the manifest JSON: a dva figure
# needs px_per_mm and viewing_distance_mm at analysis time, and an analyst must
# be able to select on them with a predicate rather than parse a blob per
# session. §5.1 measured viewing distance at mean 47.3cm, SD 8.9 across 1,153
# online participants — it is a per-participant variable, not a constant.
# ---------------------------------------------------------------------------

GOOD_MANIFEST = {
    "created_utc": "2026-09-22T10:00:00.000Z",
    "user_agent": "Mozilla/5.0 test",
    "screen": {"width_px": 1920, "height_px": 1080, "device_pixel_ratio": 2.0},
    "achieved_fps": 29.6,
    "clock": {
        "master_clock_id": "performance.now",
        "measured_resolution_ms": 0.1,
        "cross_origin_isolated": True,
    },
    "applied_audio_constraints": {"noiseSuppression": False},
    "geometry": {
        "ok": True,
        "viewing_distance_mm": 473.0,
        "px_per_mm": 3.7795,
        "geometry_method": "virtual_chinrest",
        "geometry_error_mm": 55.0,
        "precision_mm": 4.0,
        "reason": None,
    },
}

REFUSED_MANIFEST = {
    **GOOD_MANIFEST,
    "geometry": {
        "ok": False,
        "viewing_distance_mm": None,
        "px_per_mm": None,
        "geometry_method": "unknown",
        "geometry_error_mm": None,
        "reason": "blind_spot_inconsistent",
    },
}


def _sessions(tmp_path):
    return pq.read_table(tmp_path / "session_id=s001" / "sessions.parquet").to_pylist()


def test_session_row_carries_geometry_for_dva_conversion(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata(GOOD_MANIFEST)
    w.close()

    row = _sessions(tmp_path)[0]
    assert row["viewing_distance_mm"] == pytest.approx(473.0)
    assert row["px_per_mm"] == pytest.approx(3.7795, rel=1e-4)
    assert row["geometry_method"] == "virtual_chinrest"
    assert row["screen_width_px"] == 1920


def test_refused_geometry_is_null_with_a_reason_not_a_default(tmp_path, ctx):
    """The whole point of the column pair.

    A NULL distance carrying a reason is a participant the method declined to
    guess about. Silently substituting the 47.3cm population mean would produce
    dva figures wrong by an unknown amount that look exactly like correct ones.
    """
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata(REFUSED_MANIFEST)
    w.close()

    row = _sessions(tmp_path)[0]
    assert row["viewing_distance_mm"] is None
    assert row["px_per_mm"] is None
    assert row["geometry_refusal_reason"] == "blind_spot_inconsistent"
    assert row["geometry_method"] == "unknown"


def test_refused_geometry_is_distinguishable_from_never_attempted(tmp_path, ctx):
    """Both have NULL geometry; only one is a statement about the participant."""
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({k: v for k, v in GOOD_MANIFEST.items() if k != "geometry"})
    w.close()

    never_attempted = _sessions(tmp_path)[0]
    assert never_attempted["viewing_distance_mm"] is None
    assert never_attempted["geometry_refusal_reason"] is None


def test_precision_and_accuracy_are_separate_columns(tmp_path, ctx):
    """Precision is what the participant's repetitions showed; accuracy is
    floored by the method's published 5.5cm MAE. Collapsing them is how a
    method with centimetre error starts reporting millimetre confidence."""
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata(GOOD_MANIFEST)
    w.close()

    row = _sessions(tmp_path)[0]
    assert row["geometry_precision_mm"] == pytest.approx(4.0)
    assert row["geometry_error_mm"] == pytest.approx(55.0)
    assert row["geometry_error_mm"] > row["geometry_precision_mm"]


def test_degrees_per_px_refuses_without_geometry(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata(REFUSED_MANIFEST)
    assert w.degrees_per_px() is None


def test_degrees_per_px_is_plausible_with_geometry(tmp_path, ctx):
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata(GOOD_MANIFEST)

    dpp = w.degrees_per_px()
    # One CSS px at 96dpi seen from 47.3cm subtends ~0.032 degrees; equivalently
    # ~31 px per degree, the familiar figure for a desktop viewing setup.
    assert dpp == pytest.approx(0.032, abs=0.005)
    assert 1.0 / dpp == pytest.approx(31, abs=4)


def test_sessions_table_written_even_with_no_manifest(tmp_path, ctx):
    """Readers get a typed empty table, never a missing-file error."""
    w = CanonicalWriter(tmp_path, ctx)
    w.close()

    tbl = pq.read_table(tmp_path / "session_id=s001" / "sessions.parquet")
    assert tbl.num_rows == 0
    assert "viewing_distance_mm" in tbl.schema.names


def test_session_row_survives_a_malformed_timestamp(tmp_path, ctx):
    """A browser that reports an unparseable date must not lose the geometry."""
    w = CanonicalWriter(tmp_path, ctx)
    w.set_session_metadata({**GOOD_MANIFEST, "created_utc": "not a date"})
    w.close()

    row = _sessions(tmp_path)[0]
    assert row["started_utc"] is None
    assert row["viewing_distance_mm"] == pytest.approx(473.0)

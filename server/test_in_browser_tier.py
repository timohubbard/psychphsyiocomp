"""The features_in_browser tier, server side: no recording, and nothing pretends otherwise.

Four things the tier needs from the pipeline, each pinned here:
- browser chunks keep the source they declared (gaze beside blendshapes);
- an engine that had no video writes a runs row saying why, not nothing;
- a recording that should not exist is deleted BEFORE any engine reads it;
- the gaze estimator fits on the browser's features when that is all there is.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from alignment import ClockSolution
from engine_contract import Chunk, SignalRow
from engine_contract.loader import load_engine_module
from gaze_pipeline import BROWSER_FEATURE_SOURCE, run_gaze_from_browser
from pipeline import (SessionBundle, _load_browser_chunks, no_video_eligibility,
                      process_session, refuse_unconsented_recording)
from tables import CanonicalWriter, SessionContext, read_session
from test_gaze_stage import _synthetic_session

_gaze = load_engine_module("gaze.mediapipe_features")

#: What process_session hands a stage for a video-less session: the video clock,
#: unaligned because there is no video to anchor.
UNALIGNED_VIDEO = ClockSolution(clock_id="video_pts", offset_ms=0.0, n_anchors=0,
                                unaligned_reason="no_video")


class _MustNotRun:
    """A server engine that fails the test if anything asks it to read media."""

    def __init__(self):
        self.manifest = _gaze._build_manifest()
        self.source = f"{self.manifest.source}+server-batch"

    def probe(self, media):
        raise AssertionError("probe() was called on a session with no permitted video")

    def run(self, media, params):
        raise AssertionError("run() was called on a session with no permitted video")


def _meta(tier="features_in_browser"):
    return {"session_id": "s1", "participant_id": "p1", "study_id": "d",
            "consent": {"tier": tier, "retentionDays": 30},
            "geometry": {"ok": True, "viewing_distance_mm": 500.0, "px_per_mm": 3.78},
            "screen": {"width_px": 1707, "height_px": 1067}}


def test_browser_chunks_keep_the_source_they_declared(tmp_path):
    p = tmp_path / "browser_chunks.json"
    p.write_text(json.dumps([
        {"signals": [{"stream": "face", "channel": "blendshape.x", "native_clock_id": "performance.now",
                      "native_ts": 1, "value": 0.1, "reliability_tier": "moderate"}]},
        {"source": BROWSER_FEATURE_SOURCE,
         "signals": [{"stream": "gaze", "channel": "eye.left_iris_dx", "native_clock_id": "performance.now",
                      "native_ts": 1, "value": 0.2, "reliability_tier": "moderate"}]},
    ]))
    chunks, sources = _load_browser_chunks(p)
    assert len(chunks) == 2
    assert sources == [None, BROWSER_FEATURE_SOURCE]


def test_each_browser_source_is_written_under_its_own_name(tmp_path):
    row = lambda stream, ch: SignalRow(stream=stream, channel=ch, native_clock_id="performance.now",
                                       native_ts=5.0, value=0.5, reliability_tier="moderate")
    bundle = SessionBundle(
        session_id="s1", participant_id="p1", study_id="d", metadata=_meta("features_only"),
        browser_chunks=[Chunk(signals=(row("face", "blendshape.x"),)),
                        Chunk(signals=(row("gaze", "eye.left_iris_dx"),))],
        browser_chunk_sources=[None, BROWSER_FEATURE_SOURCE])
    process_session(bundle, [], tmp_path)
    sig = read_session(tmp_path, "s1").to_pylist()
    by_channel = {r["channel"]: r["source"] for r in sig}
    assert by_channel["blendshape.x"] == "face.mediapipe_blendshapes@0.1.0+browser-live"
    assert by_channel["eye.left_iris_dx"] == BROWSER_FEATURE_SOURCE


def test_an_engine_with_no_video_writes_a_runs_row_saying_why(tmp_path):
    bundle = SessionBundle(session_id="s1", participant_id="p1", study_id="d", metadata=_meta())
    summary = process_session(bundle, [(_MustNotRun(), {})], tmp_path)
    runs = read_session(tmp_path, "s1", "runs").to_pylist()
    assert len(runs) == 1
    assert runs[0]["status"] == "ineligible"
    assert "no_video" in runs[0]["ineligible_reasons"]
    assert "features_in_browser" in runs[0]["eligibility_detail"]
    assert summary["runs"][0]["unaligned_reason"] == "no_video"


def test_a_recording_that_should_not_exist_is_deleted_before_any_engine_reads_it(tmp_path):
    video = tmp_path / "capture.webm"
    video.write_bytes(b"a video the participant was told never leaves their device")
    bundle = SessionBundle(session_id="s1", participant_id="p1", study_id="d",
                           video_path=video, metadata=_meta())
    summary = process_session(bundle, [(_MustNotRun(), {})], tmp_path / "out")
    assert not video.exists()
    assert summary["recording_refused"]["action"] == "deleted_unread"
    assert "never leaves their device" in summary["recording_refused"]["flag"]


def test_other_tiers_keep_their_recording_for_the_engines():
    b = SimpleNamespace(metadata=_meta("features_only"), video_path="x", audio_path=None)
    assert refuse_unconsented_recording(b) is None
    assert b.video_path == "x"


def test_no_video_is_explained_by_the_tier_when_there_is_one():
    b = SimpleNamespace(metadata=_meta())
    assert "features_in_browser" in no_video_eligibility(b).detail
    b = SimpleNamespace(metadata=_meta("media_retained"))
    assert "no recording" in no_video_eligibility(b).detail


def _browser_session(tmp_path):
    rows, spans = _synthetic_session()
    signals = tuple(SignalRow(stream="gaze", channel=r["channel"], native_clock_id="performance.now",
                              native_ts=r["master_ts"], value=r["value"],
                              reliability_tier="moderate") for r in rows)
    events = [{"event_type": f"{s.kind}_sampling", "onset_native_ts": s.start_ts,
               "offset_native_ts": s.end_ts, "stimulus_id": s.stimulus_id,
               "metadata": {"x": s.x, "y": s.y}} for s in spans]
    bundle = SessionBundle(session_id="s1", participant_id="p1", study_id="d",
                           events=events, metadata=_meta(),
                           browser_chunks=[Chunk(signals=signals)],
                           browser_chunk_sources=[BROWSER_FEATURE_SOURCE])
    writer = CanonicalWriter(tmp_path, SessionContext("s1", "p1", "d"))
    writer.set_session_metadata(bundle.metadata)
    return bundle, writer


def test_the_estimator_fits_on_browser_features_when_there_is_no_video(tmp_path):
    bundle, writer = _browser_session(tmp_path)
    out = run_gaze_from_browser(writer, bundle, _MustNotRun(), solution=UNALIGNED_VIDEO,
                                feature_channels=_gaze.FEATURE_CHANNELS,
                                no_video=no_video_eligibility(bundle))
    writer.close()
    assert out["status"] == "ok", out
    assert out["feature_source"] == BROWSER_FEATURE_SOURCE
    assert out["n_calibration_targets"] == 13
    assert out["average_offset_deg"] < 1.0

    sig = read_session(tmp_path, "s1").to_pylist()
    gaze_x = [r for r in sig if r["channel"] == "gaze.x"]
    assert gaze_x and all(r["master_ts"] is not None for r in gaze_x)

    runs = read_session(tmp_path, "s1", "runs").to_pylist()
    assert [r["status"] for r in runs] == ["ineligible"], "the server engine's absence is recorded"


def test_no_browser_features_is_a_recorded_refusal_not_an_error(tmp_path):
    bundle, writer = _browser_session(tmp_path)
    bundle.browser_chunk_sources = [None]          # the chunks are not gaze features
    out = run_gaze_from_browser(writer, bundle, _MustNotRun(), solution=UNALIGNED_VIDEO,
                                feature_channels=_gaze.FEATURE_CHANNELS,
                                no_video=no_video_eligibility(bundle))
    writer.close()
    assert out["status"] == "refused" and out["refusal"] == "no_browser_features"
    q = read_session(tmp_path, "s1", "quality").to_pylist()
    assert any(r["metric"] == "gaze_fit_refused" for r in q)

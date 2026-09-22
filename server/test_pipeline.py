"""End-to-end pipeline tests.

The M0 gate proven against real MediaPipe output over a real video file, not
synthetic chunks — a synthetic-chunk test can pass while the actual decode,
probe, or alignment path is broken.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from engine_contract.loader import load_engine_module
from engine_contract.media import describe_video, mean_luma

# By engine_id, never by sys.path order — see conftest.py.
MediaPipeBlendshapesBatch = load_engine_module(
    "face.mediapipe_blendshapes").MediaPipeBlendshapesBatch
from engine_contract import Chunk, SignalRow
from pipeline import MASTER_CLOCK, SessionBundle, build_registry, process_session
from synthetic_face import write_face_clip
from tables import read_session

REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = REPO_ROOT / "models" / "face_landmarker.task"


@pytest.fixture(scope="module")
def engine():
    if not MODEL_PATH.exists():
        pytest.skip(f"model not fetched: run `npm run models`")
    return MediaPipeBlendshapesBatch(MODEL_PATH)


@pytest.fixture(scope="module")
def clip_with_flash(tmp_path_factory) -> tuple[Path, int, float]:
    """A face-present clip with a flash at a known frame — a sync clapper.

    The face is drawn, not filmed. MediaPipe detects it (52 blendshapes), so
    the engine produces real signal rows, while the repo holds no identifiable
    biometric data — see synthetic_face.py.

    Returns (path, flash_frame_index, fps).
    """
    path = tmp_path_factory.mktemp("media") / "flash.mp4"
    fps, n_frames, flash_frame = 30.0, 90, 30
    write_face_clip(path, n_frames=n_frames, fps=fps, flash_frame=flash_frame)
    return path, flash_frame, fps


def _luma_series(video_path: Path) -> list[tuple[float, float]]:
    """Per-frame (native_ts_ms, mean_luma), as the aligner consumes it."""
    cap = cv2.VideoCapture(str(video_path))
    series: list[tuple[float, float]] = []
    idx = 0
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            series.append((idx * 1000.0 / fps, mean_luma(frame)))
            idx += 1
    finally:
        cap.release()
    return series


# ---------------------------------------------------------------------------
# alignment from a real video
# ---------------------------------------------------------------------------

def test_clapper_in_real_video_produces_an_anchor(clip_with_flash):
    path, flash_frame, fps = clip_with_flash
    expected_video_ts = flash_frame * 1000.0 / fps
    marker_master_ts = 12_345.0

    bundle = SessionBundle(
        session_id="s1", participant_id="p1", study_id="m0",
        video_path=path,
        events=[{"event_type": "sync_clapper", "onset_native_ts": marker_master_ts}],
    )
    reg = build_registry(bundle, video_luma=_luma_series(path))
    sol = reg.solve("video_pts")

    assert sol.aligned, "a clear flash should yield an anchor"
    # video_ts of the flash maps onto the master timestamp we drew it at.
    mapped, unc = sol.to_master(expected_video_ts)
    assert abs(mapped - marker_master_ts) < 50.0, f"mapped {mapped} vs {marker_master_ts}"
    assert unc >= 25.0, "one anchor cannot justify a tight error bar"


def test_missing_sync_event_leaves_video_unaligned(clip_with_flash):
    """No marker means no anchor — and that must be visible, not guessed."""
    path, _, _ = clip_with_flash
    bundle = SessionBundle(
        session_id="s1", participant_id="p1", study_id="m0",
        video_path=path, events=[],
    )
    sol = build_registry(bundle, video_luma=_luma_series(path)).solve("video_pts")

    assert not sol.aligned
    assert "no anchors" in sol.unaligned_reason


def test_flashless_video_leaves_video_unaligned(tmp_path):
    """The browser claims it flashed, but nothing is visible in the recording.

    A plausible real failure: the participant covered the camera, or the flash
    fell in a dropped frame. Must not silently align on the claim alone.
    """
    path = tmp_path / "noflash.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (320, 240))
    rng = np.random.default_rng(2)
    for _ in range(60):
        frame = np.clip(
            np.full((240, 320, 3), 90, dtype=np.int16)
            + rng.integers(-5, 5, (240, 320, 3)), 0, 255
        ).astype(np.uint8)
        writer.write(frame)
    writer.release()

    bundle = SessionBundle(
        session_id="s1", participant_id="p1", study_id="m0", video_path=path,
        events=[{"event_type": "sync_clapper", "onset_native_ts": 1000.0}],
    )
    sol = build_registry(bundle, video_luma=_luma_series(path)).solve("video_pts")
    assert not sol.aligned


# ---------------------------------------------------------------------------
# full pipeline
# ---------------------------------------------------------------------------

def test_pipeline_writes_all_canonical_tables(engine, clip_with_flash, tmp_path):
    path, _, _ = clip_with_flash
    bundle = SessionBundle(
        session_id="s_full", participant_id="p1", study_id="m0", video_path=path,
        events=[
            {"event_type": "sync_clapper", "onset_native_ts": 1000.0},
            {"event_type": "stimulus_onset", "onset_native_ts": 2000.0,
             "stimulus_id": "img_01"},
        ],
    )
    summary = process_session(
        bundle, [(engine, {})], tmp_path, video_luma=_luma_series(path)
    )

    assert summary["session_id"] == "s_full"
    assert summary["runs"], "the engine run must be recorded"
    assert summary["runs"][0]["status"] == "ok"

    events = read_session(tmp_path, "s_full", "events").to_pylist()
    types = {e["event_type"] for e in events}
    assert "sync_clapper" in types and "stimulus_onset" in types

    runs = read_session(tmp_path, "s_full", "runs").to_pylist()
    assert len(runs) == 1
    assert runs[0]["media_sha256"]


def test_stimulus_events_are_on_the_master_clock(engine, clip_with_flash, tmp_path):
    """Stimulus-relative timing is what the science depends on."""
    path, _, _ = clip_with_flash
    bundle = SessionBundle(
        session_id="s_ev", participant_id="p1", study_id="m0", video_path=path,
        events=[{"event_type": "stimulus_onset", "onset_native_ts": 2000.0,
                 "stimulus_id": "img_01"}],
    )
    process_session(bundle, [], tmp_path)

    ev = [
        e for e in read_session(tmp_path, "s_ev", "events").to_pylist()
        if e["event_type"] == "stimulus_onset"
    ]
    assert ev
    assert ev[0]["native_clock_id"] == MASTER_CLOCK
    assert ev[0]["onset_master_ts"] == pytest.approx(2000.0)


def test_m0_gate_end_to_end_real_engine(engine, clip_with_flash, tmp_path):
    """THE M0 GATE, against real MediaPipe output.

    One Parquet file, two `source` values for the same channel in one session,
    both on the master clock so they can be plotted against each other.
    """
    path, _, _ = clip_with_flash
    channel = "blendshape.mouthSmileLeft"
    browser_source = "face.mediapipe_blendshapes@0.1.0+browser-live"

    # Stand in for the browser pass: same channel, stamped on the master clock.
    browser_chunk = Chunk(signals=tuple(
        SignalRow(
            stream="face", channel=channel, native_clock_id=MASTER_CLOCK,
            native_ts=1000.0 + i * 33.3, value=0.05 * i,
            reliability_tier="moderate",
        )
        for i in range(10)
    ))

    bundle = SessionBundle(
        session_id="s_m0", participant_id="p1", study_id="m0", video_path=path,
        events=[{"event_type": "sync_clapper", "onset_native_ts": 1000.0}],
        browser_chunks=[browser_chunk],
        metadata={"browser_source": browser_source},
    )
    summary = process_session(
        bundle, [(engine, {})], tmp_path, video_luma=_luma_series(path)
    )

    rows = read_session(tmp_path, "s_m0", "signals").to_pylist()
    sources = {r["source"] for r in rows}

    assert browser_source in sources
    assert any(s.endswith("+server-batch") for s in sources), (
        f"server placement missing from {sources}"
    )
    assert len(sources) >= 2, "M0 requires two placements in one session"

    # Both placements must be expressed on the master clock, or the whole
    # exercise is pointless — unaligned rows cannot be compared.
    browser_rows = [r for r in rows if r["source"] == browser_source]
    assert browser_rows and all(r["master_ts"] is not None for r in browser_rows)

    server_rows = [r for r in rows if r["source"].endswith("+server-batch")]
    assert server_rows, "server engine produced no signal rows"
    assert all(r["master_ts"] is not None for r in server_rows), (
        "server rows must be aligned via the clapper anchor"
    )
    assert all(r["master_ts_uncertainty_ms"] is not None for r in server_rows)


def test_ineligible_engine_still_writes_a_run_row(engine, tmp_path):
    """A skipped engine must leave evidence, not silence."""
    tiny = tmp_path / "tiny.mp4"
    writer = cv2.VideoWriter(str(tiny), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (160, 120))
    for _ in range(10):
        writer.write(np.full((120, 160, 3), 100, dtype=np.uint8))
    writer.release()

    bundle = SessionBundle(
        session_id="s_inel", participant_id="p1", study_id="m0", video_path=tiny,
    )
    summary = process_session(bundle, [(engine, {})], tmp_path)

    assert summary["runs"][0]["status"] == "ineligible"
    runs = read_session(tmp_path, "s_inel", "runs").to_pylist()
    assert len(runs) == 1
    assert runs[0]["eligible"] is False
    assert "resolution_below_min" in runs[0]["ineligible_reasons"]
    assert runs[0]["eligibility_detail"]


def test_unaligned_session_records_reason_in_runs(engine, clip_with_flash, tmp_path):
    """No sync marker -> NULL master_ts, with the reason preserved."""
    path, _, _ = clip_with_flash
    bundle = SessionBundle(
        session_id="s_unal", participant_id="p1", study_id="m0",
        video_path=path, events=[],
    )
    summary = process_session(bundle, [(engine, {})], tmp_path)

    assert summary["runs"][0]["aligned"] is False
    runs = read_session(tmp_path, "s_unal", "runs").to_pylist()
    assert runs[0]["unaligned_reason"]
    assert runs[0]["clock_offset_ms"] is None

    rows = read_session(tmp_path, "s_unal", "signals").to_pylist()
    server = [r for r in rows if r["source"].endswith("+server-batch")]
    assert server and all(r["master_ts"] is None for r in server)
    assert all(r["native_ts"] is not None for r in server), (
        "native_ts stays authoritative even when unaligned"
    )


# ---------------------------------------------------------------------------
# consent enforcement
# ---------------------------------------------------------------------------

def _bundle_with(tmp_path, tier):
    """A bundle with a real file standing in for the recording."""
    from pipeline import SessionBundle

    video = tmp_path / "capture.webm"
    video.write_bytes(b"not really a video")
    audio = tmp_path / "capture.audio.wav"
    audio.write_bytes(b"not really audio")

    meta = {} if tier is None else {"consent": {"tier": tier}}
    return SessionBundle(session_id="s", participant_id="p", study_id="d",
                         video_path=video, audio_path=audio, metadata=meta)


def test_features_only_deletes_the_recording(tmp_path):
    """§6.5: raw video processed and discarded within the session by default.
    A tier written to a column and never acted on is not consent, it is a note
    about consent."""
    from pipeline import enforce_consent

    b = _bundle_with(tmp_path, "features_only")
    r = enforce_consent(b, {})

    assert r["action"] == "deleted_per_consent"
    assert r["media_deleted"] is True
    assert not b.video_path.exists()
    assert not b.audio_path.exists()


def test_media_retained_keeps_the_recording(tmp_path):
    from pipeline import enforce_consent

    b = _bundle_with(tmp_path, "media_retained")
    r = enforce_consent(b, {})

    assert r["action"] == "kept_per_consent"
    assert b.video_path.exists()


def test_transcript_tier_also_keeps_the_recording(tmp_path):
    from pipeline import enforce_consent

    b = _bundle_with(tmp_path, "media_plus_transcript")
    assert enforce_consent(b, {})["action"] == "kept_per_consent"
    assert b.video_path.exists()


def test_a_session_with_no_tier_keeps_its_media_and_says_so(tmp_path):
    """Deleting a participant's recording on the strength of a missing field is
    not a recoverable mistake. Refuse to guess, keep the file, flag it."""
    from pipeline import enforce_consent

    b = _bundle_with(tmp_path, None)
    r = enforce_consent(b, {})

    assert r["action"] == "kept_no_tier_recorded"
    assert r["media_deleted"] is False
    assert b.video_path.exists()

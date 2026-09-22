"""Tests for the server-batch placement.

Two tiers:
  - pure functions (euler_from_matrix, mean_luma) mirroring browser/pose.test.mjs
  - an end-to-end run over a synthetic video, so probe/run/quality are exercised
    against the real MediaPipe pipeline rather than a mock

Run:  .venv/Scripts/python.exe -m pytest engines/ -q
"""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from engine_contract.loader import load_engine_module

# Loaded by engine_id, never by sys.path order — see conftest.py.
_engine = load_engine_module("face.mediapipe_blendshapes")
MediaPipeBlendshapesBatch = _engine.MediaPipeBlendshapesBatch
describe_video = _engine.describe_video
euler_from_matrix = _engine.euler_from_matrix
mean_luma = _engine.mean_luma
from engine_contract import MediaDescriptor

REPO_ROOT = Path(__file__).resolve().parents[3]
MODEL_PATH = REPO_ROOT / "models" / "face_landmarker.task"

CLOSE = 1e-3


# --------------------------------------------------------------------------
# rotation helpers — row-major, matching MediaPipe's Python API
# --------------------------------------------------------------------------

def _rot_x(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4)
    m[:3, :3] = [[1, 0, 0], [0, c, -s], [0, s, c]]
    return m


def _rot_y(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4)
    m[:3, :3] = [[c, 0, s], [0, 1, 0], [-s, 0, c]]
    return m


def _rot_z(deg: float) -> np.ndarray:
    t = math.radians(deg)
    c, s = math.cos(t), math.sin(t)
    m = np.eye(4)
    m[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    return m


def test_identity_is_zero_rotation():
    yaw, pitch, roll = euler_from_matrix(np.eye(4))
    assert abs(yaw) < CLOSE and abs(pitch) < CLOSE and abs(roll) < CLOSE


@pytest.mark.parametrize("deg", [-60, -30, -5, 5, 30, 60])
def test_pure_yaw_isolated(deg):
    yaw, pitch, roll = euler_from_matrix(_rot_y(deg))
    assert abs(yaw - deg) < CLOSE, f"yaw {yaw} != {deg}"
    assert abs(pitch) < CLOSE, f"pitch leaked: {pitch}"
    assert abs(roll) < CLOSE, f"roll leaked: {roll}"


@pytest.mark.parametrize("deg", [-45, -20, 20, 45])
def test_pure_pitch_isolated(deg):
    """A nod must read as pitch, never as roll.

    Under the aerospace Z-Y-X convention this lands in roll instead — the exact
    bug the browser-side tests caught. Pinned here too so the two placements
    cannot silently diverge on convention.
    """
    yaw, pitch, roll = euler_from_matrix(_rot_x(deg))
    assert abs(pitch - deg) < CLOSE, f"pitch {pitch} != {deg}"
    assert abs(yaw) < CLOSE, f"yaw leaked: {yaw}"
    assert abs(roll) < CLOSE, f"roll leaked: {roll}"


@pytest.mark.parametrize("deg", [-40, -15, 15, 40])
def test_pure_roll_isolated(deg):
    yaw, pitch, roll = euler_from_matrix(_rot_z(deg))
    assert abs(roll - deg) < CLOSE, f"roll {roll} != {deg}"
    assert abs(yaw) < CLOSE, f"yaw leaked: {yaw}"
    assert abs(pitch) < CLOSE, f"pitch leaked: {pitch}"


def test_axes_independent_under_composition():
    expected = {"yaw": 25.0, "pitch": -15.0, "roll": 10.0}
    r = _rot_y(expected["yaw"]) @ _rot_x(expected["pitch"]) @ _rot_z(expected["roll"])
    yaw, pitch, roll = euler_from_matrix(r)
    got = {"yaw": yaw, "pitch": pitch, "roll": roll}
    for axis, want in expected.items():
        assert abs(got[axis] - want) < CLOSE, f"{axis}: {got[axis]} != {want}"


def test_matches_browser_placement_convention():
    """The two placements must agree, or the same video yields different pose.

    browser/pose.js takes a COLUMN-major flat array; this takes a row-major
    ndarray. Same rotation, different memory layout — verify they agree.
    """
    r = _rot_y(25.0) @ _rot_x(-15.0) @ _rot_z(10.0)
    yaw, pitch, roll = euler_from_matrix(r)

    # Emulate the JS side: flatten column-major, index [col*4 + row]
    flat = r.flatten(order="F")
    r02, r10, r11, r12, r22 = flat[8], flat[1], flat[5], flat[9], flat[10]
    js_pitch = math.degrees(math.atan2(-r12, math.hypot(r10, r11)))
    js_yaw = math.degrees(math.atan2(r02, r22))
    js_roll = math.degrees(math.atan2(r10, r11))

    assert abs(yaw - js_yaw) < CLOSE
    assert abs(pitch - js_pitch) < CLOSE
    assert abs(roll - js_roll) < CLOSE


def test_rejects_malformed_matrix():
    with pytest.raises(ValueError):
        euler_from_matrix(np.eye(3))


# --------------------------------------------------------------------------
# luminance
# --------------------------------------------------------------------------

def test_mean_luma_anchors():
    white = np.full((64, 64, 3), 255, dtype=np.uint8)
    black = np.zeros((64, 64, 3), dtype=np.uint8)
    assert abs(mean_luma(white) - 255) < 0.5
    assert mean_luma(black) < 0.5


def test_mean_luma_weights_green_most():
    def solid(b, g, r):
        img = np.zeros((64, 64, 3), dtype=np.uint8)
        img[:, :] = (b, g, r)  # OpenCV is BGR
        return img

    assert mean_luma(solid(0, 255, 0)) > mean_luma(solid(0, 0, 255))
    assert mean_luma(solid(0, 0, 255)) > mean_luma(solid(255, 0, 0))


def test_mean_luma_discriminates_the_bias_threshold():
    """§2.5 — the rPPG skin-tone gap largely closes above luminance 30."""
    dim = np.full((64, 64, 3), 20, dtype=np.uint8)
    lit = np.full((64, 64, 3), 40, dtype=np.uint8)
    assert mean_luma(dim) < 30
    assert mean_luma(lit) > 30


# --------------------------------------------------------------------------
# probe()
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def batch_engine():
    if not MODEL_PATH.exists():
        pytest.skip(f"model not fetched: {MODEL_PATH} (run tools/fetch_models.py)")
    return MediaPipeBlendshapesBatch(MODEL_PATH)


def _descriptor(**overrides) -> MediaDescriptor:
    base = dict(
        path="dummy.mp4", kind="video", sha256="0" * 64, duration_s=10.0,
        fps=30.0, width=640, height=480, mean_roi_luminance=120.0,
    )
    base.update(overrides)
    return MediaDescriptor(**base)


def test_probe_accepts_good_media(batch_engine):
    e = batch_engine.probe(_descriptor())
    assert e.eligible and not e.reasons


def test_probe_rejects_low_fps_with_a_reason(batch_engine):
    """§5.3 uses 5 Hz as a published exclusion threshold."""
    e = batch_engine.probe(_descriptor(fps=3.0))
    assert not e.eligible
    assert "fps_below_min" in e.reasons
    assert "3.0 fps" in e.detail


def test_probe_rejects_low_resolution(batch_engine):
    e = batch_engine.probe(_descriptor(width=160, height=120))
    assert not e.eligible
    assert "resolution_below_min" in e.reasons


def test_probe_warns_on_low_luminance_without_blocking(batch_engine):
    """Dim video still yields usable blendshapes, so this warns rather than blocks.

    But it must be RECORDED — §2.5 bias risk has to be visible at analysis time,
    not silently absent.
    """
    e = batch_engine.probe(_descriptor(mean_roi_luminance=12.0))
    assert e.eligible, "low luminance should warn, not block"
    assert "bias" in e.detail.lower()
    assert "12.0" in e.detail


def test_probe_returns_rather_than_raises_on_wrong_kind(batch_engine):
    e = batch_engine.probe(_descriptor(kind="audio"))
    assert not e.eligible
    assert "wrong_media_kind" in e.reasons


# --------------------------------------------------------------------------
# end-to-end over a synthetic video
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory) -> Path:
    """A short clip with no real face in it.

    Deliberate: it exercises decode, timestamping, quality accounting and the
    face_lost path without needing a consented human recording in the test
    suite. Face-present assertions belong in a separate fixture-video test.
    """
    path = tmp_path_factory.mktemp("media") / "synthetic.mp4"
    fps, n_frames, w, h = 30.0, 90, 640, 480
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    rng = np.random.default_rng(0)
    for i in range(n_frames):
        frame = np.full((h, w, 3), 100, dtype=np.uint8)
        frame += rng.integers(-8, 8, frame.shape, dtype=np.int16).astype(np.uint8)
        cv2.circle(frame, (w // 2, h // 2), 80 + i % 10, (160, 170, 180), -1)
        writer.write(frame)
    writer.release()
    assert path.exists() and path.stat().st_size > 0
    return path


def test_describe_video_probes_real_file(synthetic_video):
    d = describe_video(synthetic_video)
    assert d.kind == "video"
    assert d.width == 640 and d.height == 480
    assert d.fps and abs(d.fps - 30.0) < 1.0
    assert len(d.sha256) == 64
    assert d.mean_roi_luminance is not None


def test_run_produces_quality_rows_even_with_no_face(batch_engine, synthetic_video):
    """A faceless clip must still yield quality rows and a face_lost event.

    Silence would be the wrong output — §2.2's whole point is that low
    face-detection yield is a measurable property of the session, not an
    absence of data.
    """
    d = describe_video(synthetic_video)
    chunks = list(batch_engine.run(d))

    quality = [q for c in chunks for q in c.quality]
    events = [e for c in chunks for e in c.events]

    metrics = {q.metric for q in quality}
    assert "achieved_fps" in metrics
    assert "face_detect_rate" in metrics
    assert "mean_luminance" in metrics

    rates = [q.value for q in quality if q.metric == "face_detect_rate"]
    assert rates and all(r == 0.0 for r in rates), "no face present, so rate must be 0"

    assert any(e.event_type == "face_lost" for e in events)
    lost = next(e for e in events if e.event_type == "face_lost")
    assert lost.offset_native_ts is not None, "face_lost must be closed at flush"
    assert lost.offset_native_ts > lost.onset_native_ts


def test_run_timestamps_are_monotonic(batch_engine, synthetic_video):
    """MediaPipe's VIDEO mode requires strictly increasing timestamps.

    Some containers report a flat or non-monotonic PTS, which the engine
    compensates for — verify the compensation actually holds.
    """
    d = describe_video(synthetic_video)
    ts = [
        row.window_end_native_ts
        for c in batch_engine.run(d)
        for row in c.quality
    ]
    assert ts == sorted(ts), "quality window timestamps must be non-decreasing"


def test_achieved_fps_is_measured_not_assumed(batch_engine, synthetic_video):
    """§2.1: rate is device- and load-dependent and must be measured per session."""
    d = describe_video(synthetic_video)
    fps_rows = [
        q.value for c in batch_engine.run(d) for q in c.quality if q.metric == "achieved_fps"
    ]
    assert fps_rows
    # Synthetic clip is a true 30 fps; allow slack for window boundaries.
    assert all(10.0 < v < 60.0 for v in fps_rows), f"implausible fps: {fps_rows}"


def test_source_distinguishes_placement(batch_engine):
    """The M0 success criterion depends on the two placements not colliding."""
    assert batch_engine.source.endswith("+server-batch")
    assert batch_engine.manifest.engine_id == "face.mediapipe_blendshapes"
    # Same engine_id, different source — that is the point.
    assert batch_engine.manifest.source in batch_engine.source

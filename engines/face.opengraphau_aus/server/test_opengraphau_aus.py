"""Tests for the OpenGraphAU engine's contract behaviour.

The network's accuracy is not ours to assert. What is ours: that it loads the
checkpoint it claims to or refuses, that its channel names pair with Py-Feat's
without colliding with each other, that the face lands where the template says,
and that it never emits an emotion.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from engine_contract import MediaDescriptor
from engine_contract.au_reliability import normalise, reliability
from engine_contract.loader import load_engine_module

_engine = load_engine_module("face.opengraphau_aus")
OpenGraphAUs = _engine.OpenGraphAUs
gm = _engine._load_model_module()

ROOT = Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "models" / "opengraphau" / "OpenGprahAU-ResNet50_second_stage.pth"
LANDMARKER = ROOT / "models" / "face_landmarker.task"

#: What face.pyfeat_aus emits with its default xgb model.
PYFEAT_AUS = {"AU01", "AU02", "AU04", "AU05", "AU06", "AU07", "AU09", "AU10",
              "AU11", "AU12", "AU14", "AU15", "AU17", "AU20", "AU23", "AU24",
              "AU25", "AU26", "AU28", "AU43"}


def engine() -> OpenGraphAUs:
    return OpenGraphAUs(WEIGHTS, LANDMARKER)


def media(**kw) -> MediaDescriptor:
    base = dict(path="x.webm", kind="video", sha256="0" * 64, duration_s=10.0,
                fps=30.0, width=1280, height=720, mean_roi_luminance=140.0)
    base.update(kw)
    return MediaDescriptor(**base)


# ---------------------------------------------------------------------------
# channel names: pair with Py-Feat, never with each other
# ---------------------------------------------------------------------------

def test_every_output_column_gets_a_distinct_channel():
    """41 columns, 41 names. The digits-only normaliser gave 34 — the seven
    left AUs and seven right AUs folded onto their bilateral channels."""
    keys = [normalise(f"AU{a}") for a in gm.MAIN_AUS + gm.LATERAL_AUS]
    assert len(keys) == 41
    assert len(set(keys)) == 41


def test_the_shared_aus_pair_with_pyfeat_by_name():
    """Agreement pairs sources by channel name, so a shared AU must be spelled
    identically by both engines or §2.2's cross-check silently measures
    nothing for it."""
    ours = {normalise(f"AU{a}") for a in gm.MAIN_AUS}
    shared = ours & PYFEAT_AUS
    assert len(shared) == 18
    assert {"AU06", "AU12", "AU14", "AU20", "AU23"} <= shared


def test_lateral_units_are_tiered_low_not_inherited():
    assert reliability(normalise("AUL12")).tier == "low"
    assert reliability(normalise("AU12")).tier == "high"


def test_no_declared_output_is_an_emotion():
    channels = [s.channel for s in engine().manifest.outputs.signals]
    banned = ("emotion", "happy", "sad", "anger", "angry", "fear",
              "disgust", "surprise", "valence", "arousal")
    for ch in channels:
        assert not any(b in ch.lower() for b in banned), ch


def test_outputs_are_declared_as_occurrence_not_intensity():
    """A cosine similarity thresholded at 0.5 upstream. Calling it an intensity
    would invite exactly the absolute reading §2.2 warns against."""
    spec = next(s for s in engine().manifest.outputs.signals if s.channel == "au.*")
    assert spec.unit == "probability"
    assert "not intensities" in (spec.description or "")


# ---------------------------------------------------------------------------
# alignment lands the face on the measured template
# ---------------------------------------------------------------------------

def _apply(m, p):
    return m[:, :2] @ np.asarray(p, float) + m[:, 2]


@pytest.mark.parametrize("tilt_deg", [0.0, 12.0, -20.0])
def test_eyes_land_on_the_template(tilt_deg):
    mid = np.array([640.0, 330.0])
    half = 45.0
    t = math.radians(tilt_deg)
    d = np.array([math.cos(t), math.sin(t)]) * half
    left, right = mid - d, mid + d

    m = _engine.alignment_matrix(left, right)
    l2, r2 = _apply(m, left), _apply(m, right)

    offset = (_engine.TEMPLATE_SIDE - _engine.CROP_SIDE) / 2
    want_mid = np.array(_engine.TEMPLATE_EYE_MID) * _engine.TEMPLATE_SIDE - offset
    assert np.allclose((l2 + r2) / 2, want_mid, atol=1e-6)
    assert abs(l2[1] - r2[1]) < 1e-6, "eye line is not level"
    assert l2[0] < r2[0], "the face was mirrored or turned upside down"
    assert math.isclose(np.linalg.norm(r2 - l2),
                        _engine.TEMPLATE_IOD * _engine.TEMPLATE_SIDE, rel_tol=1e-9)


def test_coincident_eyes_are_refused():
    with pytest.raises(ValueError, match="coincide"):
        _engine.alignment_matrix(np.array([5.0, 5.0]), np.array([5.0, 5.0]))


def _fake_landmarks(left, right):
    pts = np.zeros((478, 2))
    for i in _engine.IMAGE_LEFT_EYE:
        pts[i] = left
    for i in _engine.IMAGE_RIGHT_EYE:
        pts[i] = right
    return pts


def test_a_centred_face_is_analysed_on_recorded_pixels_only():
    frame = np.full((720, 1280, 3), 128, np.uint8)
    crop, outside = _engine.align_face(frame, _fake_landmarks([600, 330], [680, 330]))
    assert crop.shape == (224, 224, 3)
    assert outside == 0.0


def test_a_face_at_the_edge_reports_the_invented_pixels():
    """warpAffine fills off-frame pixels with black and says nothing. The engine
    has to say it instead."""
    frame = np.full((720, 1280, 3), 128, np.uint8)
    _, outside = _engine.align_face(frame, _fake_landmarks([5, 330], [85, 330]))
    assert 0.3 < outside < 0.7


def test_a_small_face_is_shrunk_before_warping_without_moving():
    """The antialiasing pre-shrink must not change the geometry: the eyes
    should land on the same template pixels either way."""
    frame = np.zeros((720, 1280, 3), np.uint8)
    for x in (400, 880):
        frame[300:310, x - 5:x + 5] = 255     # two bright "eyes" 480px apart
    crop, _ = _engine.align_face(frame, _fake_landmarks([400, 305], [880, 305]))
    bright = np.argwhere(crop.max(axis=2) > 60)
    left_blob = bright[bright[:, 1] < 112].mean(axis=0)
    right_blob = bright[bright[:, 1] >= 112].mean(axis=0)
    iod = _engine.TEMPLATE_IOD * _engine.TEMPLATE_SIDE
    assert abs((right_blob[1] - left_blob[1]) - iod) < 2.0


# ---------------------------------------------------------------------------
# the checkpoint is the one the manifest names, loaded whole, or nothing
# ---------------------------------------------------------------------------

def test_missing_weights_are_refused_with_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="npm run models"):
        _engine.verify_weights(tmp_path / "absent.pth", "0" * 64)


def test_a_different_checkpoint_is_refused(tmp_path):
    """Google Drive links can be re-pointed. A different file under this
    engine's name and version would make every row it writes misattributed."""
    f = tmp_path / "w.pth"
    f.write_bytes(b"not the checkpoint")
    with pytest.raises(ValueError, match="different checkpoint"):
        _engine.verify_weights(f, "0" * 64)


def test_a_manifest_without_a_hash_is_refused(tmp_path):
    f = tmp_path / "w.pth"
    f.write_bytes(b"x")
    with pytest.raises(ValueError, match="refusing to guess"):
        _engine.verify_weights(f, None)


def test_a_partial_checkpoint_does_not_load(tmp_path):
    """Upstream loads with strict=False. Measured: the stage-2 checkpoint
    loaded into the stage-1 architecture, as upstream's demo does, leaves 8
    tensors random and drops 49 — and still runs. This load must raise."""
    import torch
    state = gm.MEFARG().state_dict()
    state.pop(next(k for k in state if k.startswith("head.gnn")))
    path = tmp_path / "partial.pth"
    torch.save({"state_dict": state}, path)
    with pytest.raises(RuntimeError, match="Missing key"):
        gm.load_checkpoint(path)


def test_a_dataparallel_prefix_is_tolerated(tmp_path):
    """The released checkpoints were saved from DataParallel ('module.' keys).
    Stripping that is a rename, not a partial load."""
    import torch
    state = {f"module.{k}": v for k, v in gm.MEFARG().state_dict().items()}
    path = tmp_path / "dp.pth"
    torch.save({"state_dict": state}, path)
    assert gm.load_checkpoint(path) is not None


def test_the_manifest_hash_matches_the_fetcher():
    """Two places pin the checkpoint. If they drift, `npm run models` fetches a
    file the engine then refuses — at the first session instead of at setup."""
    spec = importlib.util.spec_from_file_location(
        "fetch_models_for_test", ROOT / "tools" / "fetch_models.py")
    fm = importlib.util.module_from_spec(spec)
    # Registered first: a dataclass resolves its annotations via sys.modules.
    sys.modules[spec.name] = fm
    spec.loader.exec_module(fm)
    pinned = next(m.sha256 for m in fm.MODELS if m.name == "opengraphau_r50_s2")
    assert pinned == engine().manifest.provenance.weights_sha256


@pytest.mark.skipif(not WEIGHTS.exists(), reason="weights not fetched (npm run models)")
def test_the_real_checkpoint_loads_strictly_and_scores_in_range():
    import torch
    _engine.verify_weights(WEIGHTS, engine().manifest.provenance.weights_sha256)
    net = gm.load_checkpoint(WEIGHTS)
    with torch.no_grad():
        out = net(torch.zeros(2, 3, 224, 224)).numpy()
    assert out.shape == (2, 41)
    assert np.all(out >= -1e-6) and np.all(out <= 1 + 1e-6)


# ---------------------------------------------------------------------------
# probe and licence
# ---------------------------------------------------------------------------

def test_probe_accepts_usable_media():
    assert engine().probe(media()).eligible


def test_probe_refuses_below_the_luminance_floor():
    e = engine().probe(media(mean_roi_luminance=12.0))
    assert not e.eligible
    assert "luminance_below_min" in e.reasons


def test_probe_returns_ineligibility_rather_than_raising():
    e = engine().probe(media(kind="audio"))
    assert e.eligible is False
    assert e.detail


def test_licence_is_apache_code_with_unverified_weights():
    lic = engine().manifest.license
    assert lic.spdx == "Apache-2.0"
    assert lic.commercial_use == "unknown"
    assert "NOT individually verified" in (lic.notes or "")


def test_the_vendored_code_keeps_its_notice():
    """Apache-2.0 §4: keep the notice and state the changes."""
    text = (Path(_engine.__file__).parent / "graphau_model.py").read_text(encoding="utf-8")
    assert "Apache License, Version 2.0" in text
    assert "Modifications" in text
    assert "a0ad10d516ed121f476cbc6d66a84ebfc033a53f" in text

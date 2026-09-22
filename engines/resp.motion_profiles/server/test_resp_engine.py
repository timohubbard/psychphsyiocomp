"""Tests for the respiration engine's contract behaviour and ROI logic.

The signal-processing core is tested in server/test_respiration.py. What these
cover is the part specific to this engine: locating a shoulder line, falling
back honestly when it cannot, and — above all — not emitting a breathing rate.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from engine_contract import MediaDescriptor
from engine_contract.loader import load_engine_module

_engine = load_engine_module("resp.motion_profiles")
RespirationMotionProfiles = _engine.RespirationMotionProfiles
cell_profiles = _engine.cell_profiles
fallback_roi = _engine.fallback_roi
roi_from_shoulders = _engine.roi_from_shoulders

MODEL = Path("models/pose_landmarker.task")


class LM:
    def __init__(self, x, y):
        self.x, self.y = x, y


def shoulders(lx=0.35, ly=0.45, rx=0.65, ry=0.45, n=33):
    pts = [LM(0.5, 0.5) for _ in range(n)]
    pts[11] = LM(lx, ly)
    pts[12] = LM(rx, ry)
    return pts


def media(**kw) -> MediaDescriptor:
    base = dict(path="v.webm", kind="video", sha256="0" * 64, duration_s=60.0,
                fps=30.0, width=1280, height=720, mean_roi_luminance=140.0)
    base.update(kw)
    return MediaDescriptor(**base)


def engine():
    return RespirationMotionProfiles(MODEL)


# ---------------------------------------------------------------------------
# it does not emit a breathing rate
# ---------------------------------------------------------------------------

def test_rate_is_off_by_default():
    """§2.4: after two dedicated research passes, NO verified breaths-per-minute
    figure against a chest belt, RIP or spirometry survived adversarial checking
    — and one specific figure was explicitly REFUTED. A breathing rate is a
    number a clinician recognises on sight, and shipping one this project cannot
    defend would be the most damaging thing it could do.
    """
    raw = json.loads((Path(_engine.__file__).resolve().parent.parent
                      / "engine.manifest.json").read_text(encoding="utf-8"))
    assert raw["params_schema"]["properties"]["emit_rate_bpm"]["default"] is False


def test_no_declared_channel_is_a_breathing_rate():
    channels = {s.channel for s in engine().manifest.outputs.signals}
    assert not any("bpm" in c or "rate" in c for c in channels)
    assert "respiration.waveform" in channels


def test_the_manifest_states_why_rather_than_omitting_it():
    raw = json.loads((Path(_engine.__file__).resolve().parent.parent
                      / "engine.manifest.json").read_text(encoding="utf-8"))
    note = raw["capability_notes"]["no_validated_rate"]
    assert "refuted" in note.lower()
    assert "validation study" in note.lower()


def test_the_waveform_is_tiered_low():
    """No verified accuracy figure exists for this method anywhere. A moderate
    tier would imply one does."""
    spec = next(s for s in engine().manifest.outputs.signals
                if s.channel == "respiration.waveform")
    assert spec.reliability_tier == "low"


def test_confidence_channels_accompany_the_waveform():
    """Non-negotiable per the build plan: since no accuracy figure exists, a
    calibrated confidence channel is what makes the output shippable at all.
    The claim is 'here is the signal and how much to trust it'."""
    channels = {s.channel for s in engine().manifest.outputs.signals}
    assert {"respiration.periodicity", "respiration.cells_used",
            "respiration.gross_motion"} <= channels


# ---------------------------------------------------------------------------
# ROI
# ---------------------------------------------------------------------------

def test_the_roi_sits_below_the_shoulder_line():
    box = roi_from_shoulders(shoulders(), 1280, 720)
    left, top, right, bottom = box
    assert top >= 720 * 0.45 - 40, "ROI starts above the shoulders"
    assert bottom > top and right > left


def test_the_roi_spans_the_shoulders_horizontally():
    left, _, right, _ = roi_from_shoulders(shoulders(lx=0.3, rx=0.7), 1280, 720)
    assert left == pytest.approx(1280 * 0.3, abs=2)
    assert right == pytest.approx(1280 * 0.7, abs=2)


def test_shoulder_order_does_not_matter():
    a = roi_from_shoulders(shoulders(lx=0.3, rx=0.7), 1280, 720)
    b = roi_from_shoulders(shoulders(lx=0.7, rx=0.3), 1280, 720)
    assert a == b


def test_a_participant_too_far_away_yields_no_roi():
    """A shoulder span of a few pixels cannot carry sub-pixel chest motion."""
    assert roi_from_shoulders(shoulders(lx=0.50, rx=0.505), 1280, 720) is None


def test_missing_landmarks_yield_no_roi_rather_than_an_index_error():
    assert roi_from_shoulders(None, 1280, 720) is None
    assert roi_from_shoulders([LM(0.5, 0.5)] * 5, 1280, 720) is None


def test_the_fallback_is_a_torso_band_inside_the_frame():
    """Most at-home framing is head-and-shoulders, so shoulder-line motion is
    often the only chest signal available — a different regime from the clinical
    chest-camera papers, and probably why no published figure transfers."""
    left, top, right, bottom = fallback_roi(1280, 720)
    assert 0 <= left < right <= 1280
    assert 0 <= top < bottom <= 720
    assert top > 720 * 0.4, "fallback band should sit below the head"


# ---------------------------------------------------------------------------
# motion profiles
# ---------------------------------------------------------------------------

def test_a_profile_is_produced_per_grid_cell():
    frames = [np.zeros((64, 64), dtype=np.uint8) for _ in range(5)]
    profiles = cell_profiles(frames, (4, 4))
    assert profiles.shape == (16, 4)


def test_a_static_scene_produces_no_motion():
    rng = np.random.default_rng(0)
    still = rng.integers(0, 255, (64, 64), dtype=np.uint8)
    profiles = cell_profiles([still.copy() for _ in range(6)], (4, 4))
    assert np.abs(profiles).max() < 0.5


def test_vertical_movement_registers_in_the_profiles():
    """Breathing moves the shoulder line up and down; only the vertical flow
    component is kept, because horizontal is dominated by postural sway and by
    the participant turning to read the screen."""
    rng = np.random.default_rng(1)
    base = rng.integers(0, 255, (96, 96), dtype=np.uint8)
    frames = [np.roll(base, shift, axis=0) for shift in (0, 2, 4, 2, 0)]

    profiles = cell_profiles(frames, (4, 4))
    assert np.abs(profiles).max() > 0.3


def test_too_few_frames_returns_an_empty_profile_set():
    assert cell_profiles([np.zeros((32, 32), dtype=np.uint8)], (4, 4)).shape == (16, 0)


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

def test_probe_accepts_usable_video():
    assert engine().probe(media()).eligible


def test_probe_refuses_below_the_luminance_floor():
    e = engine().probe(media(mean_roi_luminance=11.0))
    assert not e.eligible
    assert "luminance_below_min" in e.reasons


def test_probe_refuses_below_the_sampling_floor():
    e = engine().probe(media(fps=3.0))
    assert not e.eligible
    assert "fps_below_min" in e.reasons


def test_probe_refuses_audio():
    assert not engine().probe(media(kind="audio")).eligible


# ---------------------------------------------------------------------------
# legal framing
# ---------------------------------------------------------------------------

def test_the_manifest_flags_the_higher_legal_risk():
    """§6.3: respiration output is plausibly health data under GDPR Art. 4(15)
    even without an identification purpose, because Art. 9's health-data limb
    does not carry the same identification qualifier as the biometric limb."""
    raw = json.loads((Path(_engine.__file__).resolve().parent.parent
                      / "engine.manifest.json").read_text(encoding="utf-8"))
    note = raw["capability_notes"]["legal_risk"]
    assert "health data" in note.lower()
    assert "4(15)" in note

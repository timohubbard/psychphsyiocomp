"""Tests for the Py-Feat AU engine's contract behaviour.

The detector itself is not exercised here — it is a 2GB model stack and its
correctness is not ours to assert. What IS ours, and what these check, is that
the engine refuses an identity model, tiers every AU from the published floor
rather than uniformly, and never emits an emotion.
"""

from __future__ import annotations

import pytest

from engine_contract import MediaDescriptor
from engine_contract.au_reliability import reliability
from engine_contract.loader import load_engine_module

_engine = load_engine_module("face.pyfeat_aus")
IDENTITY_MODELS = _engine.IDENTITY_MODELS
PyFeatAUs = _engine.PyFeatAUs
check_no_identity_model = _engine.check_no_identity_model


def media(**kw) -> MediaDescriptor:
    base = dict(path="x.webm", kind="video", sha256="0" * 64, duration_s=10.0,
                fps=30.0, width=1280, height=720, mean_roi_luminance=140.0)
    base.update(kw)
    return MediaDescriptor(**base)


# ---------------------------------------------------------------------------
# identity models are refused, not merely discouraged
# ---------------------------------------------------------------------------

def test_an_identity_model_is_refused():
    """Py-Feat DEFAULTS identity_model='arcface' — a face recognition model
    carrying a non-commercial weight, loaded unless you say otherwise.

    Raised rather than warned, because an identity model is not a worse AU
    detector. It is a different capability with different consent implications:
    a participant who agreed to have their brow movement measured did not agree
    to be recognised.
    """
    for bad in ("arcface", "ArcFace", "insightface", "facenet"):
        with pytest.raises(ValueError, match="identity"):
            check_no_identity_model({"face_model": bad})


def test_a_legitimate_detector_stack_passes():
    check_no_identity_model({
        "face_model": "retinaface", "landmark_model": "mobilefacenet",
        "au_model": "xgb",
    })


def test_every_identity_model_name_is_covered():
    """The list is what the manifest's licence note claims the code enforces."""
    assert {"arcface", "insightface", "facenet"} <= set(IDENTITY_MODELS)


def test_mobilefacenet_is_not_mistaken_for_an_identity_model():
    """Caught by this suite on first run. `mobilefacenet` is a LANDMARK backbone
    and contains the substring "facenet"; a substring rule rejected the default
    legitimate stack while looking like a careful safety check. A guard that
    over-matches gets switched off, and then guards nothing.
    """
    check_no_identity_model({"landmark_model": "mobilefacenet"})


def test_an_identity_model_passed_as_identity_model_is_also_refused():
    """Py-Feat's own parameter for it, which is where it would actually arrive."""
    with pytest.raises(ValueError, match="identity"):
        check_no_identity_model({"identity_model": "arcface"})


# ---------------------------------------------------------------------------
# the engine never emits an emotion
# ---------------------------------------------------------------------------

def test_no_declared_output_is_an_emotion():
    """§2.2, Barrett et al. 2019: emotion categories are "not ... diagnostic
    displays of any emotional state". Coherence r = .32; the hypothesised
    configuration appears in only ~19% of episodes. AU→emotion belongs in a
    separate, explicitly-toggleable engine so a study that wants it must say so
    — and EU AI Act Recital 18 excludes expression detection *unless used to
    infer emotion*, which makes the boundary a compliance surface too.
    """
    channels = [s.channel for s in PyFeatAUs().manifest.outputs.signals]
    banned = ("emotion", "happy", "sad", "anger", "angry", "fear",
              "disgust", "surprise", "valence", "arousal")
    for ch in channels:
        assert not any(b in ch.lower() for b in banned), ch


def test_the_engine_declares_aus_and_a_detection_flag_only():
    channels = {s.channel for s in PyFeatAUs().manifest.outputs.signals}
    assert channels == {"au.*", "face.detected"}


def test_face_detected_is_emitted_as_a_signal():
    """§2.2 measured valid-face-frame yield at 43% vs 62-63% between engines on
    identical video. The denominator is itself a finding, so it is recorded
    rather than left implicit in the absence of AU rows."""
    specs = {s.channel: s for s in PyFeatAUs().manifest.outputs.signals}
    assert "face.detected" in specs


# ---------------------------------------------------------------------------
# reliability is per AU
# ---------------------------------------------------------------------------

def test_the_engine_tiers_aus_from_the_shared_table():
    """Tiers must come from the contract, not from this engine, or Py-Feat and
    OpenFace would disagree about how much to trust the same AU."""
    assert reliability("AU12").tier == "high"
    assert reliability("AU20").tier == "low"
    assert reliability("AU12").tier != reliability("AU20").tier


def test_the_spec_level_tier_is_only_a_default():
    """The row-level tier is what matters; the spec cannot express per-AU."""
    spec = next(s for s in PyFeatAUs().manifest.outputs.signals if s.channel == "au.*")
    assert "default" in (spec.description or "").lower()


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

def test_probe_accepts_usable_media():
    assert PyFeatAUs().probe(media()).eligible


def test_probe_refuses_below_the_luminance_floor():
    """§2.5 is the evidence base's only quantified bias mitigation, so this is a
    fairness control rather than a picture-quality preference."""
    e = PyFeatAUs().probe(media(mean_roi_luminance=12.0))
    assert not e.eligible
    assert "luminance_below_min" in e.reasons


def test_probe_refuses_below_the_sampling_floor():
    e = PyFeatAUs().probe(media(fps=3.0))
    assert not e.eligible
    assert "fps_below_min" in e.reasons


def test_probe_returns_ineligibility_rather_than_raising():
    """Ineligibility is recorded as a run row, never a silent skip or a crash."""
    e = PyFeatAUs().probe(media(kind="audio"))
    assert e.eligible is False
    assert e.detail


# ---------------------------------------------------------------------------
# licence honesty
# ---------------------------------------------------------------------------

def test_commercial_use_is_unknown_not_yes():
    """Py-Feat's code is MIT, but the AU model weights' own licence was never
    separately confirmed. The licence tool buckets unknown as unverified rather
    than permissive, which is the safe direction."""
    lic = PyFeatAUs().manifest.license
    assert lic.spdx == "MIT"
    assert lic.commercial_use == "unknown"
    assert "ArcFace" in (lic.notes or "") or "arcface" in (lic.notes or "").lower()

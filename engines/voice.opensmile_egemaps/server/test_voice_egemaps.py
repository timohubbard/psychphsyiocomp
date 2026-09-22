"""Tests for the eGeMAPS voice engine.

openSMILE's own feature extraction is not exercised here; its correctness is not
ours to assert. What IS ours: that the engine never claims valence, that it
records whether speech content survived capture, and that it decides what counts
as speech from the session's own noise floor rather than a fixed level.
"""

from __future__ import annotations

import numpy as np
import pytest

from engine_contract import MediaDescriptor
from engine_contract.loader import load_engine_module

_engine = load_engine_module("voice.opensmile_egemaps")
ABSOLUTE_RMS_FLOOR = _engine.ABSOLUTE_RMS_FLOOR
OpenSmileEGeMAPS = _engine.OpenSmileEGeMAPS
SPEECH_CRITICAL_CONSTRAINTS = _engine.SPEECH_CRITICAL_CONSTRAINTS
speech_content_preserved = _engine.speech_content_preserved
voiced_threshold = _engine.voiced_threshold

CLEAN = {"noiseSuppression": False, "autoGainControl": False, "echoCancellation": False}


def media(**kw) -> MediaDescriptor:
    base = dict(path="a.wav", kind="audio", sha256="0" * 64, duration_s=120.0,
                applied_audio_constraints=dict(CLEAN))
    base.update(kw)
    return MediaDescriptor(**base)


# ---------------------------------------------------------------------------
# it never claims valence
# ---------------------------------------------------------------------------

def test_no_declared_channel_is_a_valence_channel():
    """§2.3, Wagner et al. 2023 (IEEE TPAMI): transformer SER's valence
    performance is driven by implicit LINGUISTIC content, not prosody.
    Re-synthesising utterances from transcripts — same words, prosody stripped —
    left the correlation nearly intact; freezing the transformer collapsed it to
    near zero.

    A pipeline keeping only eGeMAPS-style hand-crafted features has discarded
    exactly that mechanism. So this engine cannot support valence at any
    accuracy, ever, and must not name a channel implying otherwise.
    """
    channels = [s.channel for s in OpenSmileEGeMAPS().manifest.outputs.signals]
    banned = ("valence", "sentiment", "positivity", "emotion", "mood", "happy")
    for ch in channels:
        assert not any(b in ch.lower() for b in banned), ch


def test_the_manifest_states_the_capability_limit_rather_than_omitting_it():
    """Silence about a limit reads as absence of one."""
    import json
    from pathlib import Path

    raw = json.loads((Path(_engine.__file__).resolve().parent.parent
                      / "engine.manifest.json").read_text(encoding="utf-8"))
    note = raw["capability_notes"]["cannot_support_valence"]
    assert "linguistic" in note.lower()
    assert "arousal" in note.lower()


# ---------------------------------------------------------------------------
# speech content preservation
# ---------------------------------------------------------------------------

def test_clean_constraints_preserve_speech_content():
    preserved, why = speech_content_preserved(CLEAN)
    assert preserved is True and why is None


def test_noise_suppression_means_speech_content_was_not_preserved():
    preserved, why = speech_content_preserved({**CLEAN, "noiseSuppression": True})
    assert preserved is False
    assert "noiseSuppression" in why


def test_gain_control_also_counts():
    """AGC rescales exactly the loudness features eGeMAPS measures."""
    preserved, _ = speech_content_preserved({**CLEAN, "autoGainControl": True})
    assert preserved is False


def test_missing_constraints_count_as_not_preserved():
    """§5.2: the spec permits a UA to ignore a constraint without failing, so
    absence of evidence is not evidence of absence — and the cost of guessing
    wrong is a valence channel that silently measures nothing."""
    assert speech_content_preserved(None)[0] is False
    assert speech_content_preserved({})[0] is False
    assert speech_content_preserved({"noiseSuppression": False})[0] is False


def test_every_speech_critical_constraint_is_checked():
    for key in SPEECH_CRITICAL_CONSTRAINTS:
        assert speech_content_preserved({**CLEAN, key: True})[0] is False


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

def test_probe_accepts_clean_audio():
    assert OpenSmileEGeMAPS().probe(media()).eligible


def test_probe_does_not_refuse_merely_because_dsp_was_applied():
    """Noise suppression changes the acoustic features but does not make them
    meaningless, and this engine does not emit the capability DSP deletes.
    Refusing here would discard usable arousal data to protect a valence channel
    that was never on offer — the fact is recorded as a quality row instead."""
    e = OpenSmileEGeMAPS().probe(
        media(applied_audio_constraints={**CLEAN, "noiseSuppression": True}))
    assert e.eligible is True
    assert "speech content not preserved" in e.detail


def test_probe_refuses_video():
    e = OpenSmileEGeMAPS().probe(media(kind="video"))
    assert not e.eligible
    assert "wrong_media_kind" in e.reasons


def test_probe_refuses_audio_too_short_to_window():
    e = OpenSmileEGeMAPS().probe(media(duration_s=0.4))
    assert not e.eligible
    assert "too_short" in e.reasons


# ---------------------------------------------------------------------------
# the voicing threshold is derived, not assumed
# ---------------------------------------------------------------------------

def test_the_threshold_follows_the_session_noise_floor():
    """A fixed absolute floor cannot work when autoGainControl is disabled on
    purpose: level depends entirely on the participant's microphone and
    distance. Measured on a real session, the LOUDEST 3s window had RMS 0.0007
    — seven times below a 0.005 floor that looked conservative when written."""
    quiet = np.full(50, 0.0002)
    loud = np.full(50, 0.2)
    assert voiced_threshold(loud) > voiced_threshold(quiet) * 100


def test_the_threshold_sits_above_the_noise_floor():
    rng = np.random.default_rng(0)
    noise = np.abs(rng.normal(0.0002, 0.00005, 200))
    t = voiced_threshold(noise)
    assert t > np.percentile(noise, 90)


def test_speech_clears_the_threshold_and_room_tone_does_not():
    rng = np.random.default_rng(1)
    windows = np.abs(rng.normal(0.0002, 0.00005, 100))
    windows[40:50] = 0.01                       # ten windows of actual speech

    t = voiced_threshold(windows)
    assert (windows[40:50] >= t).all()
    assert (windows[:40] < t).sum() >= 38


def test_an_all_silent_session_voices_almost_nothing():
    """The real session: the participant was following dots, not talking. A
    threshold that finds speech in room tone would fabricate 88 features per
    window describing silence."""
    rng = np.random.default_rng(2)
    windows = np.abs(rng.normal(0.0002, 0.00005, 200))
    assert (windows >= voiced_threshold(windows)).sum() < len(windows) * 0.05


def test_digital_silence_has_an_absolute_backstop():
    """A multiplicative threshold over an all-zero session is still zero."""
    assert voiced_threshold(np.zeros(50)) == ABSOLUTE_RMS_FLOOR


def test_an_empty_session_returns_the_backstop():
    assert voiced_threshold(np.empty(0)) == ABSOLUTE_RMS_FLOOR


# ---------------------------------------------------------------------------
# licence
# ---------------------------------------------------------------------------

def test_openSMILE_is_declared_non_commercial():
    """Verbatim from the licence: 'It is not allowed to use the open-source
    version of openSMILE for any sort of commercial product.' This is the first
    genuinely restricted engine in the project, and the commercial gate should
    now exit non-zero — which is correct for an academic build."""
    lic = OpenSmileEGeMAPS().manifest.license
    assert lic.commercial_use == "no"
    assert "commercial" in (lic.notes or "").lower()

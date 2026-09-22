"""Tests for the transcript engine.

The behaviour that matters is what it throws away. Whisper transcribing speech
correctly is the library's job and is verified by a positive control at the
bottom; what this project has to get right is the case where the model is
confident and wrong.

The model is faked throughout. Hoping Whisper hallucinates on cue is not a
test — the hallucination path has to be exercised on demand, with the exact
confidence values that should and should not pass.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine_contract import MediaDescriptor
from engine_contract.loader import load_engine_module

_engine = load_engine_module("speech.faster_whisper")
FasterWhisperTranscript = _engine.FasterWhisperTranscript
is_repeat_loop = _engine.is_repeat_loop
word_count = _engine.word_count

MANIFEST = json.loads(
    (Path(_engine.__file__).resolve().parent.parent / "engine.manifest.json")
    .read_text(encoding="utf-8"))


class FakeSegment:
    def __init__(self, start, end, text, no_speech_prob=0.0, avg_logprob=-0.2):
        self.start, self.end, self.text = start, end, text
        self.no_speech_prob, self.avg_logprob = no_speech_prob, avg_logprob


class FakeInfo:
    def __init__(self, language="en", language_probability=0.99):
        self.language, self.language_probability = language, language_probability


class FakeModel:
    def __init__(self, segments, info=None):
        self._segments, self._info = segments, info or FakeInfo()
        self.calls = []

    def transcribe(self, path, **kw):
        self.calls.append(kw)
        return iter(self._segments), self._info


def media(**kw) -> MediaDescriptor:
    base = dict(path="a.wav", kind="audio", sha256="0" * 64, duration_s=60.0,
                sample_rate_hz=16000.0, channels=1)
    base.update(kw)
    return MediaDescriptor(**base)


def engine_with(segments, info=None):
    e = FasterWhisperTranscript()
    e._model = FakeModel(segments, info)
    e._loaded_size = _engine.DEFAULT_MODEL_SIZE
    return e


def run(segments, params=None, info=None, m=None):
    e = engine_with(segments, info)
    return list(e.run(m or media(), params or {}))[0], e


def kept(chunk):
    return [ev for ev in chunk.events if ev.event_type == "speech_segment"]


def rejected(chunk):
    return [ev for ev in chunk.events if ev.event_type == "speech_segment_rejected"]


def quality(chunk):
    return {q.metric: q.value for q in chunk.quality}


# ---------------------------------------------------------------------------
# hallucination
# ---------------------------------------------------------------------------

def test_a_confident_transcription_of_non_speech_is_rejected():
    """The classic failure: fluent text, high confidence, no speech there."""
    chunk, _ = run([FakeSegment(0, 3, "Thank you for watching!",
                                no_speech_prob=0.95, avg_logprob=-0.1)])
    assert kept(chunk) == []
    assert rejected(chunk)[0].metadata["reasons"] == ["no_speech_prob"]


def test_a_low_confidence_segment_is_rejected():
    chunk, _ = run([FakeSegment(0, 3, "something mumbled",
                                no_speech_prob=0.1, avg_logprob=-2.5)])
    assert kept(chunk) == []
    assert rejected(chunk)[0].metadata["reasons"] == ["avg_logprob"]


def test_the_two_gates_are_independent():
    """They fail differently, which is why both are needed: a confident
    transcription of noise clears the log-probability gate, and a genuinely
    mumbled word clears the no-speech gate."""
    chunk, _ = run([
        FakeSegment(0, 2, "confident noise", no_speech_prob=0.9, avg_logprob=-0.1),
        FakeSegment(2, 4, "unsure speech", no_speech_prob=0.05, avg_logprob=-3.0),
        FakeSegment(4, 6, "both bad", no_speech_prob=0.9, avg_logprob=-3.0),
    ])
    reasons = [ev.metadata["reasons"] for ev in rejected(chunk)]
    assert reasons == [["no_speech_prob"], ["avg_logprob"],
                       ["no_speech_prob", "avg_logprob"]]


def test_a_rejected_segment_keeps_its_timing_but_not_its_text():
    """Auditable without preserving the fabrication. A rejected transcript kept
    'for reference' is a sentence attributed to a named participant that they
    never said, sitting in a file someone will later read as evidence."""
    chunk, _ = run([FakeSegment(1.5, 4.0, "Words they never said.",
                                no_speech_prob=0.99)])
    ev = rejected(chunk)[0]
    assert ev.onset_native_ts == 1500.0
    assert ev.offset_native_ts == 4000.0
    assert "text" not in ev.metadata
    assert ev.metadata["n_words_discarded"] == 4
    assert "no_speech_prob" in ev.metadata


def test_a_rejected_segment_emits_no_signal_rows():
    """A words-per-minute figure derived from a hallucination is a number that
    looks exactly like a measurement."""
    chunk, _ = run([FakeSegment(0, 3, "invented", no_speech_prob=0.99)])
    assert chunk.signals == ()


def test_an_empty_segment_is_rejected_rather_than_counted():
    chunk, _ = run([FakeSegment(0, 3, "   ")])
    assert kept(chunk) == []
    assert "empty" in rejected(chunk)[0].metadata["reasons"]


def test_a_decoder_repeat_loop_is_caught():
    """Each repetition is individually confident and individually speech-like,
    so neither per-segment gate sees it. Only the repetition gives it away."""
    segs = [FakeSegment(i, i + 1, "Subtitles by the community", 0.1, -0.2)
            for i in range(5)]
    chunk, _ = run(segs)
    assert any("repeat_loop" in ev.metadata["reasons"] for ev in rejected(chunk))


def test_genuine_repetition_below_the_loop_threshold_survives():
    """Someone counting, or repeating a word twice, is not a decoder loop."""
    segs = [FakeSegment(i, i + 1, "yes", 0.1, -0.2) for i in range(2)]
    chunk, _ = run(segs)
    assert len(kept(chunk)) == 2


def test_the_loop_detector_ignores_case_and_padding():
    assert is_repeat_loop(["Hello", "hello ", " HELLO"])
    assert not is_repeat_loop(["hello", "hello", "goodbye"])


def test_the_loop_detector_does_not_fire_on_empty_strings():
    """Three empty segments are three empty segments, not a loop — they have
    their own reason and it should be the one reported."""
    assert not is_repeat_loop(["", "", ""])


# ---------------------------------------------------------------------------
# what it keeps
# ---------------------------------------------------------------------------

def test_good_speech_is_kept_with_its_text():
    chunk, _ = run([FakeSegment(0, 2.0, "The quick brown fox.", 0.01, -0.25)])
    ev = kept(chunk)[0]
    assert ev.metadata["text"] == "The quick brown fox."
    assert ev.metadata["n_words"] == 4
    assert ev.metadata["language"] == "en"


def test_a_rate_and_a_confidence_travel_with_every_kept_segment():
    chunk, _ = run([FakeSegment(0, 2.0, "one two three four", 0.01, -0.3)])
    channels = {s.channel: s.value for s in chunk.signals}
    assert channels["speech.rate_wpm"] == pytest.approx(120.0)
    assert channels["speech.segment_confidence"] == pytest.approx(-0.3)


def test_a_zero_length_segment_yields_no_rate():
    """Dividing by it would produce an infinite words per minute, which would
    then be a float in the signals table."""
    chunk, _ = run([FakeSegment(5.0, 5.0, "blip", 0.01, -0.2)])
    assert not any(s.channel == "speech.rate_wpm" for s in chunk.signals)
    assert len(kept(chunk)) == 1


def test_signal_timestamps_sit_at_the_middle_of_their_segment():
    chunk, _ = run([FakeSegment(10.0, 14.0, "a b", 0.01, -0.2)])
    assert {s.native_ts for s in chunk.signals} == {12000.0}


def test_word_count_is_biased_in_the_direction_the_docstring_claims():
    """A contraction counts as two, so conversational English rates run a few
    per cent high. Pinned rather than fixed: correcting it properly is
    language-specific work, and a half-corrected count is harder to reason
    about than a consistently biased one."""
    assert word_count("Hello, world!") == 2
    assert word_count("don't stop") == 3      # not 2 — the apostrophe splits
    assert word_count("") == 0
    assert word_count("...") == 0


# ---------------------------------------------------------------------------
# quality
# ---------------------------------------------------------------------------

def test_quality_counts_both_outcomes():
    chunk, _ = run([
        FakeSegment(0, 2, "kept one", 0.01, -0.2),
        FakeSegment(2, 4, "kept two", 0.01, -0.2),
        FakeSegment(4, 6, "invented", 0.99, -0.1),
    ])
    q = quality(chunk)
    assert q["segments_retained"] == 2
    assert q["segments_rejected"] == 1


def test_coverage_counts_only_retained_speech():
    """Counting rejected segments toward coverage would make a hallucinating
    session look better covered than a quiet one."""
    chunk, _ = run([
        FakeSegment(0, 10, "real speech", 0.01, -0.2),
        FakeSegment(10, 50, "invented", 0.99, -0.1),
    ], m=media(duration_s=100.0))
    assert quality(chunk)["speech_coverage"] == pytest.approx(0.10)


def test_language_probability_is_reported_not_thresholded():
    """A low value is a finding for the researcher, not grounds for this engine
    to discard a study's data on its own authority."""
    chunk, _ = run([FakeSegment(0, 2, "noe på norsk", 0.01, -0.2)],
                   info=FakeInfo("nn", 0.42))
    assert quality(chunk)["language_probability"] == pytest.approx(0.42)
    assert len(kept(chunk)) == 1


def test_a_recording_with_no_speech_reports_zero_rather_than_failing():
    chunk, _ = run([])
    q = quality(chunk)
    assert q["segments_retained"] == 0
    assert q["speech_coverage"] == 0.0
    assert chunk.signals == ()


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------

def test_probe_accepts_usable_audio():
    assert FasterWhisperTranscript().probe(media()).eligible


def test_probe_refuses_video():
    assert not FasterWhisperTranscript().probe(media(kind="video")).eligible


def test_probe_refuses_a_sample_rate_that_has_lost_the_consonants():
    e = FasterWhisperTranscript().probe(media(sample_rate_hz=4000.0))
    assert not e.eligible
    assert "sample_rate_below_min" in e.reasons


def test_probe_refuses_a_clip_too_short_to_transcribe():
    """Whisper pads a short clip to its window and transcribes the padding —
    the hallucination case at its most reliable."""
    e = FasterWhisperTranscript().probe(media(duration_s=0.2))
    assert not e.eligible
    assert "too_short" in e.reasons


def test_the_sample_rate_gate_is_actually_wired_to_a_real_field():
    """It was not, at first: `MediaDescriptor` had no `sample_rate_hz`, so the
    check read a missing attribute through getattr and passed everything."""
    assert "sample_rate_hz" in MediaDescriptor.__dataclass_fields__


# ---------------------------------------------------------------------------
# parameters are recorded, not assumed
# ---------------------------------------------------------------------------

def test_the_vad_filter_is_on_by_default():
    _, e = run([])
    assert e._model.calls[0]["vad_filter"] is True


def test_a_study_may_turn_the_vad_filter_off():
    """It can clip genuinely quiet speech. Allowed, and recorded."""
    _, e = run([], params={"vad_filter": False})
    assert e._model.calls[0]["vad_filter"] is False


def test_language_and_beam_size_reach_the_model():
    _, e = run([], params={"language": "de", "beam_size": 1})
    assert e._model.calls[0]["language"] == "de"
    assert e._model.calls[0]["beam_size"] == 1


def test_the_gates_are_tunable_but_default_conservatively():
    props = MANIFEST["params_schema"]["properties"]
    assert props["max_no_speech_prob"]["default"] == 0.6
    assert props["min_avg_logprob"]["default"] == -1.0


def test_a_looser_gate_lets_a_borderline_segment_through():
    seg = [FakeSegment(0, 2, "borderline", no_speech_prob=0.7, avg_logprob=-0.2)]
    assert kept(run(seg)[0]) == []
    assert len(kept(run(seg, params={"max_no_speech_prob": 0.8})[0])) == 1


# ---------------------------------------------------------------------------
# the manifest says what it cannot do
# ---------------------------------------------------------------------------

def test_the_manifest_states_the_hallucination_risk():
    note = MANIFEST["capability_notes"]["hallucination"]
    assert "no_speech_prob" in note
    assert "avg_logprob" in note


def test_the_manifest_states_that_consent_gates_this():
    note = MANIFEST["capability_notes"]["consent_gated"]
    assert "media_plus_transcript" in note
    assert "transcript_stage" in note


def test_the_manifest_claims_no_word_error_rate():
    """Published Whisper WERs come from curated corpora, not a consumer
    microphone in someone's home after the browser's DSP."""
    note = MANIFEST["capability_notes"]["accuracy_unstated"]
    assert "no word error rate" in note.lower()


def test_the_manifest_states_that_it_does_not_separate_speakers():
    assert "diaris" in json.dumps(MANIFEST).lower()


def test_no_declared_channel_carries_the_words():
    """The text lives in events, never in a signal. The signals table is
    float-valued and a transcript is not a measurement of a quantity."""
    for spec in MANIFEST["outputs"]["signals"]:
        assert spec["value_type"] == "float"


# ---------------------------------------------------------------------------
# timing comes from words, not segments
# ---------------------------------------------------------------------------

class FakeWord:
    def __init__(self, start, end):
        self.start, self.end = start, end


def test_segment_timing_comes_from_its_words():
    """Measured on a real session: a segment crossing VAD-removed silence was
    stamped 217.0 s, 20 s before the prompt it answered; its words said 238.6 s."""
    seg = FakeSegment(217.0, 247.1, "I'm sitting in an office")
    seg.words = [FakeWord(238.6, 238.9), FakeWord(246.5, 247.1)]
    chunk, _ = run([seg])
    ev = next(e for e in chunk.events if e.event_type == "speech_segment")
    assert ev.onset_native_ts == pytest.approx(238_600.0)
    assert ev.offset_native_ts == pytest.approx(247_100.0)


def test_rate_uses_the_word_span_not_the_stretched_segment():
    """Dividing by the stretched 30 s segment would understate the rate by
    more than a factor of three; the words span 8.5 s."""
    seg = FakeSegment(217.0, 247.1, "I'm sitting in an office")
    seg.words = [FakeWord(238.6, 238.9), FakeWord(246.5, 247.1)]
    chunk, _ = run([seg])
    wpm = next(s for s in chunk.signals if s.channel == "speech.rate_wpm").value
    assert wpm == pytest.approx(word_count("I'm sitting in an office") / 8.5 * 60, rel=0.01)


def test_segments_without_words_fall_back_to_segment_times():
    chunk, _ = run([FakeSegment(1.0, 2.0, "hello there")])
    ev = next(e for e in chunk.events if e.event_type == "speech_segment")
    assert ev.onset_native_ts == pytest.approx(1000.0)


def test_word_timestamps_are_requested_by_default_and_can_be_turned_off():
    _, e = run([FakeSegment(1.0, 2.0, "hi")])
    assert e._model.calls[-1]["word_timestamps"] is True
    _, e = run([FakeSegment(1.0, 2.0, "hi")], params={"word_timestamps": False})
    assert e._model.calls[-1]["word_timestamps"] is False


def test_the_tuned_vad_threshold_reaches_the_model():
    """The library default (0.5) clipped "The old harbour" off a real passage;
    0.35 recovered it. Passed only while the VAD is on."""
    _, e = run([FakeSegment(1.0, 2.0, "hi")])
    assert e._model.calls[-1]["vad_parameters"] == {"threshold": _engine.DEFAULT_VAD_THRESHOLD}
    _, e = run([FakeSegment(1.0, 2.0, "hi")], params={"vad_filter": False})
    assert e._model.calls[-1]["vad_parameters"] is None


def test_the_manifest_defaults_match_the_engine():
    props = MANIFEST["params_schema"]["properties"]
    assert props["model_size"]["default"] == _engine.DEFAULT_MODEL_SIZE
    assert props["vad_threshold"]["default"] == _engine.DEFAULT_VAD_THRESHOLD

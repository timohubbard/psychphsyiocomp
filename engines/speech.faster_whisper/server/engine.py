"""speech.faster_whisper — a transcript, and the reasons it is hard to ship.

Two things make this different from every other engine here.

**It must not run without consent.** A transcript can contain anything a
participant happened to say, and it is the only output in this project that any
person who opens the file can read at a glance. `media_plus_transcript` is the
one tier that permits it. The gate is NOT in this file — an engine is a pure
function of media and cannot see a session's consent — it is in
``server/transcript_stage.py``, which is the only thing that calls this.

**Whisper hallucinates.** Given silence, breathing or room tone, it will
sometimes emit a complete, fluent, plausible sentence: often a caption-style
artefact from its training data ("Thank you for watching!"), sometimes
something less recognisable. In a research record this is worse than a wrong
number. A wrong number is visibly a measurement; a fabricated sentence is
indistinguishable from a quotation, attributed to a named participant, in a
file someone will later read as evidence of what they said.

So every segment passes two independent gates and both must hold: the model's
own ``no_speech_prob``, and its mean token log-probability. They fail
differently, which is the point — a confident transcription of noise clears the
second and not the first, while a genuinely mumbled word clears the first and
not the second. A rejected segment is still RECORDED, with its timing and its
confidence but without its text, so the rejection is auditable and nobody has
to keep the fabrication to prove it happened.

No word error rate is claimed. Published Whisper WERs come from curated
corpora, not from a consumer microphone in someone's kitchen after the
browser's DSP has had a turn, and nothing from those benchmarks transfers.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

from engine_contract import (
    Chunk,
    Eligibility,
    EngineLicense,
    EngineManifest,
    EngineOutputs,
    EngineProvenance,
    EventRow,
    InputSpec,
    MediaDescriptor,
    QualityRow,
    QualitySpec,
    SignalRow,
    SignalSpec,
)

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

#: Shares an origin with `video_pts`: the extracted WAV starts where the
#: recording starts, so the alignment service maps it the same way the voice
#: engine's output is mapped.
NATIVE_CLOCK_ID = "audio_offset"

#: Below this there is nothing to transcribe, and Whisper will pad and
#: hallucinate rather than return nothing.
MIN_DURATION_S = 0.5

#: Whisper resamples everything to 16 kHz internally. Below 8 kHz the source has
#: already lost the fricative energy that distinguishes many consonants, so the
#: transcript would be a guess dressed as a reading.
MIN_SAMPLE_RATE_HZ = 8000

#: A segment repeated verbatim this many times in a row is a decoder loop, not
#: someone saying the same thing. Whisper does this on long stretches of
#: non-speech and the repetitions are individually high-confidence, so neither
#: per-segment gate catches it.
MAX_CONSECUTIVE_REPEATS = 3


def load_manifest() -> EngineManifest:
    raw = json.loads(_MANIFEST_JSON.read_text(encoding="utf-8"))
    return EngineManifest(
        engine_id=raw["engine_id"],
        version=raw["version"],
        modality=raw["modality"],
        runtime=raw["runtime"],
        placement=raw["placement"],
        inputs=[InputSpec(**i) for i in raw["inputs"]],
        params_schema=raw["params_schema"],
        outputs=EngineOutputs(
            signals=[SignalSpec(**s) for s in raw["outputs"]["signals"]],
            events=raw["outputs"]["events"],
            quality=[QualitySpec(**q) for q in raw["outputs"]["quality"]],
        ),
        license=EngineLicense(
            spdx=raw["license"]["spdx"],
            commercial_use=raw["license"]["commercial_use"],
            url=raw["license"]["url"],
            notes=raw["license"].get("notes"),
        ),
        provenance=EngineProvenance(
            training_datasets=raw["provenance"].get("training_datasets") or [],
            paper_doi=raw["provenance"].get("paper_doi"),
        ),
        determinism=raw["determinism"],
    )


def word_count(text: str) -> int:
    """Words, for a rate. Approximate, and biased in known directions.

    Counts runs of word characters, because Whisper attaches punctuation to
    tokens. Two consequences worth stating rather than discovering:

    - A contraction counts as two ("don't" -> "don", "t"), so the rate runs
      high for conversational English by a few per cent.
    - Languages that do not space-separate are not handled at all; the whole
      utterance may count as one word, and the rate collapses.

    Neither is corrected here, because correcting them properly is
    language-specific work and a half-corrected count is harder to reason
    about than a consistently biased one. `speech.rate_wpm` is tiered moderate
    for this reason among others.
    """
    return len(re.findall(r"[^\W_]+", text, flags=re.UNICODE))


def is_repeat_loop(texts: list[str], limit: int = MAX_CONSECUTIVE_REPEATS) -> bool:
    """Has the decoder locked into repeating one line?

    Checked across segments rather than within one, because the per-segment
    gates cannot see it: each repetition is individually confident and
    individually speech-like. It is only the repetition that gives it away.
    """
    if len(texts) < limit:
        return False
    tail = [t.strip().lower() for t in texts[-limit:]]
    return len(set(tail)) == 1 and bool(tail[0])


class FasterWhisperTranscript:
    """Whisper transcription with the confidence gates wired in.

    Instantiated only by ``server/transcript_stage.py``, which checks consent
    first. Nothing else should construct this.
    """

    def __init__(self, model_dir: str | Path | None = None):
        # Where the weights live. Passed in rather than left to the library's
        # default cache, so `npm run models` owns model provenance the same way
        # it does for the MediaPipe bundles.
        self._model_dir = str(model_dir) if model_dir else None
        self._model = None
        self._loaded_size: str | None = None

    @property
    def manifest(self) -> EngineManifest:
        return load_manifest()

    @property
    def source(self) -> str:
        return f"{self.manifest.source}+server-batch"

    def probe(self, media: MediaDescriptor) -> Eligibility:
        """Eligibility for transcription.

        Note what it does NOT refuse on: noise suppression having been applied.
        §2.3's objection to DSP is about spectral features, and transcription
        is far more robust to it — refusing here would discard usable data to
        protect a capability that is not this engine's. The fact is already
        recorded by the voice engine's quality rows.
        """
        reasons: list[str] = []
        details: list[str] = []

        if media.kind != "audio":
            reasons.append("not_audio")

        rate = media.sample_rate_hz
        if rate is not None and rate < MIN_SAMPLE_RATE_HZ:
            reasons.append("sample_rate_below_min")
            details.append(f"{rate} Hz < {MIN_SAMPLE_RATE_HZ}")

        if media.duration_s is not None and media.duration_s < MIN_DURATION_S:
            # Whisper pads a short clip to its window and then transcribes the
            # padding, which is the hallucination case at its most reliable.
            reasons.append("too_short")
            details.append(f"{media.duration_s:.2f}s < {MIN_DURATION_S}s")

        return Eligibility(
            eligible=not reasons,
            reasons=tuple(reasons),
            detail="; ".join(details) or None,
        )

    def _load(self, model_size: str):
        from faster_whisper import WhisperModel

        if self._model is None or self._loaded_size != model_size:
            kwargs: dict[str, Any] = {"device": "cpu", "compute_type": "int8"}
            if self._model_dir:
                kwargs["download_root"] = self._model_dir
            self._model = WhisperModel(model_size, **kwargs)
            self._loaded_size = model_size
        return self._model

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        model_size = str(params.get("model_size", "base"))
        language = params.get("language") or None
        beam_size = int(params.get("beam_size", 5))
        max_no_speech = float(params.get("max_no_speech_prob", 0.6))
        min_logprob = float(params.get("min_avg_logprob", -1.0))

        # Whisper's own VAD, in addition to the gates below. It removes the
        # long silences that give the decoder the most room to invent, and the
        # two mechanisms fail differently enough to be worth both. A study may
        # turn it off — it can clip genuinely quiet speech — and the parameter
        # is recorded either way rather than assumed.
        vad_filter = bool(params.get("vad_filter", True))

        model = self._load(model_size)
        segments, info = model.transcribe(
            str(media.path), language=language, beam_size=beam_size,
            vad_filter=vad_filter,
        )

        signals: list[SignalRow] = []
        events: list[EventRow] = []
        retained = 0
        rejected = 0
        speech_s = 0.0
        kept_texts: list[str] = []

        for seg in segments:
            text = (seg.text or "").strip()
            no_speech = float(getattr(seg, "no_speech_prob", 0.0) or 0.0)
            logprob = float(getattr(seg, "avg_logprob", 0.0) or 0.0)
            duration = max(float(seg.end) - float(seg.start), 0.0)

            fails = []
            if no_speech > max_no_speech:
                fails.append("no_speech_prob")
            if logprob < min_logprob:
                fails.append("avg_logprob")
            if not text:
                fails.append("empty")

            if not fails and is_repeat_loop(kept_texts + [text]):
                # Retroactive: the loop is only visible once enough of it
                # exists, so the segment that reveals it is rejected and the
                # count reflects that this is one failure, not several.
                fails.append("repeat_loop")

            if fails:
                rejected += 1
                # Timing and confidence, never the text. The rejection stays
                # auditable without the fabrication being preserved.
                events.append(EventRow(
                    event_type="speech_segment_rejected",
                    native_clock_id=NATIVE_CLOCK_ID,
                    onset_native_ts=float(seg.start) * 1000.0,
                    offset_native_ts=float(seg.end) * 1000.0,
                    metadata={"reasons": fails, "no_speech_prob": round(no_speech, 4),
                              "avg_logprob": round(logprob, 4),
                              "n_words_discarded": word_count(text)},
                ))
                continue

            retained += 1
            speech_s += duration
            kept_texts.append(text)

            events.append(EventRow(
                event_type="speech_segment",
                native_clock_id=NATIVE_CLOCK_ID,
                onset_native_ts=float(seg.start) * 1000.0,
                offset_native_ts=float(seg.end) * 1000.0,
                metadata={"text": text, "n_words": word_count(text),
                          "no_speech_prob": round(no_speech, 4),
                          "avg_logprob": round(logprob, 4),
                          "language": info.language},
            ))

            mid_ms = (float(seg.start) + duration / 2.0) * 1000.0
            signals.append(SignalRow(
                stream="speech", channel="speech.segment_confidence",
                native_clock_id=NATIVE_CLOCK_ID, native_ts=mid_ms,
                value=logprob, reliability_tier="high"))

            if duration > 0:
                signals.append(SignalRow(
                    stream="speech", channel="speech.rate_wpm",
                    native_clock_id=NATIVE_CLOCK_ID, native_ts=mid_ms,
                    value=word_count(text) / duration * 60.0,
                    reliability_tier="moderate"))

        total_s = media.duration_s or 0.0
        span_end = (total_s or speech_s) * 1000.0
        quality = (
            QualityRow(stream="speech", metric="language_probability",
                       window_start_native_ts=0.0, window_end_native_ts=span_end,
                       value=float(getattr(info, "language_probability", 0.0) or 0.0)),
            QualityRow(stream="speech", metric="segments_retained",
                       window_start_native_ts=0.0, window_end_native_ts=span_end,
                       value=float(retained)),
            QualityRow(stream="speech", metric="segments_rejected",
                       window_start_native_ts=0.0, window_end_native_ts=span_end,
                       value=float(rejected)),
            QualityRow(stream="speech", metric="speech_coverage",
                       window_start_native_ts=0.0, window_end_native_ts=span_end,
                       value=(speech_s / total_s) if total_s else 0.0),
        )

        yield Chunk(signals=tuple(signals), events=tuple(events), quality=quality)

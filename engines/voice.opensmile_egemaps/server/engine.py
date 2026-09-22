"""voice.opensmile_egemaps — eGeMAPSv02 acoustic features from session audio.

THIS ENGINE CANNOT SUPPORT VALENCE. Not "does not yet"; cannot, at any accuracy,
ever. §2.3 is the reason and it is worth stating in full, because the result it
describes is the one everybody quotes:

    Wagner et al. 2023 (IEEE TPAMI) proved that transformer SER's strong valence
    performance is driven by implicit LINGUISTIC content learned during
    fine-tuning, not prosody. Re-synthesising test utterances via TTS from
    transcripts — same words, prosody stripped — left high-valence models'
    correlation nearly intact. Freezing the transformer layers during
    fine-tuning collapsed correlation to near zero.

Valence-from-voice is a covert speech-content model wearing an acoustic-features
costume. A pipeline that keeps only eGeMAPS-style hand-crafted features has
discarded precisely the mechanism that made that result good. So this engine
emits acoustic features — which is what arousal actually rests on, and where
§2.3 says the ground is comparatively firm — and names no valence channel at
all. Any valence must come from a separate engine over the waveform, and must be
labelled lexical rather than prosodic.

Absolute performance is weak even at its best: §2.3 puts best-in-challenge
8-class SER at Macro-F1 0.357 against chance 0.125, with cross-corpus
degradation of 11% arousal and 30% valence. Every new population is a domain
shift.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from engine_contract import (
    Chunk,
    Eligibility,
    EngineLicense,
    EngineManifest,
    EngineOutputs,
    EngineProvenance,
    InputSpec,
    MediaDescriptor,
    QualityRow,
    QualitySpec,
    SignalRow,
    SignalSpec,
)

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

#: Audio carries no container PTS of its own here — it was extracted to WAV — so
#: offsets are seconds from the start of the extracted file. That file starts
#: where the recording starts, so this shares an origin with `video_pts`, and
#: the alignment service maps it the same way.
NATIVE_CLOCK_ID = "audio_offset"

#: DSP stages whose presence changes what the audio can support. §2.3: noise
#: suppression that degrades intelligibility deletes the valence mechanism
#: rather than adding noise to it, and automatic gain control rescales exactly
#: the loudness features eGeMAPS measures.
SPEECH_CRITICAL_CONSTRAINTS = ("noiseSuppression", "autoGainControl")

#: Digital-silence backstop. Below this, a window carries no signal at all and
#: no adaptive threshold can rescue it.
ABSOLUTE_RMS_FLOOR = 1e-5

#: How far above the session's own noise floor a window must sit to count as
#: speech. Speech typically runs 10-30 dB over room tone; 4x is ~12 dB, the
#: conservative end.
VOICED_SNR_RATIO = 4.0

#: Percentile of window RMS taken as the noise floor. The 10th, not the minimum,
#: so one unusually dead window does not define the baseline.
NOISE_FLOOR_PERCENTILE = 10.0


def _load_manifest_json() -> dict[str, Any]:
    with _MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_manifest() -> EngineManifest:
    raw = _load_manifest_json()
    lic = raw["license"]
    prov = raw.get("provenance", {})

    return EngineManifest(
        engine_id=raw["engine_id"],
        version=raw["version"],
        modality=raw["modality"],
        runtime="python-cpu",
        placement="server-batch",
        inputs=[InputSpec(kind="audio")],
        params_schema=raw["params_schema"],
        outputs=EngineOutputs(
            signals=[
                SignalSpec(
                    channel="voice.*", unit="egemaps", nominal_rate_hz=1.0,
                    value_type="float", reliability_tier="moderate",
                    description=(
                        "88 eGeMAPSv02 functionals, named exactly as openSMILE "
                        "names them. Never renamed to something friendlier — the "
                        "mapping from a functional to a psychological construct "
                        "is the contested part, and a friendly name asserts it."
                    ),
                ),
                SignalSpec(
                    channel="voice.voiced_fraction", unit="proportion",
                    nominal_rate_hz=1.0, value_type="float",
                    reliability_tier="high",
                    description="Gates the rest: F0 over silence is not a quiet voice.",
                ),
            ],
            events=[],
            quality=[
                QualitySpec(metric="speech_content_preserved", unit="bool",
                            warn_below=1.0,
                            description="§2.3: DSP that degrades intelligibility deletes valence."),
                QualitySpec(metric="voiced_fraction", unit="proportion", warn_below=0.05,
                            description="A session where nobody spoke still produces features."),
                QualitySpec(metric="achieved_window_rate", unit="hz",
                            description="Windows per second. Recorded, not assumed."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(
            training_datasets=tuple(prov.get("training_datasets", ())),
            paper_doi=prov.get("paper_doi"),
        ),
    )


def voiced_threshold(rms_by_window: np.ndarray) -> float:
    """Speech-detection threshold, relative to this session's own noise floor.

    A fixed absolute RMS floor cannot work here. `autoGainControl` is disabled
    on purpose — §2.3 and §5.2, because AGC rescales exactly the loudness
    features eGeMAPS measures — so recording level depends entirely on the
    participant's microphone, its gain, and how far away they sat. Measured on
    one real session, the LOUDEST three-second window had RMS 0.0007, seven
    times below a floor of 0.005 that looked conservative when written.

    So the floor is derived: the session's own noise floor, times a margin.
    This is the third place in this project where a fixed threshold turned out
    to encode one machine's conditions — the HMM's velocity scales and the
    agreement variance gate were the others — and the pattern is the same every
    time. Estimate the scale from the data, keep an absolute backstop for the
    degenerate case.
    """
    if len(rms_by_window) == 0:
        return ABSOLUTE_RMS_FLOOR
    noise_floor = float(np.percentile(rms_by_window, NOISE_FLOOR_PERCENTILE))
    return max(noise_floor * VOICED_SNR_RATIO, ABSOLUTE_RMS_FLOOR)


def speech_content_preserved(applied: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Could intelligible speech have survived capture?

    Returns ``(preserved, reason)``. Unknown constraints count as NOT preserved:
    §5.2 records that the spec permits a UA to ignore a constraint without
    failing, so absence of evidence here is not evidence of absence, and the
    consequence of being wrong is a valence channel that silently measures
    nothing.
    """
    if not applied:
        return False, "no applied constraints recorded — cannot confirm DSP was off"

    still_on = [k for k in SPEECH_CRITICAL_CONSTRAINTS if applied.get(k) is True]
    if still_on:
        return False, f"{', '.join(still_on)} was applied by the browser"

    missing = [k for k in SPEECH_CRITICAL_CONSTRAINTS if k not in applied]
    if missing:
        return False, f"no record of {', '.join(missing)}"

    return True, None


class OpenSmileEGeMAPS:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self) -> None:
        self.manifest = _build_manifest()
        self._smile = None

    @property
    def source(self) -> str:
        return f"{self.manifest.source}+server-batch"

    def probe(self, media: MediaDescriptor) -> Eligibility:
        """Eligibility for ACOUSTIC features.

        Note what this does NOT refuse on: DSP having been applied. Noise
        suppression changes the acoustic features but does not make them
        meaningless, and a session captured with it on is still usable for
        arousal work. What it deletes is valence — which this engine does not
        emit — so refusing here would discard usable data to protect a
        capability that was never on offer. The fact is recorded as a quality
        row instead, where a later valence engine can refuse on it.
        """
        reasons: list[str] = []
        details: list[str] = []

        if media.kind != "audio":
            reasons.append("wrong_media_kind")
            details.append(f"got {media.kind}, need audio")

        if media.duration_s is not None and media.duration_s < 1.0:
            reasons.append("too_short")
            details.append(f"{media.duration_s:.2f}s")

        preserved, why = speech_content_preserved(media.applied_audio_constraints)
        if not preserved:
            details.append(f"speech content not preserved: {why}")

        return Eligibility(eligible=not reasons, reasons=tuple(reasons),
                           detail="; ".join(details) if details else None)

    def _load(self):
        if self._smile is None:
            import opensmile

            self._smile = opensmile.Smile(
                feature_set=opensmile.FeatureSet.eGeMAPSv02,
                feature_level=opensmile.FeatureLevel.Functionals,
            )
        return self._smile

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        import soundfile as sf

        smile = self._load()
        window_s = float(params.get("window_s", 3.0))
        hop_s = float(params.get("hop_s", 1.0))

        audio, rate = sf.read(media.path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        win = int(window_s * rate)
        hop = int(hop_s * rate)
        if win <= 0 or hop <= 0 or len(audio) < win:
            yield Chunk()
            return

        starts = list(range(0, len(audio) - win + 1, hop))
        rms_by_window = np.array([
            float(np.sqrt(np.mean(audio[s:s + win] ** 2))) for s in starts
        ])
        threshold = voiced_threshold(rms_by_window)

        signals: list[SignalRow] = []
        voiced_flags: list[float] = []

        for idx, start in enumerate(starts):
            segment = audio[start:start + win]
            # Centre of the window, not its start: a functional is a statistic
            # over the whole window and attributing it to the leading edge would
            # shift every voice feature half a window early relative to gaze and
            # face, which are per-frame.
            ts_ms = (start + win / 2) / rate * 1000.0

            voiced = 1.0 if rms_by_window[idx] >= threshold else 0.0
            voiced_flags.append(voiced)

            signals.append(SignalRow(
                stream="voice", channel="voice.voiced_fraction",
                native_clock_id=NATIVE_CLOCK_ID, native_ts=ts_ms,
                value=voiced, reliability_tier="high"))

            # Silent windows still get a voiced_fraction row — the silence is a
            # finding — but no features, because 88 statistics describing
            # silence are 88 ways to be misread.
            if not voiced:
                continue

            frame = smile.process_signal(segment, rate)
            row = frame.iloc[0]
            for name, value in row.items():
                if value is None or (isinstance(value, float) and np.isnan(value)):
                    continue
                signals.append(SignalRow(
                    stream="voice", channel=f"voice.{name}",
                    native_clock_id=NATIVE_CLOCK_ID, native_ts=ts_ms,
                    value=float(value), reliability_tier="moderate"))

        preserved, _ = speech_content_preserved(media.applied_audio_constraints)
        duration_ms = len(audio) / rate * 1000.0

        quality = [
            QualityRow(stream="voice", metric="speech_content_preserved",
                       window_start_native_ts=0.0, window_end_native_ts=duration_ms,
                       value=1.0 if preserved else 0.0),
            QualityRow(stream="voice", metric="voiced_fraction",
                       window_start_native_ts=0.0, window_end_native_ts=duration_ms,
                       value=float(np.mean(voiced_flags)) if voiced_flags else 0.0),
            QualityRow(stream="voice", metric="achieved_window_rate",
                       window_start_native_ts=0.0, window_end_native_ts=duration_ms,
                       value=(len(voiced_flags) / (duration_ms / 1000.0))
                       if duration_ms else 0.0),
        ]

        yield Chunk(signals=tuple(signals), quality=tuple(quality))

"""face.pyfeat_aus — FACS Action Unit occurrence probabilities from stored video.

Three things about this engine are decisions rather than implementation.

**It never emits an emotion.** §2.2 quotes Barrett et al. 2019, an invited
consensus review spanning opposing camps: emotion categories "are not expressed
with facial movements that are sufficiently reliable and specific across
contexts, individuals, and cultures to be considered diagnostic displays of any
emotional state." Coherence r = .32; the hypothesised configuration is present
in only ~19% of emotional episodes. Py-Feat ships an emotion model and this
engine declines to load it — AU→emotion belongs in a separate, explicitly
toggleable engine, so that a study which wants it has to say so. EU AI Act
Recital 18 also excludes mere expression detection *unless used to infer
emotion*, which makes the boundary a compliance surface as well as a scientific
one.

**Reliability is set per AU, never uniformly.** §2.2 measured AU12 at F1 .72-.83
and AU20 at .13-.24 — same data, same model. A uniform confidence across 20+
units would overstate one end and understate the other. Tiers come from
`engine_contract.au_reliability`, which lives in the contract because the
difficulty is a property of the measurement problem, not of this detector.

**Its absolute output is not ground truth, and the engine says so.** §2.2 found
engine choice swinging valid-face-frame yield 43%→63% and expression counts 3-4x
on identical video, with per-participant agreement between engines at r =
0.37-0.75. The constructive finding was that *relative, within-participant
proportions* were robust where absolute counts were not. So `face.detected` is
emitted as a signal rather than left implicit: the denominator is itself a
finding, and a rate computed against a different engine's denominator is not
comparable.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from engine_contract import (
    Chunk,
    Eligibility,
    EngineLicense,
    EngineManifest,
    EngineOutputs,
    EngineProvenance,
    EventRow,
    EventSpec,
    InputSpec,
    MediaDescriptor,
    QualityRow,
    QualitySpec,
    SignalRow,
    SignalSpec,
)
from engine_contract.au_reliability import normalise, reliability
from engine_contract.media import mean_luma  # noqa: F401

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

NATIVE_CLOCK_ID = "video_pts"
QUALITY_WINDOW_MS = 5000.0

#: Detector stacks that perform IDENTITY recognition. ArcFace is a face-identity
#: model; it is not needed to measure an eyebrow, and Py-Feat ships a
#: non-commercial InsightFace weight for it. Refusing it here means the licence
#: note in the manifest describes something the code actually enforces.
#:
#: Matched EXACTLY, not as substrings. `mobilefacenet` is a landmark backbone and
#: contains "facenet" — a substring rule rejects the default legitimate stack
#: while looking like a careful safety check. A new identity model has to be
#: added here by name, which is the honest trade: a guard that over-matches gets
#: switched off, and then guards nothing.
IDENTITY_MODELS = frozenset({"insightface", "arcface", "facenet", "adaface", "magface"})


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
        inputs=[InputSpec(kind="video", min_fps=5.0, min_width=320,
                          min_height=240, min_roi_luminance=30.0)],
        params_schema=raw["params_schema"],
        outputs=EngineOutputs(
            signals=[
                SignalSpec(
                    channel="au.*", unit="probability", nominal_rate_hz=6.0,
                    value_type="float", value_range=(0.0, 1.0),
                    reliability_tier="moderate",
                    description=(
                        "FACS Action Unit occurrence probabilities, not "
                        "intensities. The tier on each ROW is set per AU from "
                        "the published per-unit floor; this spec-level "
                        "value is only a default."
                    ),
                ),
                SignalSpec(
                    channel="face.detected", unit="bool", nominal_rate_hz=6.0,
                    value_type="float", reliability_tier="high",
                    description="Whether a face was found. The denominator is a finding.",
                ),
            ],
            events=[EventSpec(event_type="face_lost", has_offset=True,
                              description="No face detected")],
            quality=[
                QualitySpec(metric="achieved_fps", unit="hz", warn_below=1.0,
                            description="Effective AU rate after frame_stride."),
                QualitySpec(metric="face_detect_rate", unit="proportion", warn_below=0.5,
                            description="§2.2: 43% vs 62-63% between engines on identical video."),
                QualitySpec(metric="mean_luminance", unit="level", warn_below=30.0,
                            description="§2.5: the only quantified bias mitigation."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(
            training_datasets=tuple(prov.get("training_datasets", ())),
            paper_doi=prov.get("paper_doi"),
        ),
    )


def check_no_identity_model(params: dict[str, Any]) -> None:
    """Refuse a detector stack that does face recognition.

    Raised rather than warned. An identity model is not a worse AU detector, it
    is a different capability with different consent implications — a
    participant who agreed to have their brow movement measured did not agree to
    be recognised. It also carries the non-commercial weight that makes this
    engine's licence status worse than it needs to be.
    """
    for key in ("face_model", "landmark_model", "au_model",
                "facepose_model", "identity_model"):
        value = str(params.get(key, "")).strip().lower()
        if value in IDENTITY_MODELS:
            raise ValueError(
                f"{key}={params[key]!r} performs identity recognition. This engine "
                "measures Action Units; identity is a different capability with "
                "different consent implications, and the weight is non-commercial."
            )


class PyFeatAUs:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self, device: str = "cpu") -> None:
        self.manifest = _build_manifest()
        self._device = device
        self._detector = None

    @property
    def source(self) -> str:
        return f"{self.manifest.source}+server-batch"

    def probe(self, media: MediaDescriptor) -> Eligibility:
        reasons: list[str] = []
        details: list[str] = []

        if media.kind != "video":
            reasons.append("wrong_media_kind")
            details.append(f"got {media.kind}")

        spec = self.manifest.inputs[0]
        if spec.min_fps and media.fps is not None and media.fps < spec.min_fps:
            reasons.append("fps_below_min")
            details.append(f"{media.fps:.1f} fps < {spec.min_fps}")
        if spec.min_width and media.width is not None and media.width < spec.min_width:
            reasons.append("resolution_below_min")
            details.append(f"{media.width}x{media.height}")
        if (spec.min_roi_luminance and media.mean_roi_luminance is not None
                and media.mean_roi_luminance < spec.min_roi_luminance):
            reasons.append("luminance_below_min")
            details.append(f"{media.mean_roi_luminance:.0f} < {spec.min_roi_luminance}")

        return Eligibility(eligible=not reasons, reasons=tuple(reasons),
                           detail="; ".join(details) if details else None)

    def _load(self, params: dict[str, Any]):
        if self._detector is not None:
            return self._detector

        check_no_identity_model(params)
        import feat  # imported late: torch takes seconds to load

        self._detector = feat.Detectorv1(
            face_model=params.get("face_model", "retinaface"),
            landmark_model=params.get("landmark_model", "mobilefacenet"),
            au_model=params.get("au_model", "xgb"),
            # Both explicitly None, and both are refusals rather than defaults.
            #
            # emotion: AU->emotion is a separate, explicitly-toggleable engine.
            # Loading the model here would make the boundary a matter of what
            # callers happen to read rather than what this engine can produce.
            #
            # identity: Py-Feat DEFAULTS identity_model='arcface' — a face
            # recognition model carrying the non-commercial InsightFace weight,
            # loaded unless you say otherwise. A participant who agreed to have
            # their brow movement measured did not agree to be recognised, and
            # nothing in AU detection needs it.
            emotion_model=None,
            identity_model=None,
            device=self._device,
        )
        return self._detector

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        detector = self._load(params)
        stride = max(1, int(params.get("frame_stride", 5)))
        batch_size = max(1, int(params.get("batch_size", 8)))

        cap = cv2.VideoCapture(media.path)
        if not cap.isOpened():
            raise OSError(f"could not open {media.path}")

        signals: list[SignalRow] = []
        events: list[EventRow] = []
        quality: list[QualityRow] = []
        lumas: list[float] = []

        processed = faces = 0
        last_ts = -1.0
        window_start: float | None = None
        face_lost_open = False
        index = 0

        pending_frames: list[np.ndarray] = []
        pending_ts: list[float] = []

        def flush() -> None:
            nonlocal processed, faces, window_start, face_lost_open, lumas
            if not pending_frames:
                return
            results = detect_aus_batch(detector, pending_frames)

            for frame_ts, aus in zip(pending_ts, results):
                processed += 1
                found = aus is not None

                signals.append(SignalRow(
                    stream="face", channel="face.detected",
                    native_clock_id=NATIVE_CLOCK_ID, native_ts=frame_ts,
                    value=1.0 if found else 0.0, reliability_tier="high"))

                if found:
                    faces += 1
                    if face_lost_open:
                        _close(events, "face_lost", frame_ts)
                        face_lost_open = False
                    for au, value in aus.items():
                        key = normalise(au)
                        signals.append(SignalRow(
                            stream="face", channel=f"au.{key}",
                            native_clock_id=NATIVE_CLOCK_ID, native_ts=frame_ts,
                            value=float(value),
                            # Per AU, from the published floor. A uniform tier
                            # here would be the single most misleading thing
                            # this engine could do.
                            reliability_tier=reliability(key).tier))
                elif not face_lost_open:
                    events.append(EventRow(
                        event_type="face_lost", native_clock_id=NATIVE_CLOCK_ID,
                        onset_native_ts=frame_ts, offset_native_ts=None,
                        stimulus_id=None, metadata=None))
                    face_lost_open = True

            pending_frames.clear()
            pending_ts.clear()

        try:
            while True:
                ok, frame_bgr = cap.read()
                if not ok:
                    break
                if index % stride:
                    index += 1
                    continue
                index += 1

                ts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if ts_ms <= last_ts and (processed or pending_ts):
                    ts_ms = last_ts + (stride * 1000.0 / (media.fps or 30.0))
                last_ts = ts_ms
                if window_start is None:
                    window_start = ts_ms

                lumas.append(mean_luma(frame_bgr))
                pending_frames.append(frame_bgr)
                pending_ts.append(ts_ms)

                if len(pending_frames) >= batch_size:
                    flush()

                if window_start is not None and ts_ms - window_start >= QUALITY_WINDOW_MS:
                    flush()
                    quality.extend(_quality_rows(window_start, ts_ms, processed, faces, lumas))
                    window_start, processed, faces = ts_ms, 0, 0
                    lumas = []
        finally:
            cap.release()

        flush()
        if window_start is not None and processed:
            quality.extend(_quality_rows(window_start, last_ts, processed, faces, lumas))

        yield Chunk(signals=tuple(signals), events=tuple(events), quality=tuple(quality))


def detect_aus_batch(
    detector, frames_bgr: list[np.ndarray],
) -> list[dict[str, float] | None]:
    """Run the detector on a batch, returning one dict (or None) per frame.

    The entire Py-Feat API surface lives in this function on purpose. Everything
    above it is contract plumbing that stays valid across detector versions, so
    an upstream API change should require editing one function rather than
    auditing an engine.

    Batched because it is roughly free to do so and the model is the cost:
    measured at 0.25s per frame, a 4-minute session at the default stride is
    about six minutes of inference either way, and per-frame calls would repeat
    the setup for each one.

    Video mode is deliberately not used. Py-Feat can read a file directly, but
    that path goes through torchcodec and needs FFmpeg shared libraries, which
    are an extra system dependency this project does not otherwise have. OpenCV
    already decodes these files and is already required.
    """
    import torch

    rgb = np.stack([cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in frames_bgr])
    batch = torch.tensor(rgb, dtype=torch.float32).permute(0, 3, 1, 2)

    fex = detector.detect(batch, data_type="tensor", progress_bar=False)
    out: list[dict[str, float] | None] = [None] * len(frames_bgr)
    if fex is None or len(fex) == 0:
        return out

    aus = fex.aus
    frame_index = (fex["frame"].tolist() if "frame" in fex.columns
                   else list(range(len(aus))))

    for pos, frame_i in enumerate(frame_index):
        if not (0 <= int(frame_i) < len(out)):
            continue
        row = aus.iloc[pos]
        values = {str(k): float(v) for k, v in row.items()
                  if v is not None and not (isinstance(v, float) and np.isnan(v))}
        out[int(frame_i)] = values or None
    return out


def _close(events: list[EventRow], event_type: str, ts_ms: float) -> None:
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        if e.event_type == event_type and e.offset_native_ts is None:
            events[i] = EventRow(
                event_type=e.event_type, native_clock_id=e.native_clock_id,
                onset_native_ts=e.onset_native_ts, offset_native_ts=ts_ms,
                stimulus_id=e.stimulus_id, metadata=e.metadata)
            return


def _quality_rows(start, end, processed, faces, lumas) -> list[QualityRow]:
    span_s = max((end - start) / 1000.0, 1e-9)

    def row(metric: str, value: float) -> QualityRow:
        return QualityRow(stream="face", metric=metric,
                          window_start_native_ts=start, window_end_native_ts=end,
                          value=value)

    rows = [
        row("achieved_fps", processed / span_s),
        row("face_detect_rate", faces / processed if processed else 0.0),
    ]
    if lumas:
        rows.append(row("mean_luminance", float(np.median(lumas))))
    return rows

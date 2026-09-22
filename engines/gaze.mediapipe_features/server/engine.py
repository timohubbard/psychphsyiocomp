"""gaze.mediapipe_features — eye and iris features from stored video.

This engine emits FEATURES, never a gaze direction. That separation is
deliberate and load-bearing:

  - Mapping features to screen coordinates requires knowing which calibration
    target was on screen when, and stimulus events live on the master clock —
    which engines are forbidden to reason about (REPORT.md §3.3). The estimator
    therefore cannot be an engine; it is a pipeline stage (server/gaze_ridge.py).

  - §2.1 found human annotation of the *same* webcam video reached 92% where
    WebGazer reached 70%. The estimator is the bottleneck, so it is the part
    that will be replaced repeatedly. Storing features means each replacement
    re-fits over existing data instead of re-decoding every session's video.

  - Features carry no gaze-dataset EULA. A model trained on ETH-XGaze or Gaze360
    does; keeping that boundary at the engine edge means the licence question
    attaches to the estimator alone.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

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
from engine_contract.media import describe_video, mean_luma  # noqa: F401

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

NATIVE_CLOCK_ID = "video_pts"
QUALITY_WINDOW_MS = 5000.0

# ---------------------------------------------------------------------------
# Landmark indices.
#
# MediaPipe's canonical face mesh, 478-point variant (the 468-point base plus
# ten iris points). Every index below was verified empirically against a real
# recording rather than taken from memory: iris centres fall between their own
# eye corners horizontally and inside the eyelids vertically, and the
# subject-right group sits image-left of the subject-left group.
#
# "LEFT" and "RIGHT" are the SUBJECT'S, following MediaPipe. The subject's right
# eye appears on the left of the image, and mixing those up produces a model
# that is subtly, consistently wrong rather than obviously broken.
# ---------------------------------------------------------------------------

RIGHT_IRIS_CENTRE = 468
LEFT_IRIS_CENTRE = 473

RIGHT_EYE_OUTER, RIGHT_EYE_INNER = 33, 133
LEFT_EYE_INNER, LEFT_EYE_OUTER = 362, 263

RIGHT_EYE_UPPER, RIGHT_EYE_LOWER = 159, 145
LEFT_EYE_UPPER, LEFT_EYE_LOWER = 386, 374

#: Below this eyelid-aperture ratio the iris is too occluded to localise. A
#: blink does not make the iris estimate noisy, it makes it meaningless — so
#: these frames are dropped and counted rather than emitted with a caveat.
MIN_OPENNESS = 0.10


def _load_manifest_json() -> dict[str, Any]:
    with _MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_manifest() -> EngineManifest:
    raw = _load_manifest_json()
    lic = raw["license"]
    prov = raw.get("provenance", {})

    def sig(channel: str, unit: str, tier: str) -> SignalSpec:
        return SignalSpec(
            channel=channel, unit=unit, nominal_rate_hz=30.0,
            value_type="float", reliability_tier=tier,
        )

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
                sig("eye.left_iris_dx", "eye_widths", "moderate"),
                sig("eye.left_iris_dy", "eye_widths", "low"),
                sig("eye.right_iris_dx", "eye_widths", "moderate"),
                sig("eye.right_iris_dy", "eye_widths", "low"),
                sig("eye.left_openness", "ratio", "moderate"),
                sig("eye.right_openness", "ratio", "moderate"),
                sig("eye.inter_ocular_px", "px", "moderate"),
                sig("head_pose.yaw", "deg", "high"),
                sig("head_pose.pitch", "deg", "high"),
                sig("head_pose.roll", "deg", "high"),
            ],
            events=[
                EventSpec(event_type="face_lost", has_offset=True,
                          description="Face detection dropped below presence confidence"),
                EventSpec(event_type="eyes_closed", has_offset=True,
                          description="Both eyes below the openness threshold"),
            ],
            quality=[
                QualitySpec(metric="achieved_fps", unit="hz", warn_below=5.0,
                            description="Measured, never assumed. §5.3 uses 5 Hz as an exclusion threshold."),
                QualitySpec(metric="face_detect_rate", unit="proportion", warn_below=0.5,
                            description="Fraction of frames with a face above presence confidence."),
                QualitySpec(metric="iris_valid_rate", unit="proportion", warn_below=0.5,
                            description="Fraction of frames yielding usable iris features."),
                QualitySpec(metric="mean_luminance", unit="level", warn_below=30.0,
                            description="§2.5: the only quantified bias mitigation in the evidence base."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(
            training_datasets=tuple(prov.get("training_datasets", ())),
            paper_doi=prov.get("paper_doi"),
        ),
    )


# ---------------------------------------------------------------------------
# feature extraction — pure maths over landmark arrays, no MediaPipe types
# ---------------------------------------------------------------------------

def eye_features(
    iris_centre: np.ndarray,
    corner_a: np.ndarray,
    corner_b: np.ndarray,
    lid_upper: np.ndarray,
    lid_lower: np.ndarray,
) -> tuple[float, float, float]:
    """Normalised iris offset and eyelid aperture for one eye.

    Returns ``(dx, dy, openness)``, all dimensionless.

    The offset is measured from the MIDPOINT of the two corners and divided by
    the distance between them. Dividing by the eye's own width is what makes
    this comparable at all: the raw pixel offset for a given gaze angle scales
    with how much of the frame the face occupies, so an unnormalised feature
    would encode how far back the participant is sitting far more strongly than
    where they are looking.

    Corners are passed as an unordered pair on purpose. Which one is nasal
    differs between the two eyes, and the midpoint and distance do not care —
    so the caller cannot introduce a left/right asymmetry by getting the order
    wrong.
    """
    width = float(np.linalg.norm(corner_b - corner_a))
    if width <= 1e-9:
        return float("nan"), float("nan"), float("nan")

    centre = (corner_a + corner_b) / 2.0
    offset = (iris_centre - centre) / width
    openness = float(np.linalg.norm(lid_upper - lid_lower)) / width
    return float(offset[0]), float(offset[1]), openness


def euler_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """Yaw/pitch/roll in degrees from a 4x4 facial transformation matrix.

    Y-X-Z intrinsic, matching the facial engine exactly. Both are pinned by
    tests: a nod must read as pitch in both placements, or the same video would
    produce different head pose depending on which engine processed it.
    """
    r = np.asarray(m, dtype=float)
    if r.shape != (4, 4):
        raise ValueError(f"expected a 4x4 matrix, got shape {r.shape}")

    r02, r10, r11, r12, r22 = r[0, 2], r[1, 0], r[1, 1], r[1, 2], r[2, 2]
    pitch = math.atan2(-r12, math.hypot(r10, r11))
    yaw = math.atan2(r02, r22)
    roll = math.atan2(r10, r11)
    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def features_from_landmarks(
    landmarks, width_px: int, height_px: int,
) -> dict[str, float] | None:
    """Turn one frame's landmarks into the feature dict, or None if unusable.

    Pixel coordinates, not normalised ones. MediaPipe returns x and y each
    divided by their own axis length, so on a 16:9 frame a circle becomes an
    ellipse and an offset means something different horizontally than
    vertically. Scaling back to pixels before measuring any distance restores
    the aspect ratio — without it, `inter_ocular_px` and the openness ratio are
    both quietly wrong, and the error changes with frame shape.
    """
    if landmarks is None or len(landmarks) <= max(LEFT_IRIS_CENTRE, LEFT_EYE_OUTER):
        return None

    def p(i: int) -> np.ndarray:
        lm = landmarks[i]
        return np.array([lm.x * width_px, lm.y * height_px], dtype=float)

    r_dx, r_dy, r_open = eye_features(
        p(RIGHT_IRIS_CENTRE), p(RIGHT_EYE_OUTER), p(RIGHT_EYE_INNER),
        p(RIGHT_EYE_UPPER), p(RIGHT_EYE_LOWER))
    l_dx, l_dy, l_open = eye_features(
        p(LEFT_IRIS_CENTRE), p(LEFT_EYE_OUTER), p(LEFT_EYE_INNER),
        p(LEFT_EYE_UPPER), p(LEFT_EYE_LOWER))

    vals = (r_dx, r_dy, r_open, l_dx, l_dy, l_open)
    if any(math.isnan(v) for v in vals):
        return None

    return {
        "eye.right_iris_dx": r_dx,
        "eye.right_iris_dy": r_dy,
        "eye.right_openness": r_open,
        "eye.left_iris_dx": l_dx,
        "eye.left_iris_dy": l_dy,
        "eye.left_openness": l_open,
        "eye.inter_ocular_px": float(
            np.linalg.norm(p(LEFT_IRIS_CENTRE) - p(RIGHT_IRIS_CENTRE))),
    }


#: Channel order the estimator expects. Fixed here so the feature vector cannot
#: be silently permuted between fitting and prediction — a reordering would not
#: raise, it would just produce a worse model.
FEATURE_CHANNELS = (
    "eye.left_iris_dx", "eye.left_iris_dy",
    "eye.right_iris_dx", "eye.right_iris_dy",
    "eye.left_openness", "eye.right_openness",
    "eye.inter_ocular_px",
    "head_pose.yaw", "head_pose.pitch", "head_pose.roll",
)

RELIABILITY = {
    "eye.left_iris_dx": "moderate", "eye.right_iris_dx": "moderate",
    "eye.left_iris_dy": "low", "eye.right_iris_dy": "low",
    "eye.left_openness": "moderate", "eye.right_openness": "moderate",
    "eye.inter_ocular_px": "moderate",
    "head_pose.yaw": "high", "head_pose.pitch": "high", "head_pose.roll": "high",
}


class MediaPipeGazeFeatures:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self, model_path: str | Path) -> None:
        self.manifest = _build_manifest()
        self._model_path = Path(model_path)
        if not self._model_path.exists():
            raise FileNotFoundError(
                f"face_landmarker.task not found at {self._model_path}. "
                "Fetch it with tools/fetch_models.py"
            )

    @property
    def source(self) -> str:
        return f"{self.manifest.source}+server-batch"

    def probe(self, media: MediaDescriptor) -> Eligibility:
        """Decide whether this media can support gaze features at all.

        Ineligibility is returned, never raised, so the caller writes a quality
        row explaining the refusal instead of silently skipping the engine.
        """
        reasons: list[str] = []
        details: list[str] = []

        if media.kind != "video":
            reasons.append("wrong_media_kind")
            details.append(f"got {media.kind}")

        spec = self.manifest.inputs[0]
        if spec.min_fps and media.fps is not None and media.fps < spec.min_fps:
            reasons.append("fps_below_min")
            details.append(f"{media.fps:.1f} fps < {spec.min_fps} fps")

        if spec.min_width and media.width is not None and media.width < spec.min_width:
            reasons.append("resolution_below_min")
            details.append(f"{media.width}x{media.height}")

        if (spec.min_roi_luminance and media.mean_roi_luminance is not None
                and media.mean_roi_luminance < spec.min_roi_luminance):
            # Not a picture-quality preference. §2.5 is the only quantified bias
            # mitigation in the evidence base, and it is about who the
            # measurement works for, not how nice it looks.
            reasons.append("luminance_below_min")
            details.append(
                f"{media.mean_roi_luminance:.0f} < {spec.min_roi_luminance}")

        return Eligibility(
            eligible=not reasons,
            reasons=tuple(reasons),
            detail="; ".join(details) if details else None,
        )

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        cap = cv2.VideoCapture(media.path)
        if not cap.isOpened():
            raise OSError(f"could not open {media.path}")

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=params.get("min_face_detection_confidence", 0.5),
            min_face_presence_confidence=params.get("min_face_presence_confidence", 0.5),
            min_tracking_confidence=params.get("min_tracking_confidence", 0.5),
        )

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        signals: list[SignalRow] = []
        events: list[EventRow] = []
        quality: list[QualityRow] = []
        lumas: list[float] = []

        frames = faces = iris_ok = 0
        last_ts = -1.0
        window_start: float | None = None
        face_lost_open = eyes_closed_open = False

        try:
            with vision.FaceLandmarker.create_from_options(options) as landmarker:
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok:
                        break

                    ts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                    if ts_ms <= last_ts and frames > 0:
                        ts_ms = last_ts + (1000.0 / (media.fps or 30.0))
                    last_ts = ts_ms
                    if window_start is None:
                        window_start = ts_ms
                    frames += 1
                    lumas.append(mean_luma(frame_bgr))

                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    result = landmarker.detect_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb),
                        int(ts_ms))

                    has_face = bool(result.face_landmarks)
                    if has_face:
                        faces += 1
                        if face_lost_open:
                            _close(events, "face_lost", ts_ms)
                            face_lost_open = False
                    elif not face_lost_open:
                        events.append(EventRow(
                            event_type="face_lost", native_clock_id=NATIVE_CLOCK_ID,
                            onset_native_ts=ts_ms, offset_native_ts=None,
                            stimulus_id=None, metadata=None))
                        face_lost_open = True

                    feats = (features_from_landmarks(result.face_landmarks[0], width, height)
                             if has_face else None)

                    if feats is not None:
                        closed = (feats["eye.left_openness"] < MIN_OPENNESS
                                  and feats["eye.right_openness"] < MIN_OPENNESS)
                        if closed and not eyes_closed_open:
                            events.append(EventRow(
                                event_type="eyes_closed", native_clock_id=NATIVE_CLOCK_ID,
                                onset_native_ts=ts_ms, offset_native_ts=None,
                                stimulus_id=None, metadata=None))
                            eyes_closed_open = True
                        elif not closed and eyes_closed_open:
                            _close(events, "eyes_closed", ts_ms)
                            eyes_closed_open = False

                        if not closed:
                            iris_ok += 1
                            for ch, v in feats.items():
                                signals.append(SignalRow(
                                    stream="gaze", channel=ch,
                                    native_clock_id=NATIVE_CLOCK_ID, native_ts=ts_ms,
                                    value=v, reliability_tier=RELIABILITY[ch]))

                            if result.facial_transformation_matrixes:
                                yaw, pitch, roll = euler_from_matrix(
                                    result.facial_transformation_matrixes[0])
                                for axis, v in (("yaw", yaw), ("pitch", pitch), ("roll", roll)):
                                    signals.append(SignalRow(
                                        stream="gaze", channel=f"head_pose.{axis}",
                                        native_clock_id=NATIVE_CLOCK_ID, native_ts=ts_ms,
                                        value=v, reliability_tier="high"))

                    if ts_ms - window_start >= QUALITY_WINDOW_MS:
                        quality.extend(_quality_rows(
                            window_start, ts_ms, frames, faces, iris_ok, lumas))
                        window_start, frames, faces, iris_ok = ts_ms, 0, 0, 0
                        lumas = []
        finally:
            cap.release()

        if window_start is not None and frames:
            quality.extend(_quality_rows(
                window_start, last_ts, frames, faces, iris_ok, lumas))

        yield Chunk(signals=tuple(signals), events=tuple(events), quality=tuple(quality))


def _close(events: list[EventRow], event_type: str, ts_ms: float) -> None:
    for e in reversed(events):
        if e.event_type == event_type and e.offset_native_ts is None:
            events[events.index(e)] = EventRow(
                event_type=e.event_type, native_clock_id=e.native_clock_id,
                onset_native_ts=e.onset_native_ts, offset_native_ts=ts_ms,
                stimulus_id=e.stimulus_id, metadata=e.metadata)
            return


def _quality_rows(start, end, frames, faces, iris_ok, lumas) -> list[QualityRow]:
    span_s = max((end - start) / 1000.0, 1e-9)

    def row(metric: str, value: float) -> QualityRow:
        return QualityRow(stream="gaze", metric=metric,
                          window_start_native_ts=start, window_end_native_ts=end,
                          value=value)

    rows = [
        row("achieved_fps", frames / span_s),
        row("face_detect_rate", faces / frames if frames else 0.0),
        # Deliberately a separate metric from face_detect_rate: a face can be
        # tracked confidently while the eyes are shut, turned away or too small
        # to localise an iris in. Only this figure says gaze was measurable.
        row("iris_valid_rate", iris_ok / frames if frames else 0.0),
    ]
    if lumas:
        rows.append(row("mean_luminance", float(np.median(lumas))))
    return rows

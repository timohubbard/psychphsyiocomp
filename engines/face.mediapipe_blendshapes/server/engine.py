"""face.mediapipe_blendshapes — server-batch placement.

The same engine_id as the browser-live placement, over the uploaded video
rather than the live stream. They emit different ``source`` values
(``...@version+browser-live`` vs ``...@version+server-batch``) so their outputs
sit side by side in ``signals`` and can be compared, rather than one silently
overwriting the other.

That duality is the M0 success criterion, and it is the concrete form of the
record-first/infer-later decision: REPORT.md §2.2 found engine choice swung
valid-face-frame yield 43%->63% on *identical video*, so the authoritative pass
has to be re-runnable server-side over stored media. The browser pass exists for
live participant feedback, not for the record.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import mediapipe as mp

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

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

#: Blendshape names MediaPipe emits that we drop — neutral is a residual.
IGNORED_BLENDSHAPES = frozenset({"_neutral"})

#: Rolling quality window, matched to the browser placement so the two are
#: directly comparable.
QUALITY_WINDOW_MS = 5000.0

#: The clock a decoded video file is stamped against. Frame presentation
#: timestamps come from the container, not from a wall clock — keeping this
#: distinct from the browser's ``performance.now`` is what lets the alignment
#: service reason about them separately (REPORT.md §3.3).
NATIVE_CLOCK_ID = "video_pts"


def _load_manifest_json() -> dict[str, Any]:
    with _MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_manifest() -> EngineManifest:
    """Build the typed manifest from the shared JSON, overriding placement.

    The JSON is the single source of truth for engine_id, version and licence —
    the licence inventory tool reads that same file, so they cannot drift.
    """
    raw = _load_manifest_json()
    lic = raw["license"]
    prov = raw.get("provenance", {})

    return EngineManifest(
        engine_id=raw["engine_id"],
        version=raw["version"],
        modality=raw["modality"],
        runtime="python-cpu",
        placement="server-batch",
        inputs=[
            InputSpec(
                kind="video",
                min_fps=5.0,
                min_width=320,
                min_height=240,
                min_roi_luminance=30.0,
            )
        ],
        params_schema=raw["params_schema"],
        outputs=EngineOutputs(
            signals=[
                SignalSpec(
                    channel="blendshape.*",
                    unit="score",
                    nominal_rate_hz=30.0,
                    value_type="float",
                    value_range=(0.0, 1.0),
                    reliability_tier="moderate",
                    description=(
                        "52 ARKit-style blendshape coefficients. NOT FACS action "
                        "units — emitted under blendshape.* and never relabelled."
                    ),
                ),
                *[
                    SignalSpec(
                        channel=f"head_pose.{axis}",
                        unit="deg",
                        nominal_rate_hz=30.0,
                        value_type="float",
                        reliability_tier="high",
                    )
                    for axis in ("yaw", "pitch", "roll")
                ],
            ],
            events=[
                EventSpec(
                    event_type="face_lost",
                    description="Face detection dropped below presence confidence",
                    has_offset=True,
                )
            ],
            quality=[
                QualitySpec(
                    metric="achieved_fps",
                    unit="hz",
                    warn_below=5.0,
                    description=(
                        "Measured, never assumed. §2.1 measured 9-39 fps jittered "
                        "across home setups; §5.3 uses 5 Hz as an exclusion threshold."
                    ),
                ),
                QualitySpec(
                    metric="face_detect_rate",
                    unit="proportion",
                    warn_below=0.5,
                    description=(
                        "§2.2 measured 43% (AFFDEX) vs 62-63% (FaceReader/Py-Feat) "
                        "on identical video."
                    ),
                ),
                QualitySpec(
                    metric="mean_luminance",
                    unit="level",
                    warn_below=30.0,
                    description=(
                        "§2.5: the rPPG skin-tone accuracy gap largely closes at "
                        ">=30. The only quantified bias mitigation in the evidence base."
                    ),
                ),
            ],
        ),
        license=EngineLicense(
            spdx=lic["spdx"],
            commercial_use=lic["commercial_use"],
            url=lic["url"],
            notes=lic.get("notes"),
        ),
        provenance=EngineProvenance(
            training_datasets=tuple(prov.get("training_datasets", ())),
            paper_doi=prov.get("paper_doi"),
        ),
    )


def euler_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """Yaw/pitch/roll in degrees from a 4x4 facial transformation matrix.

    Decomposed as R = Ry(yaw) @ Rx(pitch) @ Rz(roll) — intrinsic Y-X-Z, the
    head-pose convention. NOT the aerospace Z-Y-X ordering, under which a pure
    X-rotation decomposes into roll, i.e. a nod would be reported as a head
    tilt. Mirrors browser/pose.js; both are pinned by tests.

    MediaPipe's Python API returns row-major ndarray, unlike the column-major
    flat array the JS API emits — hence the different indexing from pose.js.
    """
    r = np.asarray(m, dtype=float)
    if r.shape != (4, 4):
        raise ValueError(f"expected a 4x4 matrix, got shape {r.shape}")

    r02, r10, r11, r12, r22 = r[0, 2], r[1, 0], r[1, 1], r[1, 2], r[2, 2]

    pitch = math.atan2(-r12, math.hypot(r10, r11))
    yaw = math.atan2(r02, r22)
    roll = math.atan2(r10, r11)

    return math.degrees(yaw), math.degrees(pitch), math.degrees(roll)


def mean_luma(frame_bgr: np.ndarray) -> float:
    """Rec. 601 luma over a downsampled frame.

    §2.5 is why this exists: the rPPG accuracy gap between Fitzpatrick type 1
    and type 5 collapses from ~2.25 bpm to ~0.21 bpm once luminance clears 30.
    That is the only quantified bias mitigation anywhere in the evidence base,
    so this is a fairness control, not a diagnostic nicety.
    """
    small = cv2.resize(frame_bgr, (32, 32), interpolation=cv2.INTER_AREA)
    b, g, r = small[:, :, 0], small[:, :, 1], small[:, :, 2]
    return float(np.mean(0.299 * r + 0.587 * g + 0.114 * b))


def sha256_of(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk_size):
            h.update(block)
    return h.hexdigest()


def describe_video(path: str | Path) -> MediaDescriptor:
    """Build a MediaDescriptor by probing a video file."""
    p = Path(path)
    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        raise OSError(f"could not open video: {p}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
        n_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Sample a handful of frames for mean luminance rather than decoding
        # the whole file just to probe.
        lumas: list[float] = []
        for i in range(5):
            cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(n_frames * i / 5)))
            ok, frame = cap.read()
            if ok:
                lumas.append(mean_luma(frame))
    finally:
        cap.release()

    return MediaDescriptor(
        path=str(p),
        kind="video",
        sha256=sha256_of(p),
        duration_s=(n_frames / fps) if fps else 0.0,
        fps=fps or None,
        width=width or None,
        height=height or None,
        mean_roi_luminance=float(np.mean(lumas)) if lumas else None,
    )


class MediaPipeBlendshapesBatch:
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
        """Distinct from the browser placement, so both can coexist in `signals`."""
        return f"{self.manifest.source}+server-batch"

    def probe(self, media: MediaDescriptor) -> Eligibility:
        """Can this engine run on this media, and if not, why not?

        Returns rather than raises. An ineligible-but-valid file must produce a
        recorded reason, not a silent skip — that is how the report's traps
        become machine-enforced instead of tribal knowledge.
        """
        reasons: list[str] = []
        details: list[str] = []

        spec = self.manifest.inputs[0]

        if media.kind != "video":
            reasons.append("wrong_media_kind")
            details.append(f"expected video, got {media.kind}")

        if spec.min_fps and media.fps is not None and media.fps < spec.min_fps:
            reasons.append("fps_below_min")
            details.append(f"{media.fps:.1f} fps < {spec.min_fps} fps")

        if spec.min_width and media.width is not None and media.width < spec.min_width:
            reasons.append("resolution_below_min")
            details.append(f"width {media.width} < {spec.min_width}")

        if spec.min_height and media.height is not None and media.height < spec.min_height:
            reasons.append("resolution_below_min")
            details.append(f"height {media.height} < {spec.min_height}")

        # Luminance is a warning, not a hard block: a dim session still yields
        # usable blendshapes, and refusing outright would discard data the
        # researcher may legitimately want. It is recorded either way so the
        # §2.5 bias risk is visible at analysis time rather than invisible.
        if (
            spec.min_roi_luminance
            and media.mean_roi_luminance is not None
            and media.mean_roi_luminance < spec.min_roi_luminance
        ):
            details.append(
                f"mean luminance {media.mean_roi_luminance:.1f} < "
                f"{spec.min_roi_luminance} — elevated demographic bias risk (§2.5)"
            )

        return Eligibility(
            eligible=not reasons,
            reasons=tuple(reasons),
            detail="; ".join(details) if details else None,
        )

    def run(
        self, media: MediaDescriptor, params: dict[str, Any] | None = None
    ) -> Iterator[Chunk]:
        """Decode the video and yield one Chunk per frame that produced output."""
        params = {
            "min_face_detection_confidence": 0.5,
            "min_face_presence_confidence": 0.5,
            "min_tracking_confidence": 0.5,
            **(params or {}),
        }

        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
            min_face_detection_confidence=params["min_face_detection_confidence"],
            min_face_presence_confidence=params["min_face_presence_confidence"],
            min_tracking_confidence=params["min_tracking_confidence"],
        )

        cap = cv2.VideoCapture(media.path)
        if not cap.isOpened():
            raise OSError(f"could not open video: {media.path}")

        window_start: float | None = None
        frames_seen = 0
        frames_with_face = 0
        luma_sum = 0.0
        luma_count = 0
        face_lost_at: float | None = None
        last_ts = 0.0

        try:
            with vision.FaceLandmarker.create_from_options(options) as landmarker:
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok:
                        break

                    # Presentation timestamp from the container. This is the
                    # engine's NATIVE clock; it never converts to any other.
                    ts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                    if ts_ms <= last_ts and frames_seen > 0:
                        # Some containers report a flat or non-monotonic PTS.
                        # MediaPipe requires strictly increasing timestamps in
                        # VIDEO mode, so synthesise from the nominal rate.
                        ts_ms = last_ts + (1000.0 / (media.fps or 30.0))
                    last_ts = ts_ms

                    if window_start is None:
                        window_start = ts_ms
                    frames_seen += 1

                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(mp_image, int(ts_ms))

                    signals: list[SignalRow] = []
                    events: list[EventRow] = []

                    has_face = bool(result.face_blendshapes)

                    if has_face:
                        frames_with_face += 1
                        if face_lost_at is not None:
                            events.append(
                                EventRow(
                                    event_type="face_lost",
                                    native_clock_id=NATIVE_CLOCK_ID,
                                    onset_native_ts=face_lost_at,
                                    offset_native_ts=ts_ms,
                                )
                            )
                            face_lost_at = None

                        for cat in result.face_blendshapes[0]:
                            if cat.category_name in IGNORED_BLENDSHAPES:
                                continue
                            signals.append(
                                SignalRow(
                                    stream="face",
                                    channel=f"blendshape.{cat.category_name}",
                                    native_clock_id=NATIVE_CLOCK_ID,
                                    native_ts=ts_ms,
                                    value=float(cat.score),
                                    reliability_tier="moderate",
                                )
                            )

                        if result.facial_transformation_matrixes:
                            yaw, pitch, roll = euler_from_matrix(
                                result.facial_transformation_matrixes[0]
                            )
                            for axis, value in (
                                ("yaw", yaw),
                                ("pitch", pitch),
                                ("roll", roll),
                            ):
                                signals.append(
                                    SignalRow(
                                        stream="face",
                                        channel=f"head_pose.{axis}",
                                        native_clock_id=NATIVE_CLOCK_ID,
                                        native_ts=ts_ms,
                                        value=value,
                                        reliability_tier="high",
                                    )
                                )
                    elif face_lost_at is None:
                        face_lost_at = ts_ms

                    luma_sum += mean_luma(frame_bgr)
                    luma_count += 1

                    quality: list[QualityRow] = []
                    if window_start is not None and ts_ms - window_start >= QUALITY_WINDOW_MS:
                        quality = self._quality_rows(
                            window_start, ts_ms, frames_seen, frames_with_face,
                            luma_sum, luma_count,
                        )
                        window_start = ts_ms
                        frames_seen = frames_with_face = luma_count = 0
                        luma_sum = 0.0

                    if signals or events or quality:
                        yield Chunk(
                            signals=tuple(signals),
                            events=tuple(events),
                            quality=tuple(quality),
                        )
        finally:
            cap.release()

        # Trailing partial window, plus any unclosed face_lost. A 40-second clip
        # must not silently produce zero quality rows just because it never
        # filled a 5-second window boundary.
        tail_events: list[EventRow] = []
        if face_lost_at is not None:
            tail_events.append(
                EventRow(
                    event_type="face_lost",
                    native_clock_id=NATIVE_CLOCK_ID,
                    onset_native_ts=face_lost_at,
                    offset_native_ts=last_ts,
                )
            )
        tail_quality: list[QualityRow] = []
        if window_start is not None and frames_seen > 0:
            tail_quality = self._quality_rows(
                window_start, last_ts, frames_seen, frames_with_face, luma_sum, luma_count
            )
        if tail_events or tail_quality:
            yield Chunk(events=tuple(tail_events), quality=tuple(tail_quality))

    @staticmethod
    def _quality_rows(
        start: float,
        end: float,
        frames_seen: int,
        frames_with_face: int,
        luma_sum: float,
        luma_count: int,
    ) -> list[QualityRow]:
        elapsed = max(end - start, 1.0)
        rows = [
            QualityRow(
                stream="face",
                metric="achieved_fps",
                window_start_native_ts=start,
                window_end_native_ts=end,
                value=(frames_seen / elapsed) * 1000.0,
            ),
            QualityRow(
                stream="face",
                metric="face_detect_rate",
                window_start_native_ts=start,
                window_end_native_ts=end,
                value=frames_with_face / frames_seen if frames_seen else 0.0,
            ),
        ]
        if luma_count:
            rows.append(
                QualityRow(
                    stream="face",
                    metric="mean_luminance",
                    window_start_native_ts=start,
                    window_end_native_ts=end,
                    value=luma_sum / luma_count,
                )
            )
        return rows

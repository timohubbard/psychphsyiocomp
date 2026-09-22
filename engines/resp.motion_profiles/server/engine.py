"""resp.motion_profiles — respiration from chest and shoulder motion.

The genuine build of the four modalities: §2.4 found no validated open
implementation and no surviving accuracy figure, so there was nothing to
integrate.

IT DOES NOT EMIT A BREATHING RATE BY DEFAULT. After two dedicated research
passes, no verified breaths-per-minute figure against a chest belt, RIP or
spirometry survived adversarial checking, and one specific figure was explicitly
refuted. A breathing rate is a number a clinician would recognise on sight, and
shipping one this project cannot defend would be the most damaging thing it
could do. What it emits instead is the waveform and a confidence channel — which
is the more valuable output anyway, since inhale-onset, breath-hold and sigh
events need no calibrated rate.

THE GRID IS KEPT APART ON PURPOSE. §2.4's one surviving algorithmic finding is
that multiple 1D or 2D motion profiles outperform single-combined-1D-profile
approaches. Averaging the ROI into one signal is the obvious implementation and
the specific thing the evidence says not to do; the maths for the fusion lives in
`server/respiration.py`, where it is measured against a naive average rather
than asserted.

THE ROI IS A SHOULDER LINE, NOT A CHEST. Most at-home framing is head and
shoulders, so shoulder-line motion is frequently the only chest signal in frame.
That is a different regime from the clinical chest-camera papers, and probably
part of why no published figure transfers.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import json
import sys
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
from engine_contract.media import mean_luma

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server"))
from respiration import (  # noqa: E402
    WAVEFORM_RATE_HZ,
    assess_confidence,
    estimate_rate,
    fuse_profiles,
    resample,
)

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

NATIVE_CLOCK_ID = "video_pts"

#: Analysis segment. Long enough to contain several breaths at the slow end of
#: the band (7.5/min is one breath per eight seconds), short enough that a
#: participant shifting position does not contaminate the whole session.
SEGMENT_S = 30.0

#: MediaPipe Pose landmark indices for the shoulders.
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12

#: ROI width is scaled down before optical flow. Chest motion at laptop distance
#: is often sub-pixel, and a mean over many pixels per cell is how sub-pixel
#: displacement becomes measurable — but the flow field itself does not need
#: full resolution, and Farneback at 720p over thousands of frames is the whole
#: cost of this engine.
ROI_WIDTH_PX = 192


def _load_manifest_json() -> dict[str, Any]:
    with _MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _build_manifest() -> EngineManifest:
    raw = _load_manifest_json()
    lic = raw["license"]

    def sig(channel: str, unit: str, rate: float, tier: str) -> SignalSpec:
        return SignalSpec(channel=channel, unit=unit, nominal_rate_hz=rate,
                          value_type="float", reliability_tier=tier)

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
                sig("respiration.waveform", "normalised", WAVEFORM_RATE_HZ, "low"),
                sig("respiration.periodicity", "proportion", 0.2, "moderate"),
                sig("respiration.cells_used", "count", 0.2, "high"),
                sig("respiration.gross_motion", "normalised", 0.2, "high"),
            ],
            events=[EventSpec(event_type="roi_lost", has_offset=True,
                              description="No shoulder line could be located")],
            quality=[
                QualitySpec(metric="analysis_fps", unit="hz", warn_below=2.0,
                            description="Below ~2 Hz the waveform shape does not survive."),
                QualitySpec(metric="roi_found_rate", unit="proportion", warn_below=0.5,
                            description="Fraction of frames with a locatable shoulder line."),
                QualitySpec(metric="usable_fraction", unit="proportion", warn_below=0.3,
                            description="Segments passing every confidence check."),
                QualitySpec(metric="mean_luminance", unit="level", warn_below=30.0,
                            description="§2.5's fairness floor applies to any camera-based physiology."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(),
    )


def roi_from_shoulders(landmarks, width: int, height: int) -> tuple[int, int, int, int] | None:
    """Bounding box below the shoulder line, from two pose keypoints.

    The box spans the shoulders horizontally and extends downward by the same
    distance, which lands on the upper chest for a head-and-shoulders framing.
    Only the two shoulder points are read — nothing else about the body is
    looked at or retained.
    """
    if landmarks is None or len(landmarks) <= max(LEFT_SHOULDER, RIGHT_SHOULDER):
        return None

    ls, rs = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]
    x0, x1 = sorted((ls.x * width, rs.x * width))
    y_line = max(ls.y, rs.y) * height
    span = x1 - x0
    if span < 20:
        return None

    top = int(max(0, y_line - span * 0.1))
    bottom = int(min(height, y_line + span * 0.9))
    left = int(max(0, x0))
    right = int(min(width, x1))

    if bottom - top < 16 or right - left < 16:
        return None
    return left, top, right, bottom


def fallback_roi(width: int, height: int) -> tuple[int, int, int, int]:
    """A fixed torso band, for when pose confidence is too low.

    Recorded as a fallback rather than silently substituted: a session analysed
    from a guessed box is a weaker claim than one tracking a located shoulder
    line, and `roi_found_rate` is what tells them apart.
    """
    return (int(width * 0.25), int(height * 0.55),
            int(width * 0.75), int(height * 0.95))


def cell_profiles(roi_frames: list[np.ndarray], grid: tuple[int, int]) -> np.ndarray:
    """Per-cell vertical motion over a segment. Returns ``(n_cells, n_frames-1)``.

    Dense optical flow, and only its VERTICAL component. Breathing moves the
    chest and shoulder line up and down; the horizontal component is dominated
    by postural sway and by the participant turning to read the screen, and
    including it adds those without adding breath.
    """
    rows, cols = grid
    n_cells = rows * cols
    if len(roi_frames) < 2:
        return np.zeros((n_cells, 0))

    profiles = np.zeros((n_cells, len(roi_frames) - 1))

    for i in range(len(roi_frames) - 1):
        flow = cv2.calcOpticalFlowFarneback(
            roi_frames[i], roi_frames[i + 1], None,
            pyr_scale=0.5, levels=3, winsize=15, iterations=3,
            poly_n=5, poly_sigma=1.2, flags=0)
        vertical = flow[..., 1]

        h, w = vertical.shape
        for r in range(rows):
            for c in range(cols):
                cell = vertical[r * h // rows:(r + 1) * h // rows,
                                c * w // cols:(c + 1) * w // cols]
                profiles[r * cols + c, i] = float(np.mean(cell)) if cell.size else 0.0

    # Cumulative sum turns per-frame velocity into displacement. Breathing is a
    # displacement, and integrating before filtering keeps the waveform's shape
    # rather than its derivative — which is what an inhale ONSET is read from.
    return np.cumsum(profiles, axis=1)


class RespirationMotionProfiles:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self, pose_model_path: str | Path) -> None:
        self.manifest = _build_manifest()
        self._pose_path = Path(pose_model_path)
        self._pose = None

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
            details.append(f"{media.fps:.1f} fps")
        if spec.min_width and media.width is not None and media.width < spec.min_width:
            reasons.append("resolution_below_min")
            details.append(f"{media.width}x{media.height}")
        if (spec.min_roi_luminance and media.mean_roi_luminance is not None
                and media.mean_roi_luminance < spec.min_roi_luminance):
            reasons.append("luminance_below_min")
            details.append(f"{media.mean_roi_luminance:.0f} < 30")

        return Eligibility(eligible=not reasons, reasons=tuple(reasons),
                           detail="; ".join(details) if details else None)

    def _load_pose(self):
        if self._pose is None:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            self._pose = vision.PoseLandmarker.create_from_options(
                vision.PoseLandmarkerOptions(
                    base_options=mp_python.BaseOptions(
                        model_asset_path=str(self._pose_path)),
                    running_mode=vision.RunningMode.VIDEO,
                    num_poses=1))
            self._mp = mp
        return self._pose

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        grid = tuple(params.get("grid", (4, 4)))
        analysis_fps = float(params.get("analysis_fps", 10.0))
        top_k = int(params.get("top_k_cells", 4))
        emit_rate = bool(params.get("emit_rate_bpm", False))

        pose = self._load_pose()
        cap = cv2.VideoCapture(media.path)
        if not cap.isOpened():
            raise OSError(f"could not open {media.path}")

        src_fps = media.fps or 30.0
        stride = max(1, int(round(src_fps / analysis_fps)))
        effective_fps = src_fps / stride

        signals: list[SignalRow] = []
        events: list[EventRow] = []
        lumas: list[float] = []

        seg_frames: list[np.ndarray] = []
        seg_start_ts: float | None = None
        per_segment_usable: list[bool] = []
        roi_found = analysed = 0
        roi_lost_open = False
        index = 0
        last_ts = -1.0

        def flush_segment(end_ts: float) -> None:
            nonlocal seg_frames, seg_start_ts
            if seg_start_ts is None or len(seg_frames) < 8:
                seg_frames = []
                seg_start_ts = None
                return

            profiles = cell_profiles(seg_frames, grid)
            fusion = fuse_profiles(profiles, effective_fps, top_k=top_k)

            gross = float(np.mean(np.abs(np.diff(
                [float(np.mean(f)) for f in seg_frames])))) if len(seg_frames) > 1 else 0.0
            conf = assess_confidence(
                fusion, effective_fps=effective_fps,
                roi_luminance=float(np.median(lumas)) if lumas else None,
                gross_motion=gross)
            per_segment_usable.append(conf.usable)

            for channel, value in (
                ("respiration.periodicity", conf.periodicity),
                ("respiration.cells_used", float(conf.cells_used)),
                ("respiration.gross_motion", gross),
            ):
                signals.append(SignalRow(
                    stream="respiration", channel=channel,
                    native_clock_id=NATIVE_CLOCK_ID, native_ts=seg_start_ts,
                    value=value,
                    reliability_tier="high" if channel != "respiration.periodicity"
                    else "moderate"))

            # The waveform is emitted only when the segment is usable. A
            # waveform nobody should trust, emitted beside one they should,
            # becomes indistinguishable the moment it is plotted.
            if conf.usable and fusion.refusal is None:
                wave, dt_ms = resample(fusion.waveform, effective_fps)
                for i, v in enumerate(wave):
                    signals.append(SignalRow(
                        stream="respiration", channel="respiration.waveform",
                        native_clock_id=NATIVE_CLOCK_ID,
                        native_ts=seg_start_ts + i * dt_ms,
                        value=float(v), reliability_tier="low"))

                if emit_rate:
                    # Reachable only by explicit opt-in. See the manifest's
                    # capability_notes.no_validated_rate.
                    rate = estimate_rate(fusion.waveform, effective_fps)
                    if rate.confident:
                        signals.append(SignalRow(
                            stream="respiration", channel="respiration.rate_bpm",
                            native_clock_id=NATIVE_CLOCK_ID, native_ts=seg_start_ts,
                            value=float(rate.bpm), reliability_tier="low"))

            seg_frames = []
            seg_start_ts = None

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
                if ts_ms <= last_ts and analysed > 0:
                    ts_ms = last_ts + (1000.0 / effective_fps)
                last_ts = ts_ms
                analysed += 1
                lumas.append(mean_luma(frame_bgr))

                h, w = frame_bgr.shape[:2]
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                result = pose.detect_for_video(
                    self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb),
                    int(ts_ms))

                box = None
                if result.pose_landmarks:
                    box = roi_from_shoulders(result.pose_landmarks[0], w, h)

                if box is None:
                    if not roi_lost_open:
                        events.append(EventRow(
                            event_type="roi_lost", native_clock_id=NATIVE_CLOCK_ID,
                            onset_native_ts=ts_ms, offset_native_ts=None,
                            stimulus_id=None, metadata=None))
                        roi_lost_open = True
                    box = fallback_roi(w, h)
                else:
                    roi_found += 1
                    if roi_lost_open:
                        _close(events, "roi_lost", ts_ms)
                        roi_lost_open = False

                x0, y0, x1, y1 = box
                roi = cv2.cvtColor(frame_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
                scale = ROI_WIDTH_PX / max(roi.shape[1], 1)
                if scale < 1.0:
                    roi = cv2.resize(roi, (ROI_WIDTH_PX, max(8, int(roi.shape[0] * scale))),
                                     interpolation=cv2.INTER_AREA)

                if seg_start_ts is None:
                    seg_start_ts = ts_ms
                # A resized ROI can change shape between frames as the shoulder
                # box moves; optical flow needs a constant one.
                if seg_frames and roi.shape != seg_frames[0].shape:
                    roi = cv2.resize(roi, (seg_frames[0].shape[1], seg_frames[0].shape[0]),
                                     interpolation=cv2.INTER_AREA)
                seg_frames.append(roi)

                if ts_ms - seg_start_ts >= SEGMENT_S * 1000.0:
                    flush_segment(ts_ms)
        finally:
            cap.release()

        flush_segment(last_ts)

        quality = [
            QualityRow(stream="respiration", metric="analysis_fps",
                       window_start_native_ts=0.0, window_end_native_ts=last_ts,
                       value=effective_fps),
            QualityRow(stream="respiration", metric="roi_found_rate",
                       window_start_native_ts=0.0, window_end_native_ts=last_ts,
                       value=roi_found / analysed if analysed else 0.0),
            QualityRow(stream="respiration", metric="usable_fraction",
                       window_start_native_ts=0.0, window_end_native_ts=last_ts,
                       value=(sum(per_segment_usable) / len(per_segment_usable))
                       if per_segment_usable else 0.0),
        ]
        if lumas:
            quality.append(QualityRow(
                stream="respiration", metric="mean_luminance",
                window_start_native_ts=0.0, window_end_native_ts=last_ts,
                value=float(np.median(lumas))))

        yield Chunk(signals=tuple(signals), events=tuple(events), quality=tuple(quality))


def _close(events: list[EventRow], event_type: str, ts_ms: float) -> None:
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        if e.event_type == event_type and e.offset_native_ts is None:
            events[i] = EventRow(
                event_type=e.event_type, native_clock_id=e.native_clock_id,
                onset_native_ts=e.onset_native_ts, offset_native_ts=ts_ms,
                stimulus_id=e.stimulus_id, metadata=e.metadata)
            return

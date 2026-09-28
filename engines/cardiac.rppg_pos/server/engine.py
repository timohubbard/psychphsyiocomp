"""cardiac.rppg_pos — pulse from facial skin colour, server-batch.

Per frame: find the face (MediaPipe FaceLandmarker, VIDEO mode), fill the
forehead and both cheeks as a mask, and average the skin's colour inside it.
Everything after that — resampling, POS, band-pass, the per-window rate and its
gates — is server/rppg.py, pure and tested on planted pulses.

Why those three regions: they are the facial skin with the most blood flow
and the least movement. The eyes, brows, mouth and nostrils are left out
because blinking and speaking change their colour far more than any pulse.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "server"))
from rppg import RATE_HZ, analyse  # noqa: E402

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

NATIVE_CLOCK_ID = "video_pts"

#: MediaPipe face-mesh landmarks bounding each skin region: a band across the
#: forehead above the brows, and a patch on each cheek clear of the nose and
#: the mouth's corners.
FOREHEAD = (109, 10, 338, 337, 151, 108)
LEFT_CHEEK = (117, 118, 50, 205, 187, 123)
RIGHT_CHEEK = (346, 347, 280, 425, 411, 352)
REGIONS = (FOREHEAD, LEFT_CHEEK, RIGHT_CHEEK)

#: The mask is built on a downscaled frame: the mean over thousands of skin
#: pixels does not need full resolution, and the fill is most of the cost.
WORK_WIDTH = 320

#: Saturated pixels carry no colour change; very dark ones carry mostly noise.
CLIP_HIGH, CLIP_LOW = 250, 8


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
        engine_id=raw["engine_id"], version=raw["version"], modality=raw["modality"],
        runtime="python-cpu", placement="server-batch",
        inputs=[InputSpec(kind="video", min_fps=10.0, min_width=320, min_height=240,
                          min_roi_luminance=30.0)],
        params_schema=raw["params_schema"],
        outputs=EngineOutputs(
            signals=[sig("cardiac.bvp", "normalised", RATE_HZ, "unvalidated"),
                     sig("cardiac.hr_bpm", "bpm", 0.5, "unvalidated"),
                     sig("cardiac.snr_db", "dB", 0.5, "high"),
                     sig("cardiac.skin_luma", "level", 0.5, "high")],
            events=[EventSpec(event_type="roi_lost", has_offset=True,
                              description="No face, so no skin region")],
            quality=[
                QualitySpec(metric="face_found_rate", unit="proportion", warn_below=0.8,
                            description="Frames with a located face and skin region."),
                QualitySpec(metric="hr_window_pass_rate", unit="proportion", warn_below=0.5,
                            description="Heart-rate windows passing the SNR and luminance gates."),
                QualitySpec(metric="hr_median_bpm", unit="bpm", warn_below=None,
                            description="Median of passing windows."),
                QualitySpec(metric="skin_luminance", unit="level", warn_below=30.0,
                            description="Median skin-region luminance."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(),
    )


def skin_mask(landmarks, width: int, height: int) -> np.ndarray | None:
    """The forehead and cheek regions as one mask, or None if too small to trust."""
    if landmarks is None or len(landmarks) <= max(max(r) for r in REGIONS):
        return None
    mask = np.zeros((height, width), dtype=np.uint8)
    for region in REGIONS:
        pts = np.array([[landmarks[i].x * width, landmarks[i].y * height] for i in region], dtype=np.float32)
        hull = cv2.convexHull(pts).astype(np.int32)
        cv2.fillConvexPoly(mask, hull, 255)
    return mask if int(mask.sum() // 255) >= 50 else None


def skin_colour(frame_bgr: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Mean RGB and luminance of the unclipped skin pixels under the mask."""
    px = frame_bgr[mask > 0].astype(np.float64)
    ok = (px.max(axis=1) < CLIP_HIGH) & (px.min(axis=1) > CLIP_LOW)
    if ok.sum() < 30:
        return None
    b, g, r = px[ok].mean(axis=0)
    return np.array([r, g, b]), float(0.299 * r + 0.587 * g + 0.114 * b)


class RppgPOS:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self, model_path: str | Path) -> None:
        self.manifest = _build_manifest()
        self._model = Path(model_path)
        if not self._model.exists():
            raise FileNotFoundError(f"face landmarker model not found: {self._model} (npm run models)")

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
            # Nyquist for the top of the band (4 Hz) is 8 fps; 10 leaves a margin.
            reasons.append("fps_below_min")
            details.append(f"{media.fps:.1f} fps")
        if spec.min_width and media.width is not None and media.width < spec.min_width:
            reasons.append("resolution_below_min")
            details.append(f"{media.width}x{media.height}")
        return Eligibility(eligible=not reasons, reasons=tuple(reasons),
                           detail="; ".join(details) if details else None)

    def trace(self, media: MediaDescriptor, max_frames: int | None = None):
        """Per-frame (ts_ms, rgb, luma), with NaN rows where there was no skin."""
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        opts = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._model)),
            running_mode=vision.RunningMode.VIDEO, num_faces=1,
            output_face_blendshapes=False, output_facial_transformation_matrixes=False,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5)
        cap = cv2.VideoCapture(str(media.path))
        fps = cap.get(cv2.CAP_PROP_FPS) or media.fps or 30.0
        ts_list, rgb_list, luma_list = [], [], []
        last_ts = -1.0
        with vision.FaceLandmarker.create_from_options(opts) as lm:
            while True:
                ok, frame = cap.read()
                if not ok or (max_frames and len(ts_list) >= max_frames):
                    break
                ts = cap.get(cv2.CAP_PROP_POS_MSEC)
                if ts <= last_ts:
                    ts = last_ts + 1000.0 / fps
                last_ts = ts
                h, w = frame.shape[:2]
                small = cv2.resize(frame, (WORK_WIDTH, int(h * WORK_WIDTH / w))) if w > WORK_WIDTH else frame
                rgb_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                res = lm.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_img), int(ts))
                got = None
                if res.face_landmarks:
                    mask = skin_mask(res.face_landmarks[0], small.shape[1], small.shape[0])
                    if mask is not None:
                        got = skin_colour(small, mask)
                ts_list.append(ts)
                if got is None:
                    rgb_list.append([np.nan] * 3)
                    luma_list.append(np.nan)
                else:
                    rgb_list.append(got[0])
                    luma_list.append(got[1])
        cap.release()
        return np.array(ts_list), np.array(rgb_list, dtype=float), np.array(luma_list, dtype=float)

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        ts, rgb, luma = self.trace(media)
        yield from self.from_trace(ts, rgb, luma, params)

    def from_trace(self, ts: np.ndarray, rgb: np.ndarray, luma: np.ndarray,
                   params: dict[str, Any]) -> Iterator[Chunk]:
        """Everything after the per-frame extraction — separate, so it is testable on a trace."""
        found = ~np.isnan(luma)
        waves, windows = analyse(ts, rgb, luma,
                                 window_s=float(params.get("hr_window_s", 10.0)),
                                 step_s=float(params.get("hr_step_s", 2.0)),
                                 min_snr_db=float(params.get("min_snr_db", 0.0)),
                                 pos_window_s=float(params.get("pos_window_s", 1.6)))
        signals: list[SignalRow] = []
        for grid, bvp in waves:
            signals += [SignalRow(stream="cardiac", channel="cardiac.bvp", native_clock_id=NATIVE_CLOCK_ID,
                                  native_ts=float(t), value=float(v), reliability_tier="unvalidated")
                        for t, v in zip(grid, bvp)]
        for w in windows:
            if w.snr_db is not None and np.isfinite(w.snr_db):
                signals.append(SignalRow(stream="cardiac", channel="cardiac.snr_db", native_clock_id=NATIVE_CLOCK_ID,
                                         native_ts=w.center_ms, value=float(w.snr_db), reliability_tier="high"))
            signals.append(SignalRow(stream="cardiac", channel="cardiac.skin_luma", native_clock_id=NATIVE_CLOCK_ID,
                                     native_ts=w.center_ms, value=float(w.luma), reliability_tier="high"))
            if w.passed:
                signals.append(SignalRow(stream="cardiac", channel="cardiac.hr_bpm", native_clock_id=NATIVE_CLOCK_ID,
                                         native_ts=w.center_ms, value=float(w.hr_bpm), reliability_tier="unvalidated"))

        events = []
        i, n = 0, len(ts)
        while i < n:
            if not found[i]:
                j = i
                while j + 1 < n and not found[j + 1]:
                    j += 1
                if ts[j] - ts[i] >= 500:
                    events.append(EventRow(event_type="roi_lost", native_clock_id=NATIVE_CLOCK_ID,
                                           onset_native_ts=float(ts[i]), offset_native_ts=float(ts[j]),
                                           metadata={"frames": int(j - i + 1)}))
                i = j + 1
            else:
                i += 1

        end = float(ts[-1]) if len(ts) else 0.0
        passed = [w for w in windows if w.passed]
        metrics = {
            "face_found_rate": float(found.mean()) if len(found) else 0.0,
            "hr_window_pass_rate": len(passed) / len(windows) if windows else 0.0,
            "skin_luminance": float(np.nanmedian(luma)) if found.any() else 0.0,
        }
        if passed:
            metrics["hr_median_bpm"] = float(np.median([w.hr_bpm for w in passed]))
        quality = tuple(QualityRow(stream="cardiac", metric=m, window_start_native_ts=0.0,
                                   window_end_native_ts=end, value=v) for m, v in metrics.items())
        yield Chunk(signals=tuple(signals), events=tuple(events), quality=quality)

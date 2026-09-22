"""face.opengraphau_aus — the second Action Unit engine, for §2.2's cross-check.

It exists for one reason. §2.2 measured engine choice alone swinging
valid-face-frame yield 43%→63% and expression counts 3-4x on identical video,
with between-engine agreement at r = 0.37-0.75 — and that spread is the only
empirical handle on how much of a facial result is the face and how much is the
detector. With one AU engine the figure is unavailable. This is the other one.

**It has to be genuinely different, or the cross-check measures nothing.**
Py-Feat's AU model is gradient-boosted trees over HOG features of a
RetinaFace crop. This is a ResNet-50 with a graph head over AU relations
(ME-GraphAU, IJCAI 2022), fed by MediaPipe detection. Different detector,
different features, different model family, different training mix. Two
placements of one engine agree at ~0.9 (measured, see server/agreement.py);
two engines are what §2.2 describes.

**It emits occurrence scores, not intensities.** Each value is a cosine
similarity to a learned per-AU prototype, which upstream thresholds at 0.5. So
is Py-Feat's (`predict_proba` of an XGBoost classifier), which is why the two
can share channel names. Neither is calibrated, and an absolute 0.6 from one
does not mean an absolute 0.6 from the other — §2.2's instruction to report
relative within-participant proportions applies here with full force.

**It never emits an emotion**, for the reasons face.pyfeat_aus gives, and it
has no emotion head to decline.

**Laterality is off by default.** The model also scores left and right sides
of seven AUs. No per-side reliability figure exists in the evidence base, and
nothing else here emits them, so they could not be cross-checked; the contract
tiers them `low` if a study turns them on.

Contract: packages/engine-contract/python/engine_contract/manifest.py
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
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
from engine_contract.media import mean_luma

_HERE = Path(__file__).resolve().parent
_MANIFEST_JSON = _HERE.parent / "engine.manifest.json"

NATIVE_CLOCK_ID = "video_pts"
QUALITY_WINDOW_MS = 5000.0

#: Where the aligned face sits in the 256px image upstream resizes to before
#: its 224px centre crop, as fractions of the side.
#:
#: MEASURED, not chosen. All six of upstream's demo images are aligned the same
#: way — eyes level, the eye midpoint at (0.502, 0.487), inter-ocular distance
#: 0.234 of the width (range 0.219-0.244) — measured with the same MediaPipe
#: eye-corner landmarks this engine uses. That is a template, so frames are
#: warped onto it. A crop margin picked by eye would put every face at a scale
#: the network never saw, and nothing downstream would reveal it.
TEMPLATE_SIDE = 256
CROP_SIDE = 224
TEMPLATE_EYE_MID = (0.502, 0.487)
TEMPLATE_IOD = 0.234

#: MediaPipe FaceMesh eye-corner landmarks. Each eye's centre is the mean of its
#: two corners, which is stable under blinks where the iris landmarks are not.
IMAGE_LEFT_EYE = (33, 133)
IMAGE_RIGHT_EYE = (362, 263)

#: ImageNet statistics, as upstream's `image_eval` normalises.
_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _load_manifest_json() -> dict[str, Any]:
    with _MANIFEST_JSON.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_model_module():
    """The vendored network, under a name no other engine can collide with.

    Engines are loaded by path precisely because two same-named modules resolve
    by sys.path order (engine_contract/loader.py). A sibling `graphau_model`
    imported the ordinary way would reintroduce that hazard one level down.
    """
    name = "engine_impl_face_opengraphau_aus_graphau_model"
    import sys
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _HERE / "graphau_model.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


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
                        "Per-AU occurrence scores, not intensities. The tier on "
                        "each ROW is set per AU from the published per-unit "
                        "floor; this spec-level value is only a default."
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
                            description="Engine-specific; never compare across engines."),
                QualitySpec(metric="mean_luminance", unit="level", warn_below=30.0,
                            description="§2.5: the only quantified bias mitigation."),
                QualitySpec(metric="crop_outside_frame", unit="proportion",
                            description="Share of the aligned crop filled black."),
            ],
        ),
        license=EngineLicense(spdx=lic["spdx"], commercial_use=lic["commercial_use"],
                              url=lic["url"], notes=lic.get("notes")),
        provenance=EngineProvenance(
            training_datasets=tuple(prov.get("training_datasets", ())),
            weights_sha256=prov.get("weights_sha256"),
            paper_doi=prov.get("paper_doi"),
        ),
    )


# ---------------------------------------------------------------------------
# alignment
# ---------------------------------------------------------------------------

def eye_centres(landmarks_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(image-left eye, image-right eye) centres in pixels."""
    left = landmarks_px[list(IMAGE_LEFT_EYE)].mean(axis=0)
    right = landmarks_px[list(IMAGE_RIGHT_EYE)].mean(axis=0)
    return left, right


def alignment_matrix(left_eye: np.ndarray, right_eye: np.ndarray) -> np.ndarray:
    """2x3 similarity transform taking the frame onto the 224px model input.

    Rotates the eye line level, scales the inter-ocular distance to the
    template's, and places the eye midpoint where the template has it — then
    shifts by the centre-crop offset, so the one warp does what upstream's
    resize-then-crop does to an already-aligned image.
    """
    dx, dy = (right_eye - left_eye).astype(float)
    iod = math.hypot(dx, dy)
    if iod < 1e-6:
        raise ValueError("eyes coincide; cannot align")

    scale = TEMPLATE_IOD * TEMPLATE_SIDE / iod
    angle = math.degrees(math.atan2(dy, dx))
    mid = (left_eye + right_eye) / 2.0

    m = cv2.getRotationMatrix2D((float(mid[0]), float(mid[1])), angle, scale)
    offset = (TEMPLATE_SIDE - CROP_SIDE) / 2.0
    m[0, 2] += TEMPLATE_EYE_MID[0] * TEMPLATE_SIDE - offset - mid[0]
    m[1, 2] += TEMPLATE_EYE_MID[1] * TEMPLATE_SIDE - offset - mid[1]
    return m


def align_face(frame_bgr: np.ndarray, landmarks_px: np.ndarray) -> tuple[np.ndarray, float]:
    """Aligned RGB crop, plus the share of it that lay outside the frame.

    The outside share is returned rather than hidden. `warpAffine` fills
    off-frame pixels with black without complaint, and a face at the edge of
    the frame is then analysed partly on pixels nobody recorded.
    """
    m = alignment_matrix(*eye_centres(landmarks_px))
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    # Shrink with area averaging first, then warp at roughly 1:1. A bilinear
    # warp that downscales samples 4 source pixels of every 16 and aliases;
    # upstream's PIL resize antialiases. Measured on upstream's six demo images
    # against upstream's own preprocessing: mean per-AU error 0.019-0.054
    # warped directly, 0.013-0.026 shrunk first.
    scale = float(np.sqrt(abs(np.linalg.det(m[:, :2]))))
    if scale < 1.0:
        rgb = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        m = m.copy()
        m[:, :2] /= scale
    crop = cv2.warpAffine(rgb, m, (CROP_SIDE, CROP_SIDE), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)

    inside = cv2.warpAffine(np.full(rgb.shape[:2], 255, np.uint8), m, (CROP_SIDE, CROP_SIDE),
                            flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT,
                            borderValue=0)
    outside = 1.0 - float(np.count_nonzero(inside)) / inside.size
    return crop, outside


def to_tensor_batch(crops_rgb: list[np.ndarray]):
    import torch
    x = np.stack(crops_rgb).astype(np.float32) / 255.0
    x = (x - _MEAN) / _STD
    return torch.from_numpy(x).permute(0, 3, 1, 2).contiguous()


# ---------------------------------------------------------------------------
# weights
# ---------------------------------------------------------------------------

def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while block := fh.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def verify_weights(path: Path, expected_sha256: str | None) -> None:
    """Refuse a checkpoint that is not the one the manifest names.

    The weights come from a Google Drive link, which can be re-pointed without
    notice, and the run row cites the manifest's hash as the model that
    produced the numbers. A hash nothing checks would promise attributability
    it does not deliver.
    """
    if not Path(path).exists():
        raise FileNotFoundError(
            f"OpenGraphAU weights not found at {path}. Run `npm run models`.")
    if expected_sha256 is None:
        raise ValueError("manifest records no weights_sha256; refusing to guess")
    actual = sha256_of(path)
    if actual != expected_sha256:
        raise ValueError(
            f"weights at {path} have sha256 {actual[:16]}..., manifest expects "
            f"{expected_sha256[:16]}... — a different checkpoint would produce "
            "different numbers under this engine's name and version.")


class OpenGraphAUs:
    """Server-batch placement. Implements the Engine protocol."""

    def __init__(self, weights_path: str | Path, landmarker_path: str | Path,
                 device: str = "cpu") -> None:
        self.manifest = _build_manifest()
        self._weights = Path(weights_path)
        self._landmarker_path = Path(landmarker_path)
        self._device = device
        self._net = None

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

    def _load(self):
        if self._net is None:
            verify_weights(self._weights, self.manifest.provenance.weights_sha256)
            self._net = _load_model_module().load_checkpoint(self._weights).to(self._device)
        return self._net

    def run(self, media: MediaDescriptor, params: dict[str, Any]) -> Iterator[Chunk]:
        import torch

        gm = _load_model_module()
        net = self._load()

        # Py-Feat sets OMP_NUM_THREADS=1 when imported (a macOS workaround for
        # torch and xgboost loading different OpenMP runtimes), and that is
        # process-wide. Measured on the real session: after the Py-Feat engine
        # had run, this network ran on one core at roughly 20x its standalone
        # cost. Set for the duration of this engine only, and put back, so
        # Py-Feat's own choice still governs Py-Feat.
        threads = int(params.get("torch_threads") or (os.cpu_count() or 1))
        previous_threads = torch.get_num_threads()
        torch.set_num_threads(max(1, threads))
        try:
            yield from self._run(media, params, gm, net)
        finally:
            torch.set_num_threads(previous_threads)

    def _run(self, media: MediaDescriptor, params: dict[str, Any], gm, net) -> Iterator[Chunk]:
        import mediapipe as mp
        import torch
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision

        stride = max(1, int(params.get("frame_stride", 5)))
        batch_size = max(1, int(params.get("batch_size", 16)))
        emit_lateral = bool(params.get("emit_lateral", False))
        labels = list(gm.MAIN_AUS) + list(gm.LATERAL_AUS)
        n_emit = len(labels) if emit_lateral else len(gm.MAIN_AUS)
        keys = [normalise(f"AU{a}") for a in labels[:n_emit]]
        tiers = [reliability(k).tier for k in keys]

        # IMAGE mode, not VIDEO: every analysed frame is detected on its own
        # pixels. VIDEO mode tracks between calls, which at a stride of 5 would
        # make whether a face is "found" depend on the stride as well as on
        # the frame.
        options = vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(self._landmarker_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=float(
                params.get("min_face_detection_confidence", 0.5)),
        )

        cap = cv2.VideoCapture(media.path)
        if not cap.isOpened():
            raise OSError(f"could not open {media.path}")

        signals: list[SignalRow] = []
        events: list[EventRow] = []
        quality: list[QualityRow] = []
        lumas: list[float] = []
        outside: list[float] = []

        processed = faces = 0
        last_ts = -1.0
        window_start: float | None = None
        face_lost_open = False
        index = 0

        # (timestamp, crop or None) in frame order, so a face-less frame keeps
        # its place between the faces either side of it.
        pending: list[tuple[float, np.ndarray | None]] = []

        def flush() -> None:
            nonlocal processed, faces, face_lost_open
            if not pending:
                return
            crops = [c for _, c in pending if c is not None]
            scores = None
            if crops:
                with torch.no_grad():
                    scores = net(to_tensor_batch(crops).to(self._device)).cpu().numpy()

            k = 0
            for frame_ts, crop in pending:
                processed += 1
                found = crop is not None
                signals.append(SignalRow(
                    stream="face", channel="face.detected",
                    native_clock_id=NATIVE_CLOCK_ID, native_ts=frame_ts,
                    value=1.0 if found else 0.0, reliability_tier="high"))

                if found:
                    faces += 1
                    if face_lost_open:
                        _close(events, "face_lost", frame_ts)
                        face_lost_open = False
                    row = scores[k]
                    k += 1
                    for key, tier, value in zip(keys, tiers, row[:n_emit]):
                        signals.append(SignalRow(
                            stream="face", channel=f"au.{key}",
                            native_clock_id=NATIVE_CLOCK_ID, native_ts=frame_ts,
                            value=float(value), reliability_tier=tier))
                elif not face_lost_open:
                    events.append(EventRow(
                        event_type="face_lost", native_clock_id=NATIVE_CLOCK_ID,
                        onset_native_ts=frame_ts, offset_native_ts=None,
                        stimulus_id=None, metadata=None))
                    face_lost_open = True
            pending.clear()

        try:
            with vision.FaceLandmarker.create_from_options(options) as landmarker:
                while True:
                    ok, frame_bgr = cap.read()
                    if not ok:
                        break
                    if index % stride:
                        index += 1
                        continue
                    index += 1

                    ts_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                    if ts_ms <= last_ts and (processed or pending):
                        ts_ms = last_ts + (stride * 1000.0 / (media.fps or 30.0))
                    last_ts = ts_ms
                    if window_start is None:
                        window_start = ts_ms

                    lumas.append(mean_luma(frame_bgr))
                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    result = landmarker.detect(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

                    crop = None
                    if result.face_landmarks:
                        h, w = frame_bgr.shape[:2]
                        pts = np.array([[p.x * w, p.y * h]
                                        for p in result.face_landmarks[0]])
                        crop, out = align_face(frame_bgr, pts)
                        outside.append(out)
                    pending.append((ts_ms, crop))

                    if len(pending) >= batch_size:
                        flush()

                    if ts_ms - window_start >= QUALITY_WINDOW_MS:
                        flush()
                        quality.extend(_quality_rows(window_start, ts_ms, processed,
                                                     faces, lumas, outside))
                        window_start, processed, faces = ts_ms, 0, 0
                        lumas, outside = [], []
        finally:
            cap.release()

        flush()
        if window_start is not None and processed:
            quality.extend(_quality_rows(window_start, last_ts, processed, faces,
                                         lumas, outside))

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


def _quality_rows(start, end, processed, faces, lumas, outside) -> list[QualityRow]:
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
    if outside:
        rows.append(row("crop_outside_frame", float(np.median(outside))))
    return rows

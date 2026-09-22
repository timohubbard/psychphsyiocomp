"""Media probing — builds the MediaDescriptor that engines are handed.

This lives in the contract rather than in an engine because a MediaDescriptor
IS a contract type and every engine needs an identical one. Leaving it inside
the first engine that happened to need it meant the second would have to import
from the first, which is backwards, and would put two modules named `engine` on
sys.path at once.

Everything here measures rather than trusts the container. See `_scan` for why
that distinction turned out to be load-bearing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from engine_contract.manifest import MediaDescriptor


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


#: Frames to decode when probing. One sequential pass, because a WebM written by
#: MediaRecorder carries no seek index: `cap.set(POS_FRAMES/POS_MSEC, ...)`
#: returns True and then reads fail or land back at 0ms. Seeking cannot be used
#: to sample this file at all, so the probe reads forward and takes what it needs
#: on the way past. ~30s at 30fps: enough to characterise lighting, far cheaper
#: than decoding a full session.
_PROBE_FRAMES = 900

#: Sample luminance every Nth frame of that pass, for spread rather than a burst.
_LUMA_STRIDE = 30

#: Presentation timestamps needed to measure the frame rate. A couple of seconds.
_FPS_SAMPLE_FRAMES = 120


def _plausible_count(value: float) -> float | None:
    """Reject OpenCV's 'unknown' sentinels for frame count.

    A WebM written by MediaRecorder carries no frame count, and OpenCV signals
    that by returning INT64_MIN (-9.22e18) rather than 0 or NaN. Arithmetic on
    it succeeds and produces a confident, enormous, negative answer — this
    exact file yielded ``duration_s = -9.2e18``. Anything non-finite,
    non-positive or absurdly large is 'unknown', not a measurement.
    """
    if not np.isfinite(value) or value <= 0 or value > 1e9:
        return None
    return float(value)


def _scan(cap: cv2.VideoCapture) -> tuple[float | None, list[float], int]:
    """One forward pass: measure frame rate and sample luminance together.

    Together, because seeking is not available on the files this actually has to
    probe (see ``_PROBE_FRAMES``) — so every quantity the probe needs has to be
    collected on a single read-through or not at all.

    Frame rate is the MEDIAN of the presentation-timestamp deltas. The
    container's own CAP_PROP_FPS is a hint, not a measurement: this project's
    first real capture reported **1000.0 fps** for a 30fps recording, because
    WebM stores a timebase there. Believing it breaks three things at once — the
    duration, the ``min_fps`` eligibility check, and the synthetic-timestamp
    fallback in ``run()``, which would step 1ms per frame instead of 32ms.

    A median, not a mean, in both places: one dropped frame is a single bad
    delta, and a sync clapper is a single blown-out luminance sample. Both are
    outliers to be ignored rather than averaged in — and the clapper case
    matters, because a mean pulled upward by a white flash could let a session
    too dim for fair rPPG pass the ≥30 luminance gate (§2.5).
    """
    deltas: list[float] = []
    lumas: list[float] = []
    prev_ts: float | None = None
    frames = 0

    for i in range(_PROBE_FRAMES):
        ok, frame = cap.read()
        if not ok:
            break
        frames += 1

        if i < _FPS_SAMPLE_FRAMES:
            ts = cap.get(cv2.CAP_PROP_POS_MSEC)
            if np.isfinite(ts):
                if prev_ts is not None and ts > prev_ts:
                    deltas.append(ts - prev_ts)
                prev_ts = ts

        if i % _LUMA_STRIDE == 0:
            lumas.append(mean_luma(frame))

    fps = None
    if len(deltas) >= 2:
        median_delta = float(np.median(deltas))
        if median_delta > 0:
            fps = 1000.0 / median_delta

    return fps, lumas, frames


def describe_video(path: str | Path) -> MediaDescriptor:
    """Build a MediaDescriptor by probing a video file.

    Everything that can be measured is measured. The engine manifest promises
    'measured, never assumed' about the frame rate; this is where that promise
    is either kept or quietly broken.
    """
    p = Path(path)
    cap = cv2.VideoCapture(str(p))
    if not cap.isOpened():
        raise OSError(f"could not open video: {p}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n_frames = _plausible_count(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        fps, lumas, frames_read = _scan(cap)
        if fps is None:
            # Fall back to the container's claim only when PTS gave us nothing,
            # and still refuse an implausible value rather than pass it on.
            claimed = cap.get(cv2.CAP_PROP_FPS)
            fps = claimed if np.isfinite(claimed) and 0 < claimed <= 240 else None

        # Only when the container actually knows its own length. A duration
        # synthesised from an unknown frame count is the -9.2e18 bug.
        duration_s = (n_frames / fps) if (n_frames and fps) else None
    finally:
        cap.release()

    return MediaDescriptor(
        path=str(p),
        kind="video",
        sha256=sha256_of(p),
        duration_s=duration_s,
        fps=fps,
        width=width or None,
        height=height or None,
        mean_roi_luminance=float(np.median(lumas)) if lumas else None,
    )



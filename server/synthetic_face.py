"""Synthetic face generator for tests.

MediaPipe's face landmarker does detect this drawing (verified: 52 blendshapes),
which gives the test suite a face-present fixture containing no real person.

That matters beyond convenience. Participant webcam video is identifiable
biometric data (REPORT.md §6.4 — blurring alone does not de-identify it, since
gait, body and voice cues survive), so committing a real face to the repo for
test purposes would be exactly the kind of casual biometric retention the
compliance section argues against. A drawing has no data subject.

These images are NOT a substitute for accuracy validation. They exercise the
plumbing — decode, detect, timestamp, align, write — not whether the numbers
mean anything. Real accuracy work needs consented recordings and the
within-session designs described in §2.1.
"""

from __future__ import annotations

import cv2
import numpy as np

#: Defaults chosen to clear the engine's own probe() floors (320x240 minimum).
DEFAULT_SIZE = (640, 480)


def draw_face(
    width: int = DEFAULT_SIZE[0],
    height: int = DEFAULT_SIZE[1],
    *,
    mouth_open: float = 0.0,
    gaze_dx: int = 0,
    brightness: int = 0,
) -> np.ndarray:
    """Render a detectable synthetic face as a BGR image.

    :param mouth_open: 0.0 closed .. 1.0 open — drives a blendshape response,
        so a sequence of frames produces varying signal rather than a constant
    :param gaze_dx: horizontal iris offset in pixels
    :param brightness: added to every channel, for luminance-threshold tests
    """
    img = np.full((height, width, 3), 200, dtype=np.uint8)
    cx, cy = width // 2, height // 2

    # Face oval, in BGR skin tone.
    cv2.ellipse(img, (cx, cy), (110, 145), 0, 0, 360, (165, 190, 215), -1)

    for dx in (-42, 42):
        eye_x, eye_y = cx + dx, cy - 38
        cv2.ellipse(img, (eye_x, eye_y), (26, 14), 0, 0, 360, (245, 245, 245), -1)
        cv2.circle(img, (eye_x + gaze_dx, eye_y), 10, (70, 60, 50), -1)
        cv2.circle(img, (eye_x + gaze_dx, eye_y), 4, (20, 20, 20), -1)
        # Brow
        cv2.ellipse(img, (eye_x, cy - 60), (28, 8), 0, 180, 360, (120, 140, 165), 3)

    # Nose
    cv2.line(img, (cx, cy - 25), (cx, cy + 18), (140, 165, 190), 4)
    cv2.ellipse(img, (cx, cy + 22), (10, 7), 0, 0, 180, (130, 155, 180), 3)

    # Mouth — height varies so consecutive frames differ.
    mouth_h = int(6 + 26 * max(0.0, min(1.0, mouth_open)))
    cv2.ellipse(img, (cx, cy + 62), (40, mouth_h), 0, 0, 360, (120, 120, 170), -1)

    img = cv2.GaussianBlur(img, (5, 5), 0)

    if brightness:
        img = np.clip(img.astype(np.int16) + brightness, 0, 255).astype(np.uint8)
    return img


def write_face_clip(
    path,
    *,
    n_frames: int = 90,
    fps: float = 30.0,
    size: tuple[int, int] = DEFAULT_SIZE,
    flash_frame: int | None = None,
) -> None:
    """Write a short clip of the synthetic face.

    :param flash_frame: if set, that frame is rendered as a full-brightness
        flash — a synthetic sync clapper for the alignment path
    """
    width, height = size
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height)
    )
    try:
        for i in range(n_frames):
            if flash_frame is not None and i == flash_frame:
                writer.write(np.full((height, width, 3), 245, dtype=np.uint8))
                continue
            # Animate the mouth so blendshape values are not constant.
            phase = 0.5 * (1 + np.sin(2 * np.pi * i / 30.0))
            writer.write(draw_face(width, height, mouth_open=float(phase)))
    finally:
        writer.release()

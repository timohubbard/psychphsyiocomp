"""Generate the example stimuli in studies/stimuli/ and print their study items.

Self-generated on purpose: an example study that ships someone else's photos
or clips hands every user a licence question. These are plain shapes and
ffmpeg's own test pattern — CC0 by construction — chosen so an AOI has
something unambiguous to be drawn around:

    scene_left.png   a bright disc on the left, a dim bar on the right
    scene_right.png  the mirror image — the same two AOIs, swapped
    pattern.webm     4 s of ffmpeg's testsrc2 pattern, VP9, no audio

Run once; the files are committed and the study names them by sha256. Running
it again may produce different bytes (encoders embed metadata), which the
capture page would then refuse as a changed stimulus — which is correct.

    npm run py -- tools/make_stimuli.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
from engine_contract.media import ffmpeg_exe  # noqa: E402

OUT = ROOT / "studies" / "stimuli"
W, H = 1280, 720


def _scene(mirror: bool) -> np.ndarray:
    img = np.full((H, W, 3), 96, np.uint8)
    disc_x, bar_x = (int(W * 0.72), int(W * 0.18)) if mirror else (int(W * 0.28), int(W * 0.7))
    cv2.circle(img, (disc_x, H // 2), 150, (40, 200, 250), -1, lineType=cv2.LINE_AA)
    cv2.rectangle(img, (bar_x, H // 2 - 60), (bar_x + 140, H // 2 + 60), (70, 70, 70), -1)
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / "scene_left.png"), _scene(False))
    cv2.imwrite(str(OUT / "scene_right.png"), _scene(True))
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4",
                    "-c:v", "libvpx-vp9", "-b:v", "300k", "-an",
                    str(OUT / "pattern.webm")], check=True)

    items = []
    for sid, kind, name, ms in (("scene_left", "image", "scene_left.png", 4000),
                                ("scene_right", "image", "scene_right.png", 4000),
                                ("pattern", "video", "pattern.webm", 4000)):
        data = (OUT / name).read_bytes()
        items.append({"stimulus_id": sid, "kind": kind, "src": f"stimuli/{name}",
                      "sha256": hashlib.sha256(data).hexdigest(), "duration_ms": ms})
        print(f"  {name:18s} {len(data):>8d} bytes", file=sys.stderr)
    print(json.dumps(items, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

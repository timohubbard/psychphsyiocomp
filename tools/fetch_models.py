#!/usr/bin/env python3
"""Fetch model bundles engines need at runtime.

Models are deliberately NOT committed — they are large, versioned upstream, and
their licence terms can differ from the library's. Each entry below records
where it came from and what its licence position is, so the licence inventory
has a paper trail for the weights as well as the code.

Usage:
    python tools/fetch_models.py            # fetch anything missing
    python tools/fetch_models.py --force    # re-fetch everything
    python tools/fetch_models.py --list     # show status only
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "models"


@dataclass(frozen=True)
class Model:
    name: str
    url: str
    dest: Path
    licence_note: str


MODELS = [
    Model(
        name="face_landmarker",
        url=(
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
            "face_landmarker/float16/1/face_landmarker.task"
        ),
        dest=MODELS_DIR / "face_landmarker.task",
        licence_note=(
            "Distributed by Google with MediaPipe (library is Apache-2.0). The "
            ".task bundle's own licence line was NOT verified during research — "
            "re-verify before any commercial ship. Flagged, not assumed."
        ),
    ),
    Model(
        name="pose_landmarker",
        url=(
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
        ),
        dest=MODELS_DIR / "pose_landmarker.task",
        licence_note=(
            "Distributed by Google with MediaPipe (library is Apache-2.0). Same "
            "unverified-bundle caveat as the face model. Used ONLY to locate the "
            "shoulder line for a respiration ROI — no identity, no pose "
            "classification, and nothing about the body is retained beyond two "
            "keypoints per frame."
        ),
    ),
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def fetch(model: Model, force: bool = False) -> bool:
    model.dest.parent.mkdir(parents=True, exist_ok=True)
    if model.dest.exists() and not force:
        print(f"  {model.name:20s} present  ({model.dest.stat().st_size / 1e6:.1f} MB)")
        return False

    print(f"  {model.name:20s} fetching from {model.url}")
    tmp = model.dest.with_suffix(model.dest.suffix + ".part")
    try:
        with urllib.request.urlopen(model.url, timeout=120) as resp, tmp.open("wb") as out:
            while block := resp.read(1 << 16):
                out.write(block)
        tmp.replace(model.dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    print(
        f"  {model.name:20s} done     ({model.dest.stat().st_size / 1e6:.1f} MB) "
        f"sha256={sha256_of(model.dest)[:16]}..."
    )
    return True


WHISPER_DIR = MODELS_DIR / "whisper"

#: Fetched through faster-whisper's own downloader rather than a URL, because
#: a Whisper checkpoint is a directory of files (weights, tokenizer, config)
#: and pinning one URL would pin one of them.
WHISPER_SIZES = ("base",)

WHISPER_LICENCE = (
    "faster-whisper and CTranslate2 are MIT (SYSTRAN). The WEIGHTS are "
    "OpenAI's, released under MIT per the openai/whisper repository — a "
    "separate artifact, and that licence line was read from the repository "
    "rather than independently verified. Converted checkpoints are "
    "redistributed on the Hugging Face Hub by the Systran organisation."
)


def fetch_whisper(force: bool = False) -> None:
    """Pre-download the Whisper checkpoint into models/whisper.

    Optional: nothing else in the pipeline needs it unless a study offers the
    transcript tier. It is fetched explicitly here rather than on first use so
    that the licence note above is printed to somebody, and so a run in a
    sealed environment fails at setup instead of mid-session.
    """
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("  whisper              SKIPPED  faster-whisper is not installed")
        print("      (only needed for studies offering the transcript tier)")
        return

    WHISPER_DIR.mkdir(parents=True, exist_ok=True)
    for size in WHISPER_SIZES:
        marker = WHISPER_DIR / f".{size}.fetched"
        if marker.exists() and not force:
            print(f"  whisper:{size:12s} present  {WHISPER_DIR.relative_to(REPO_ROOT)}")
            continue
        print(f"  whisper:{size:12s} fetching...")
        WhisperModel(size, device="cpu", compute_type="int8",
                     download_root=str(WHISPER_DIR))
        marker.write_text("ok", encoding="utf-8")
        print(f"  whisper:{size:12s} ok       {WHISPER_DIR.relative_to(REPO_ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-fetch even if present")
    ap.add_argument("--list", action="store_true", help="show status without fetching")
    args = ap.parse_args()

    print()
    print("  MODEL BUNDLES")
    print("  " + "-" * 72)

    if args.list:
        for m in MODELS:
            state = "present" if m.dest.exists() else "MISSING"
            print(f"  {m.name:20s} {state:8s} {m.dest.relative_to(REPO_ROOT)}")
            print(f"      licence: {m.licence_note}")
        state = "present" if any(WHISPER_DIR.glob(".*.fetched")) else "MISSING"
        print(f"  {'whisper':20s} {state:8s} models/whisper  (optional)")
        print(f"      licence: {WHISPER_LICENCE}")
        print()
        return 0

    for m in MODELS:
        try:
            fetch(m, force=args.force)
        except Exception as exc:
            print(f"  {m.name:20s} FAILED   {exc}", file=sys.stderr)
            return 1

    fetch_whisper(force=args.force)

    print("  " + "-" * 72)
    print("  Model licence notes:")
    for m in MODELS:
        print(f"    {m.name}: {m.licence_note}")
    print(f"    whisper: {WHISPER_LICENCE}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

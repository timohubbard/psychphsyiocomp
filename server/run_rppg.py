"""Run the rPPG engine over a stored recording and report — writes nothing.

    npm run rppg -- tempdata/<bundle> [--max-frames N]

For looking at what the engine makes of real footage before a session is
(re)processed with it (`npm run process -- <bundle> --rppg` writes the rows).
Reports the share of heart-rate windows that passed, the rate over time and
the SNR, so the gates can be judged on real compression and lighting.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import numpy as np  # noqa: E402

from engine_contract import describe_video  # noqa: E402
from engine_contract.loader import load_engine_module  # noqa: E402
from rppg import analyse  # noqa: E402

MODEL = ROOT / "models" / "face_landmarker.task"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--max-frames", type=int, default=None)
    args = ap.parse_args()
    video = next((args.bundle / n for n in ("capture.webm", "capture.mp4") if (args.bundle / n).exists()), None)
    if video is None:
        print(f"  no capture.webm or capture.mp4 in {args.bundle}")
        return 1
    engine = load_engine_module("cardiac.rppg_pos").RppgPOS(MODEL)
    media = describe_video(video)
    elig = engine.probe(media)
    size_mb = video.stat().st_size / 1e6
    print(f"\n  rPPG (POS) — {video}")
    if not elig.eligible:
        print(f"  INELIGIBLE: {elig.reasons} {elig.detail}")
        return 1
    ts, rgb, luma = engine.trace(media, args.max_frames)
    # A MediaRecorder file has no duration in its header; the decoded frames do.
    seconds = (ts[-1] - ts[0]) / 1000 if len(ts) > 1 else 0.0
    print(f"  {media.width}x{media.height} at {media.fps or 0:.1f} fps, {seconds:.0f} s decoded, "
          f"~{size_mb * 8 / max(seconds, 1):.2f} Mbit/s")
    found = ~np.isnan(luma)
    _, windows = analyse(ts, rgb, luma)
    passed = [w for w in windows if w.passed]
    print(f"  skin found in {found.mean():.0%} of {len(ts)} frames; skin luminance median {np.nanmedian(luma):.0f}")
    print(f"  windows: {len(passed)}/{len(windows)} passed "
          f"({', '.join(f'{r}: {sum(w.reason == r for w in windows)}' for r in ('low_snr', 'too_dark', 'flat_signal') if any(w.reason == r for w in windows)) or 'none refused'})")
    snrs = [w.snr_db for w in windows if w.snr_db is not None]
    if snrs:
        print(f"  SNR dB: median {np.median(snrs):.1f}, range {min(snrs):.1f} .. {max(snrs):.1f}")
    if passed:
        hr = np.array([w.hr_bpm for w in passed])
        print(f"  heart rate (passing windows): median {np.median(hr):.0f} bpm, "
              f"IQR {np.percentile(hr, 25):.0f}-{np.percentile(hr, 75):.0f}, "
              f"window-to-window change median {np.median(np.abs(np.diff(hr))) if len(hr) > 1 else 0:.1f} bpm")
        print("  over time (s: bpm @ dB):  " + "  ".join(
            f"{w.center_ms / 1000:.0f}:{w.hr_bpm:.0f}@{w.snr_db:.1f}" for w in passed[:: max(1, len(passed) // 12)]))
    print("\n  UNVALIDATED — no reference in this recording. Compare against a chest strap before trusting a figure.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

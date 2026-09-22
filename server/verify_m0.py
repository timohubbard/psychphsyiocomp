#!/usr/bin/env python3
"""M0 verification — runs a full session and prints the gate result.

    node tools/py.mjs server/verify_m0.py

The gate, from the build plan:

    Open one Parquet file, see two `source` values for the same channel in the
    same session, and plot them against each other.

This does exactly that and reports pass/fail. It stands in for the notebook in
the plan — same job, but it runs in CI and has an exit code.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(REPO_ROOT / "server"))
sys.path.insert(0, str(REPO_ROOT / "engines" / "face.mediapipe_blendshapes" / "server"))

import cv2  # noqa: E402

from engine import MediaPipeBlendshapesBatch, mean_luma  # noqa: E402
from engine_contract import Chunk, SignalRow  # noqa: E402
from pipeline import MASTER_CLOCK, SessionBundle, process_session  # noqa: E402
from synthetic_face import write_face_clip  # noqa: E402
from tables import read_session  # noqa: E402

MODEL_PATH = REPO_ROOT / "models" / "face_landmarker.task"
CHANNEL = "blendshape.mouthSmileLeft"
BROWSER_SOURCE = "face.mediapipe_blendshapes@0.1.0+browser-live"


def luma_series(video_path: Path) -> list[tuple[float, float]]:
    cap = cv2.VideoCapture(str(video_path))
    series: list[tuple[float, float]] = []
    idx = 0
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            series.append((idx * 1000.0 / fps, mean_luma(frame)))
            idx += 1
    finally:
        cap.release()
    return series


def main() -> int:
    if not MODEL_PATH.exists():
        print(f"  model not found: {MODEL_PATH}")
        print("  run: npm run models")
        return 2

    print()
    print("  M0 VERIFICATION")
    print("  " + "-" * 72)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        clip = tmp_path / "session.mp4"
        flash_frame, fps = 30, 30.0
        write_face_clip(clip, n_frames=90, fps=fps, flash_frame=flash_frame)
        print(f"  synthetic face clip   90 frames @ {fps:g}fps, flash at frame {flash_frame}")

        browser_chunk = Chunk(signals=tuple(
            SignalRow(
                stream="face", channel=CHANNEL, native_clock_id=MASTER_CLOCK,
                native_ts=1000.0 + i * 33.3, value=0.05 * i,
                reliability_tier="moderate",
            )
            for i in range(10)
        ))

        bundle = SessionBundle(
            session_id="m0_verify", participant_id="p_synthetic", study_id="m0",
            video_path=clip,
            events=[
                {"event_type": "sync_clapper", "onset_native_ts": 1000.0},
                {"event_type": "stimulus_onset", "onset_native_ts": 2000.0,
                 "stimulus_id": "img_01"},
            ],
            browser_chunks=[browser_chunk],
            metadata={"browser_source": BROWSER_SOURCE},
        )

        engine = MediaPipeBlendshapesBatch(MODEL_PATH)
        out_root = tmp_path / "out"
        summary = process_session(
            bundle, [(engine, {})], out_root, video_luma=luma_series(clip)
        )

        for run in summary["runs"]:
            aligned = "aligned" if run["aligned"] else "UNALIGNED"
            print(f"  run                   {run['source']}")
            print(f"                        status={run['status']}  {aligned}  rows={run['rows']}")

        signals = read_session(out_root, "m0_verify", "signals").to_pylist()
        print(f"  signal rows           {len(signals)}")

        # --- the gate -----------------------------------------------------
        same_channel = [r for r in signals if r["channel"] == CHANNEL]
        sources = sorted({r["source"] for r in same_channel})

        print()
        print(f"  channel under test    {CHANNEL}")
        for s in sources:
            rows = [r for r in same_channel if r["source"] == s]
            aligned = sum(1 for r in rows if r["master_ts"] is not None)
            unc = next(
                (r["master_ts_uncertainty_ms"] for r in rows
                 if r["master_ts_uncertainty_ms"] is not None), None
            )
            unc_str = f"±{unc:.0f}ms" if unc is not None else "n/a"
            print(f"    {s:52s} {len(rows):5d} rows  {aligned} aligned  {unc_str}")

        print()
        print("  " + "-" * 72)

        checks = [
            ("two sources for one channel", len(sources) >= 2),
            ("browser placement present", any("browser-live" in s for s in sources)),
            ("server placement present", any("server-batch" in s for s in sources)),
            ("all rows on master clock",
             all(r["master_ts"] is not None for r in same_channel)),
            ("uncertainty recorded",
             all(r["master_ts_uncertainty_ms"] is not None for r in same_channel)),
        ]
        for label, ok in checks:
            print(f"  [{'PASS' if ok else 'FAIL'}]  {label}")

        print()
        if all(ok for _, ok in checks):
            print("  M0 GATE: PASS — two placements, one channel, one session,")
            print("           both on the master clock and therefore comparable.")
            print()
            return 0

        print("  M0 GATE: FAIL")
        print()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

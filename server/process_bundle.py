"""Process a real captured session into the canonical tables.

``verify_m0.py`` proves the machinery works against a synthetic clip. This is
the path a session a participant actually produced takes — and it is a separate
entry point on purpose, because the two exercise genuinely different things.
The synthetic clip has a sane frame count, a seekable index, and a clapper flash
placed where the generator put it. A browser's WebM has none of those.

Usage::

    npm run py -- server/process_bundle.py tempdata --out out/

The clapper scan is the expensive part: it decodes the video once to find the
luminance spike the alignment anchors on. There is no shortcut, because a
MediaRecorder WebM cannot be seeked (see ``describe_video``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))
import cv2  # noqa: E402
import numpy as np  # noqa: E402

from engine_contract.loader import load_engine_module  # noqa: E402
from engine_contract.media import mean_luma  # noqa: E402

# Loaded by engine_id rather than by sys.path order. With more than one engine
# installed, `import engine` is ambiguous and resolves to whichever directory
# was inserted last — which is exactly how this script broke when the gaze
# engine was added.
_face = load_engine_module("face.mediapipe_blendshapes")
MediaPipeBlendshapesBatch = _face.MediaPipeBlendshapesBatch

_gaze = load_engine_module("gaze.mediapipe_features")
from pipeline import SessionBundle, process_session  # noqa: E402
from tables import read_session  # noqa: E402

MODEL_PATH = ROOT / "models" / "face_landmarker.task"


def scan_luma(video_path: Path, max_frames: int | None = None) -> list[tuple[float, float]]:
    """Decode the video once, returning (pts_ms, mean_luma) per frame.

    Sequential by necessity: the files this runs on carry no seek index.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise OSError(f"could not open {video_path}")

    out: list[tuple[float, float]] = []
    last_ts = -1.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            ts = cap.get(cv2.CAP_PROP_POS_MSEC)
            if not np.isfinite(ts) or ts <= last_ts:
                # Keep the series strictly increasing so the clapper detector
                # sees a real time axis rather than a flat run.
                ts = last_ts + 1.0
            last_ts = ts
            out.append((ts, mean_luma(frame)))
            if max_frames and len(out) >= max_frames:
                break
    finally:
        cap.release()
    return out


def _gaze_stage(writer, bundle, solution):
    """Feature engine plus estimator, as one pipeline stage."""
    from gaze_pipeline import run_gaze
    engine = _gaze.MediaPipeGazeFeatures(str(MODEL_PATH))
    return run_gaze(writer, bundle, engine, solution,
                    feature_channels=_gaze.FEATURE_CHANNELS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path, help="directory holding session.json")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--max-frames", type=int, default=None,
                    help="cap the decode for a quick smoke run")
    ap.add_argument("--no-gaze", action="store_true",
                    help="skip the gaze engine and estimator")
    args = ap.parse_args()

    bundle = SessionBundle.from_dir(args.bundle)

    print("\n  PROCESSING A REAL CAPTURE")
    print("  " + "-" * 72)
    print(f"  session          {bundle.session_id}  ({bundle.study_id})")
    print(f"  video            {bundle.video_path}")
    print(f"  events           {len(bundle.events)}")
    browser_rows = sum(len(c.signals) for c in bundle.browser_chunks)
    print(f"  browser chunks   {len(bundle.browser_chunks)}  ({browser_rows} signal rows)")

    geom = bundle.metadata.get("geometry") or {}
    if geom.get("ok"):
        print(f"  geometry         {geom['viewing_distance_mm']/10:.1f}cm "
              f"+/-{geom['geometry_error_mm']/10:.1f}cm")
    else:
        print(f"  geometry         REFUSED ({geom.get('reason')})")

    luma = None
    if bundle.video_path:
        print("\n  scanning video for the sync clapper (one sequential decode)...")
        luma = scan_luma(bundle.video_path, args.max_frames)
        vals = [v for _, v in luma]
        print(f"  frames scanned   {len(luma)}")
        print(f"  luma range       {min(vals):.1f} .. {max(vals):.1f}  "
              f"(median {float(np.median(vals)):.1f})")

    engines = [(MediaPipeBlendshapesBatch(str(MODEL_PATH)), {})]
    summary = process_session(bundle, engines, args.out, video_luma=luma,
                              extra_stages=None if args.no_gaze else [_gaze_stage])


    print("\n  " + "-" * 72)
    print(f"  sources written  {sorted(summary['sources'])}")
    for r in summary["runs"]:
        print(f"    {r}")
    dpp = summary.get("degrees_per_px")
    print(f"  degrees per px   {dpp if dpp is None else round(dpp, 4)}")

    sig = read_session(args.out, bundle.session_id, "signals")
    print(f"\n  signal rows      {sig.num_rows}")

    import pyarrow.compute as pc
    srcs = pc.unique(sig.column("source")).to_pylist()
    print(f"  distinct sources {srcs}")

    aligned = pc.sum(pc.invert(pc.is_null(sig.column("master_ts")))).as_py() or 0
    print(f"  aligned rows     {aligned} / {sig.num_rows}")

    g = summary.get("gaze")
    if g:
        print(f"\n  gaze           status={g['status']}")
        if g["status"] == "ok":
            deg = (f"{g['average_offset_deg']:.2f} deg"
                   if g.get("average_offset_deg") else "no geometry, px only")
            print(f"    offset       {g['average_offset_px']:.0f} px  =  {deg}")
            print(f"    in ROI       {g['percent_in_roi']:.0%}"
                  f"   rate {g['samples_per_sec']:.1f} Hz")
            print(f"    fitted on    {g['n_calibration_targets']} targets, "
                  f"scored on {g['n_validation_targets']} held-out")
            print(f"    gate         {'PASS' if g['passed'] else 'FAIL'} {g['reasons']}")
        else:
            print(f"    {g.get('refusal') or g.get('reasons')}")

    print("\n  M0 criterion on REAL data: "
          f"{'PASS' if len(srcs) >= 2 else 'FAIL'} "
          f"({len(srcs)} source(s) for this session)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

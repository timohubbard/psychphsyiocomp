"""Fit and score gaze on a real captured session, end to end.

    npm run py -- server/run_gaze.py tempdata

Runs the feature engine over the stored video, aligns it to the master clock
via the sync clapper, pools features per calibration target, fits the ridge, and
scores it on validation targets it never saw.
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

_gaze = load_engine_module("gaze.mediapipe_features")
FEATURE_CHANNELS = _gaze.FEATURE_CHANNELS
MediaPipeGazeFeatures = _gaze.MediaPipeGazeFeatures
from gaze_ridge import GateCriteria  # noqa: E402
from gaze_stage import feature_matrix, fit_session, target_spans  # noqa: E402
from pipeline import MASTER_CLOCK, SessionBundle, build_registry  # noqa: E402
from process_bundle import scan_luma  # noqa: E402

MODEL_PATH = ROOT / "models" / "face_landmarker.task"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--roi-px", type=float, default=100.0)
    ap.add_argument("--no-pose", action="store_true",
                    help="iris only; useful when the head barely moved")
    args = ap.parse_args()

    bundle = SessionBundle.from_dir(args.bundle)
    geom = bundle.metadata.get("geometry") or {}
    screen = bundle.metadata.get("screen") or {}
    viewport = (float(screen.get("width_px", 1920)), float(screen.get("height_px", 1080)))

    print("\n  GAZE — fit and score on a real session")
    print("  " + "-" * 72)
    print(f"  session        {bundle.session_id}")
    print(f"  viewport       {viewport[0]:.0f} x {viewport[1]:.0f}")

    dpp = None
    if geom.get("ok"):
        mm_per_px = 1.0 / geom["px_per_mm"]
        dpp = np.degrees(np.arctan2(mm_per_px, geom["viewing_distance_mm"]))
        print(f"  geometry       {geom['viewing_distance_mm']/10:.1f}cm "
              f"-> {dpp:.4f} deg/px ({1/dpp:.0f} px/deg)")
    else:
        print(f"  geometry       REFUSED ({geom.get('reason')}) — no angular error available")

    media = describe_video(bundle.video_path)
    engine = MediaPipeGazeFeatures(str(MODEL_PATH))
    elig = engine.probe(media)
    print(f"  probe          eligible={elig.eligible} {elig.detail or ''}")
    if not elig.eligible:
        print(f"  REFUSED: {elig.reasons}")
        return 1

    print("\n  scanning for the sync clapper...")
    luma = scan_luma(bundle.video_path)
    registry = build_registry(bundle, video_luma=luma)
    solution = registry.solve("video_pts")
    print(f"  aligned        {solution.aligned}  "
          f"offset={getattr(solution, 'offset_ms', None)}")
    if not solution.aligned:
        print("  cannot proceed: features would have no master timestamps")
        return 1

    print("\n  extracting eye features (one decode)...")
    rows: list[dict] = []
    for chunk in engine.run(media, {}):
        for s in chunk.signals:
            master_ts, _ = solution.to_master(s.native_ts)
            rows.append({"channel": s.channel, "master_ts": master_ts, "value": s.value})
        for q in chunk.quality:
            if q.metric in ("iris_valid_rate", "face_detect_rate"):
                pass
        quality = {q.metric: q.value for q in chunk.quality}
    print(f"  feature rows   {len(rows)}")

    ts, X = feature_matrix(rows, FEATURE_CHANNELS)
    print(f"  usable frames  {len(ts)}  x {X.shape[1]} channels")

    spans = target_spans(bundle.events_aligned(solution) if hasattr(bundle, "events_aligned")
                         else _aligned_events(bundle))
    n_cal = sum(1 for s in spans if s.kind == "calibration_point")
    n_val = sum(1 for s in spans if s.kind == "validation_point")
    print(f"  targets        {n_cal} calibration, {n_val} validation")

    fit = fit_session(ts, X, spans, viewport_px=viewport, degrees_per_px=dpp,
                      channels=FEATURE_CHANNELS, use_pose=not args.no_pose,
                      criteria=GateCriteria(), roi_radius_px=args.roi_px)

    print("\n  " + "-" * 72)
    if fit.refusal:
        print(f"  REFUSED: {fit.refusal} — {fit.reasons}")
        return 1

    r = fit.validation
    print(f"  fitted on      {fit.n_calibration_targets} targets, alpha={fit.alpha:.3f}")
    print(f"  scored on      {fit.n_validation_targets} HELD-OUT targets")
    print(f"\n  average_offset {r.average_offset_px:.0f} px"
          + (f"   =  {r.average_offset_deg:.2f} deg" if r.average_offset_deg else ""))
    print(f"  percent_in_roi {r.percent_in_roi:.0%}  (within {args.roi_px:.0f}px)")
    print(f"  samples_per_s  {r.samples_per_sec:.1f} Hz")
    print(f"\n  gate           {'PASS' if fit.passed else 'FAIL'}  {fit.reasons}")
    print("\n  For scale: §4.2 says webcam AOIs need padding to a 3-4.5 deg budget.")
    print()
    return 0


def _aligned_events(bundle) -> list[dict]:
    """Browser events are already on the master clock — they define it."""
    out = []
    for e in bundle.events:
        out.append({
            "event_type": e["event_type"],
            "onset_master_ts": e.get("onset_native_ts"),
            "offset_master_ts": e.get("offset_native_ts"),
            "stimulus_id": e.get("stimulus_id"),
            "metadata": e.get("metadata"),
        })
    return out


if __name__ == "__main__":
    raise SystemExit(main())

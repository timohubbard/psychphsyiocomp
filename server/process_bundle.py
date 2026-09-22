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
POSE_MODEL_PATH = ROOT / "models" / "pose_landmarker.task"


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


def _voice_stage(writer, bundle, solution):
    """Extract audio and run the eGeMAPS engine.

    A stage rather than an engine entry because the audio has to be produced
    first, and `process_session` hands engines the video descriptor.
    """
    import uuid
    from datetime import datetime, timezone

    from engine_contract import describe_audio

    wav = bundle.ensure_audio()
    if wav is None:
        return {"status": "no_audio"}

    engine = load_engine_module("voice.opensmile_egemaps").OpenSmileEGeMAPS()
    media = describe_audio(wav, bundle.metadata.get("applied_audio_constraints"))

    started = datetime.now(timezone.utc)
    eligibility = engine.probe(media)
    run_id = str(uuid.uuid4())

    if not eligibility.eligible:
        writer.add_run(run_id=run_id, manifest=engine.manifest, source=engine.source,
                       params={}, media_sha256=media.sha256, started=started,
                       ended=datetime.now(timezone.utc), status="ineligible",
                       eligibility=eligibility, solution=solution)
        return {"status": "ineligible", "reasons": list(eligibility.reasons)}

    chunks = list(engine.run(media, {}))
    rows = writer.add_chunks(chunks, source=engine.source, params={}, solution=solution)
    writer.add_run(run_id=run_id, manifest=engine.manifest, source=engine.source,
                   params={}, media_sha256=media.sha256, started=started,
                   ended=datetime.now(timezone.utc), status="ok",
                   eligibility=eligibility, solution=solution)

    quality = {q.metric: q.value for c in chunks for q in c.quality}
    return {"status": "ok", "rows": rows, **quality}


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
    ap.add_argument("--aus", action="store_true",
                    help="also run the Py-Feat Action Unit engine (slow: ~0.25s/frame)")
    ap.add_argument("--au-stride", type=int, default=15,
                    help="analyse every Nth frame for AUs; AU dynamics are slow")
    ap.add_argument("--no-voice", action="store_true",
                    help="skip audio extraction and the eGeMAPS engine")
    ap.add_argument("--resp", action="store_true",
                    help="also run the respiration engine (waveform only — it "
                         "does not emit a breathing rate, see its manifest)")
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

    # Opt-in for a different reason than the AU engine below: not cost, but
    # standing. Respiration is plausibly health data under GDPR Art. 4(15)
    # (§6.3), so a study gets it because it asked for it, never by default.
    if args.resp:
        _resp = load_engine_module("resp.motion_profiles")
        engines.append((_resp.RespirationMotionProfiles(str(POSE_MODEL_PATH)),
                        {"analysis_fps": 10}))

    # Opt-in, because it is the slowest thing in the pipeline by a wide margin:
    # ~0.25s per analysed frame on CPU against a few milliseconds for the others.
    # Off by default so the common path stays fast, rather than silently skipped
    # when it fails — an engine that is present must run.
    if args.aus:
        _pyfeat = load_engine_module("face.pyfeat_aus")
        engines.append((_pyfeat.PyFeatAUs(),
                        {"frame_stride": args.au_stride, "batch_size": 8}))
    stages = []
    if not args.no_gaze:
        stages.append(("gaze", _gaze_stage))
    if not args.no_voice:
        stages.append(("voice", _voice_stage))

    summary = process_session(bundle, engines, args.out, video_luma=luma,
                              extra_stages=stages)


    st = summary.get("study") or {}
    if st.get("ok"):
        d = st["detail"]
        print(f"\n  protocol         {d['study_id']} v{d['version']} "
              f"({d['content_hash']})")
    else:
        # Named rather than silent. `no_study_recorded` is the expected state
        # for the pilots captured before study definitions existed;
        # `study_edited_since_session` is not, and means this session is not
        # comparable with ones run after the edit.
        reason = (st.get("reasons") or ["unknown"])[0]
        print(f"\n  protocol         UNVERIFIED ({reason})")

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

    v = summary.get("voice")
    if v:
        print(f"\n  voice          status={v['status']}")
        if v["status"] == "ok":
            preserved = v.get("speech_content_preserved")
            print(f"    rows         {v.get('rows', 0)}")
            print(f"    voiced       {v.get('voiced_fraction', 0):.1%} of windows")
            print(f"    speech kept  {'yes' if preserved else 'NO — valence unavailable'}")
        else:
            print(f"    {v.get('reasons') or v['status']}")

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

    if args.resp:
        q = read_session(args.out, bundle.session_id, "quality")
        resp_q = {r["metric"]: r["value"] for r in q.to_pylist()
                  if r["source"].startswith("resp.")}
        if resp_q:
            print("\n  respiration    waveform only — NO breathing rate is emitted")
            print(f"    ROI found    {resp_q.get('roi_found_rate', 0):.0%} of analysed frames")
            print(f"    usable       {resp_q.get('usable_fraction', 0):.0%} of segments")
            print(f"    analysis     {resp_q.get('analysis_fps', 0):.1f} Hz"
                  f"   luma {resp_q.get('mean_luminance', 0):.0f}")
            print("    rate         withheld: no validation study exists "
                  "(see engine.manifest.json)")

    print("\n  M0 criterion on REAL data: "
          f"{'PASS' if len(srcs) >= 2 else 'FAIL'} "
          f"({len(srcs)} source(s) for this session)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

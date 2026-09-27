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
from pipeline import (SessionBundle, no_video_eligibility, process_session,  # noqa: E402
                      refuse_unconsented_recording)
from ingest import upload_refusal  # noqa: E402
from pseudonym import apply_to_bundle  # noqa: E402
from retention import refusal_for  # noqa: E402
from tables import read_session  # noqa: E402

MODEL_PATH = ROOT / "models" / "face_landmarker.task"
POSE_MODEL_PATH = ROOT / "models" / "pose_landmarker.task"
WHISPER_DIR = ROOT / "models" / "whisper"
OPENGRAPHAU_WEIGHTS = ROOT / "models" / "opengraphau" / "OpenGprahAU-ResNet50_second_stage.pth"


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

    engine = load_engine_module("voice.opensmile_egemaps").OpenSmileEGeMAPS()
    wav = bundle.ensure_audio()
    if wav is None:
        # A runs row, not a silent return: "voice never ran because there was
        # no recording" has to be distinguishable from "nobody ran voice".
        from engine_contract import Eligibility
        now = datetime.now(timezone.utc)
        eligibility = (no_video_eligibility(bundle) if bundle.video_path is None
                       else Eligibility(eligible=False, reasons=("no_audio",),
                                        detail="the recording has no audio track"))
        writer.add_run(run_id=str(uuid.uuid4()), manifest=engine.manifest,
                       source=engine.source, params={}, media_sha256=None,
                       started=now, ended=now, status="ineligible",
                       eligibility=eligibility, solution=solution)
        return {"status": "no_audio", "reasons": list(eligibility.reasons),
                "detail": eligibility.detail}

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


def _transcript_stage_factory(model_dir, params):
    """The transcript stage, which may well produce nothing.

    Wrapped in a factory so the consent gate stays in transcript_stage.py and
    this file never learns what a permitting tier is.
    """
    def stage(writer, bundle, solution):
        from transcript_stage import run_transcript
        study = None
        try:
            from study import load_study
            recorded = bundle.metadata.get("study") or {}
            if recorded.get("study_id"):
                study = load_study(ROOT / "studies", recorded["study_id"])
        except (FileNotFoundError, ValueError):
            # Not fatal, and not a reason to widen the gate: without the study
            # the check falls back to the session's own consent record, which
            # is the participant's actual decision either way.
            study = None
        return run_transcript(writer, bundle, solution, study=study,
                              model_dir=model_dir, params=params)
    return stage


def _gaze_stage(writer, bundle, solution):
    """Feature engine plus estimator, as one pipeline stage.

    With no recording (features_in_browser) the estimator is fitted on the
    features the browser computed — the only gaze measurement such a session
    will ever have — and the server engine's absence is a runs row.
    """
    from gaze_pipeline import run_gaze, run_gaze_from_browser
    engine = _gaze.MediaPipeGazeFeatures(str(MODEL_PATH))
    if bundle.video_path is None:
        return run_gaze_from_browser(writer, bundle, engine, solution,
                                     feature_channels=_gaze.FEATURE_CHANNELS,
                                     no_video=no_video_eligibility(bundle))
    return run_gaze(writer, bundle, engine, solution,
                    feature_channels=_gaze.FEATURE_CHANNELS)


def _print_expression_scores(out: Path, session_id: str) -> None:
    """Score each AU engine against the movements the session asked for.

    Only sessions recorded with the expression_prompts task have anything to
    score; for the rest this says so in one line rather than printing a table of
    refusals.
    """
    import pyarrow.compute as pc
    from expression_scoring import score_session, summarise
    from tables import read_session

    events = read_session(out, session_id, "events").to_pylist()
    if not any(e["event_type"] == "expression_hold" for e in events):
        print("    posed-movement scoring: not applicable (no expression_prompts task)")
        return
    sig = read_session(out, session_id, "signals")
    sig = sig.filter(pc.starts_with(sig.column("channel"), "au."))
    rep = score_session(sig.select(["source", "channel", "master_ts", "value"]).to_pylist(),
                        events)
    print(f"\n  posed movements   {rep.n_trials} trials   (AUC: 1.0 = always higher "
          "when asked, 0.5 = chance)")
    if rep.refusal:
        print(f"    {rep.refusal}")
        return
    for src, s in summarise(rep).items():
        sens, spec = s["median_sensitivity_auc"], s["median_specificity_auc"]
        print(f"    {src}")
        print(f"      median sensitivity {sens if sens is None else round(sens, 2)}   "
              f"specificity {spec if spec is None else round(spec, 2)}   "
              f"over {s['n_aus_scored']} AUs")
    for sc in rep.scores:
        if sc.verdict == "ok":
            spec = "—" if sc.specificity_auc is None else f"{sc.specificity_auc:.2f}"
            print(f"      {sc.au} {sc.source.split('@')[0]:24s} sens {sc.sensitivity_auc:.2f}  "
                  f"spec {spec}  (n={sc.n_target} vs {sc.n_neutral} neutral)")
    ok = [a for a in rep.agreement if a.verdict == "ok"]
    if ok:
        rs = sorted(a.r for a in ok)
        print(f"    engines agree on held movements: median r {float(np.median(rs)):.2f} "
              f"over {len(ok)} AUs (range {rs[0]:.2f} .. {rs[-1]:.2f})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("bundle", type=Path, help="directory holding session.json")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--max-frames", type=int, default=None,
                    help="cap the decode for a quick smoke run")
    ap.add_argument("--no-gaze", action="store_true",
                    help="skip the gaze engine and estimator")
    ap.add_argument("--aus", action="store_true",
                    help="also run the Action Unit engines (slow: ~0.4s per analysed "
                         "frame for both together)")
    ap.add_argument("--au-engines", default="pyfeat,opengraphau",
                    help="comma-separated AU engines for --aus. Both by default: "
                         "§2.2's between-engine spread is the only uncertainty "
                         "estimate facial measurement has, and one engine "
                         "cannot produce it")
    ap.add_argument("--au-stride", type=int, default=15,
                    help="analyse every Nth frame for AUs; AU dynamics are slow")
    ap.add_argument("--no-voice", action="store_true",
                    help="skip audio extraction and the eGeMAPS engine")
    ap.add_argument("--transcript", action="store_true",
                    help="also transcribe speech — ONLY runs for sessions whose "
                         "consent tier is media_plus_transcript, and records a "
                         "reason when it refuses")
    ap.add_argument("--whisper-model", default="small",
                    help="Whisper checkpoint; recorded in the run row because "
                         "different checkpoints give different transcripts")
    ap.add_argument("--resp", action="store_true",
                    help="also run the respiration engine (waveform only — it "
                         "does not emit a breathing rate, see its manifest)")
    ap.add_argument("--rppg", action="store_true",
                    help="also run the rPPG heart-rate engine. Runs anyway when the "
                         "session's study declares the `cardiac` modality")
    ap.add_argument("--no-blinks", action="store_true",
                    help="skip blink detection (derived from the face engine's output)")
    args = ap.parse_args()

    bundle = SessionBundle.from_dir(args.bundle)

    # Before anything is written: a withdrawn or expired session must not come
    # back because a copy of its bundle was still lying around. See retention.py.
    refusal = (refusal_for(args.out, bundle.session_id, bundle.metadata)
               or upload_refusal(args.bundle))
    if refusal:
        print(f"\n  REFUSED  {refusal}")
        return 2

    # Before anything is written: a raw panel ID becomes a pseudonym, so no
    # table, log line or export below ever sees it (server/pseudonym.py).
    pseud = apply_to_bundle(args.out, bundle, args.bundle)
    if pseud:
        print(f"\n  participant      pseudonymised as {pseud}")

    # Before the clapper scan below decodes a single frame: a recording that a
    # features_in_browser participant never agreed to send is deleted unread.
    recording_refused = refuse_unconsented_recording(bundle)
    if recording_refused:
        print(f"\n  RECORDING DELETED UNREAD  {recording_refused['flag']}")

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

    # A pulse is health data (GDPR Art. 9), so it is measured when the study
    # asked for it — its `cardiac` modality, disclosed on the consent screen —
    # or when the researcher asks explicitly, never by default.
    study_mods = (bundle.metadata.get("study") or {}).get("modalities") or []
    if args.rppg or "cardiac" in study_mods:
        _rppg = load_engine_module("cardiac.rppg_pos")
        engines.append((_rppg.RppgPOS(str(MODEL_PATH)), {}))

    # Opt-in, because it is the slowest thing in the pipeline by a wide margin:
    # ~0.25s per analysed frame on CPU against a few milliseconds for the others.
    # Off by default so the common path stays fast, rather than silently skipped
    # when it fails — an engine that is present must run.
    if args.aus:
        chosen = {e.strip() for e in args.au_engines.split(",") if e.strip()}
        unknown = chosen - {"pyfeat", "opengraphau"}
        if unknown:
            ap.error(f"unknown AU engine(s): {sorted(unknown)}")
        if len(chosen) == 1:
            print(f"\n  NOTE: one AU engine ({next(iter(chosen))}) — the §2.2 "
                  "between-engine uncertainty will be reported as unavailable")
        if "pyfeat" in chosen:
            _pyfeat = load_engine_module("face.pyfeat_aus")
            engines.append((_pyfeat.PyFeatAUs(),
                            {"frame_stride": args.au_stride, "batch_size": 8}))
        if "opengraphau" in chosen:
            _ogau = load_engine_module("face.opengraphau_aus")
            engines.append((_ogau.OpenGraphAUs(OPENGRAPHAU_WEIGHTS, str(MODEL_PATH)),
                            {"frame_stride": args.au_stride, "batch_size": 16}))
    stages = []
    if not args.no_gaze:
        stages.append(("gaze", _gaze_stage))
    if not args.no_voice:
        stages.append(("voice", _voice_stage))
    if not args.no_blinks:
        from blinks import run_blinks
        stages.append(("blinks", lambda writer, bundle, solution: run_blinks(writer)))
    if args.transcript:
        stages.append(("transcript", _transcript_stage_factory(
            WHISPER_DIR, {"model_size": args.whisper_model})))

    # A rerun replaces the session's tables wholesale (tables.CanonicalWriter),
    # so a stage left off this time loses its earlier output. Said up front,
    # because a rerun "just to refresh the transcript" would otherwise quietly
    # drop fifteen minutes of AU inference.
    existing = sorted(p.name.split("=", 1)[1] for p in
                      (args.out / f"session_id={bundle.session_id}").glob("stream=*")
                      if any(p.glob("*.parquet")))
    if existing:
        print(f"\n  replacing existing output for this session (streams: "
              f"{', '.join(existing)}) — stages not run now will be absent")

    summary = process_session(bundle, engines, args.out, video_luma=luma,
                              extra_stages=stages)
    if recording_refused:
        summary["recording_refused"] = recording_refused


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

    t = summary.get("transcript")
    if t:
        print(f"\n  transcript     status={t['status']}")
        if t["status"] == "ok":
            print(f"    segments     {t.get('segments_retained', 0):.0f} kept, "
                  f"{t.get('segments_rejected', 0):.0f} rejected as probable "
                  f"hallucination")
            print(f"    coverage     {t.get('speech_coverage', 0):.1%} of the "
                  f"recording   language p={t.get('language_probability', 0):.2f}")
        else:
            # A refusal is the expected outcome for most sessions and reads as
            # one, rather than as a failure.
            print(f"    {t.get('reason') or t.get('reasons')}")

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

    b = summary.get("blinks")
    if b:
        print(f"\n  blinks         status={b['status']}")
        if b["status"] == "ok":
            print(f"    rate         {b.get('blink_rate_per_min', 0):.1f} per minute of face-present time "
                  f"({int(b.get('blink_count', 0))} blinks, median {b.get('blink_duration_median_ms', 0):.0f} ms)")
            print(f"    closures     {int(b.get('eye_closure_count', 0))} longer than a blink; "
                  f"eyes closed {b.get('eyes_closed_fraction', 0):.1%} of the time")
            print(f"    from         {b['from_source']}")
        else:
            print(f"    {b.get('refusal')}")

    rppg_q = {r["metric"]: r["value"] for r in read_session(args.out, bundle.session_id, "quality").to_pylist()
              if r["source"].startswith("cardiac.")}
    if rppg_q:
        print("\n  heart rate     rPPG (POS) — UNVALIDATED until compared with a reference")
        print(f"    windows      {rppg_q.get('hr_window_pass_rate', 0):.0%} passed the SNR and "
              f"luminance gates")
        if "hr_median_bpm" in rppg_q:
            print(f"    median       {rppg_q['hr_median_bpm']:.0f} bpm over passing windows")
        print(f"    skin luma    {rppg_q.get('mean_luminance', 0):.0f}   face found "
              f"{rppg_q.get('face_found_rate', 0):.0%}")

    if args.aus:
        from store import agreement_report
        rep = agreement_report(args.out, bundle.session_id, max_channels=200)
        au = [c for c in rep["channels"] if c["channel"].startswith("au.")]
        between = [c for c in au if c["kind"] == "engines" and c["verdict"] == "ok"]
        print("\n  action units   between-engine agreement (§2.2 published "
              "r = 0.37-0.75)")
        if between:
            rs = sorted(c["r"] for c in between)
            print(f"    measured     {len(between)} shared AUs   median r "
                  f"{float(np.median(rs)):.2f}   range {rs[0]:.2f} .. {rs[-1]:.2f}")
            for c in sorted(between, key=lambda c: c["r"]):
                print(f"      {c['channel']:14s} r={c['r']:+.2f}  n={c['n']}  "
                      f"sd {c['sd_a']:.3f}/{c['sd_b']:.3f}")
        by_verdict: dict[str, int] = {}
        for c in au:
            if c["verdict"] != "ok":
                by_verdict[c["verdict"]] = by_verdict.get(c["verdict"], 0) + 1
        if by_verdict:
            print(f"    not measured {by_verdict}")
        _print_expression_scores(args.out, bundle.session_id)

    if bundle.video_path is None:
        # The M0 gate compares two placements of one engine over the same
        # recording. With no recording there is only one placement, by design.
        print("\n  M0 criterion: not applicable — no recording (the browser "
              "placement is the only one)")
    else:
        print("\n  M0 criterion on REAL data: "
              f"{'PASS' if len(srcs) >= 2 else 'FAIL'} "
              f"({len(srcs)} source(s) for this session)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

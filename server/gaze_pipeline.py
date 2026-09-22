"""Run the gaze feature engine and the estimator, and persist both.

Kept apart from `pipeline.process_session` because the two halves are different
kinds of thing. The feature engine is an ordinary engine and goes through the
normal `add_chunks` path. The estimator is not: it needs the master clock, it
produces a source that depends on a per-participant fit, and its parameters are
that participant's calibration.

That last point matters for re-run semantics. The fitted model IS a parameter,
so two fits of the same session appear as two distinguishable sources rather
than silently overwriting each other — the same rule every engine follows.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import numpy as np

from engine_contract import Chunk, QualityRow, SignalRow
from gaze_ridge import GateCriteria
from gaze_stage import feature_matrix, fit_session, target_spans

#: Source for the estimator's own output. Distinct from the feature engine's:
#: the features are a measurement, the gaze coordinates are an inference from
#: them, and conflating the two would make a better estimator look like a
#: changed measurement.
ESTIMATOR_SOURCE = "gaze.ridge@0.1.0+server-fit"


def run_gaze(
    writer,
    bundle,
    engine,
    solution,
    *,
    feature_channels,
    criteria: GateCriteria | None = None,
    roi_radius_px: float = 100.0,
    use_pose: bool = True,
) -> dict[str, Any]:
    """Extract features, fit, score, and write everything to the tables.

    Returns a summary dict. A refusal is a normal outcome and is recorded as a
    quality row rather than raised — a session whose calibration failed is still
    a session, and the reason has to survive to analysis.
    """
    from engine_contract import describe_video

    media = describe_video(bundle.video_path)
    eligibility = engine.probe(media)

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)

    if not eligibility.eligible:
        writer.add_run(
            run_id=run_id, manifest=engine.manifest, source=engine.source,
            params={}, media_sha256=media.sha256, started=started,
            ended=datetime.now(timezone.utc), status="ineligible",
            eligibility=eligibility, solution=solution,
        )
        return {"status": "ineligible", "reasons": list(eligibility.reasons)}

    chunks = list(engine.run(media, {}))
    writer.add_chunks(chunks, source=engine.source, params={}, solution=solution)
    writer.add_run(
        run_id=run_id, manifest=engine.manifest, source=engine.source,
        params={}, media_sha256=media.sha256, started=started,
        ended=datetime.now(timezone.utc), status="ok",
        eligibility=eligibility, solution=solution,
    )

    # -- the estimator ----------------------------------------------------

    rows = [
        {"channel": s.channel,
         "master_ts": solution.to_master(s.native_ts)[0],
         "value": s.value}
        for c in chunks for s in c.signals
    ]
    ts, X = feature_matrix(rows, feature_channels)

    events = [{
        "event_type": e["event_type"],
        "onset_master_ts": e.get("onset_native_ts"),
        "offset_master_ts": e.get("offset_native_ts"),
        "stimulus_id": e.get("stimulus_id"),
        "metadata": e.get("metadata"),
    } for e in bundle.events]
    spans = target_spans(events)

    screen = bundle.metadata.get("screen") or {}
    viewport = (float(screen.get("width_px") or 1920), float(screen.get("height_px") or 1080))
    dpp = writer.degrees_per_px()

    fit = fit_session(ts, X, spans, viewport_px=viewport, degrees_per_px=dpp,
                      channels=list(feature_channels), use_pose=use_pose,
                      criteria=criteria or GateCriteria(), roi_radius_px=roi_radius_px)

    if fit.refusal:
        _write_quality(writer, solution, ts, {
            "gaze_fit_refused": 1.0,
            "gaze_calibration_targets": float(fit.n_calibration_targets),
        })
        return {"status": "refused", "refusal": fit.refusal, "reasons": fit.reasons}

    # Predicted gaze for every usable frame, as ordinary signals so they join
    # against everything else on the master clock.
    from gaze_stage import design_from_channels
    pred = fit.model.predict(design_from_channels(X, list(feature_channels), use_pose=use_pose))

    gaze_signals = []
    for t, (gx, gy) in zip(ts, pred):
        gaze_signals.append(SignalRow(
            stream="gaze", channel="gaze.x", native_clock_id=solution.clock_id,
            native_ts=t, value=float(gx), reliability_tier="moderate"))
        gaze_signals.append(SignalRow(
            stream="gaze", channel="gaze.y", native_clock_id=solution.clock_id,
            native_ts=t, value=float(gy), reliability_tier="low"))

    # Already on the master clock: the features were converted before fitting,
    # so the identity solution is the honest description of this step.
    from alignment import ClockSolution
    identity = ClockSolution(
        clock_id=solution.clock_id, offset_ms=0.0, rate=1.0,
        # Uncertainty is inherited, not reset. These coordinates were derived
        # from features that carried the clapper anchor's error, and claiming a
        # clean clock here would quietly discard it.
        uncertainty_ms=solution.uncertainty_ms, n_anchors=solution.n_anchors,
        unaligned_reason=None,
    )

    v = fit.validation
    writer.add_chunks(
        [Chunk(signals=tuple(gaze_signals), quality=tuple(_validation_quality(v, ts)))],
        source=ESTIMATOR_SOURCE,
        # The fit IS the parameterisation. Recording it means a re-fit appends a
        # distinguishable source instead of silently replacing this one.
        params={"alpha": fit.alpha, "use_pose": use_pose,
                "n_calibration_targets": fit.n_calibration_targets,
                "channels": list(feature_channels)},
        solution=identity,
    )

    return {
        "status": "ok",
        "alpha": fit.alpha,
        "n_calibration_targets": fit.n_calibration_targets,
        "n_validation_targets": fit.n_validation_targets,
        "average_offset_px": v.average_offset_px,
        "average_offset_deg": v.average_offset_deg,
        "percent_in_roi": v.percent_in_roi,
        "samples_per_sec": v.samples_per_sec,
        "passed": fit.passed,
        "reasons": fit.reasons,
    }


def _validation_quality(v, ts: np.ndarray) -> list[QualityRow]:
    """Validation metrics as quality rows spanning the whole session.

    Session-scoped rather than windowed: the figure describes one fit over one
    calibration block, and slicing it into windows would imply it was measured
    repeatedly.
    """
    start = float(ts[0]) if len(ts) else 0.0
    end = float(ts[-1]) if len(ts) else 0.0

    metrics = {
        "gaze_average_offset_px": v.average_offset_px,
        "gaze_percent_in_roi": v.percent_in_roi,
        "gaze_samples_per_sec": v.samples_per_sec,
        "gaze_validation_targets": float(v.n_targets),
    }
    if v.average_offset_deg is not None:
        metrics["gaze_average_offset_deg"] = v.average_offset_deg

    return [
        QualityRow(stream="gaze", metric=m, window_start_native_ts=start,
                   window_end_native_ts=end, value=float(val))
        for m, val in metrics.items()
    ]


def _write_quality(writer, solution, ts, metrics: dict[str, float]) -> None:
    start = float(ts[0]) if len(ts) else 0.0
    end = float(ts[-1]) if len(ts) else 0.0
    writer.add_chunks(
        [Chunk(quality=tuple(
            QualityRow(stream="gaze", metric=m, window_start_native_ts=start,
                       window_end_native_ts=end, value=v)
            for m, v in metrics.items()))],
        source=ESTIMATOR_SOURCE, params={}, solution=solution,
    )

"""Gaze estimator stage — features plus calibration events in, gaze out.

This is the join that cannot live inside an engine. It needs to know which
calibration target was on screen across which span of the MASTER clock, and
engines are forbidden to reason about that clock at all (REPORT.md §3.3).

Everything here is pure functions over arrays and dicts, so the part that can be
silently wrong — pooling the wrong frames into the wrong target — is testable
without a webcam, a model file, or a video.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

from gaze_ridge import GateCriteria, RidgeGaze, ValidationResult, gate, validate


#: Channels that describe where the eye is pointing. These, and their quadratic
#: expansion, are the gaze signal.
IRIS_CHANNELS = (
    "eye.left_iris_dx", "eye.left_iris_dy",
    "eye.right_iris_dx", "eye.right_iris_dy",
)

#: Head orientation. Gaze in SCREEN coordinates is eye-in-head plus head-in-
#: world, so an estimator given only the iris cannot tell a head turn from an
#: eye movement. Kept even though a still-headed session does not need it.
POSE_CHANNELS = ("head_pose.yaw", "head_pose.pitch", "head_pose.roll")

#: Deliberately NOT predictors. Eyelid aperture and inter-ocular distance are
#: quality gates — they say whether the iris estimate is meaningful and whether
#: the participant has moved — and they drift over a session. Handing a drifting
#: quantity to the regression invites it to predict target position from elapsed
#: time, which is precisely the leak measured on the first real session.
QUALITY_CHANNELS = ("eye.left_openness", "eye.right_openness", "eye.inter_ocular_px")


def expand_features(X: np.ndarray, iris_idx: Sequence[int],
                    pose_idx: Sequence[int]) -> np.ndarray:
    """Quadratic expansion of the iris columns, plus linear head pose.

    The eye rotates and the screen is a plane, so the mapping from iris offset
    to screen position is genuinely not linear — the expansion is a statement
    about the geometry, not a search for whatever happens to fit.

    Measured on the first real session, against five held-out targets:

        iris, linear            2.17 deg
        iris, quadratic         1.30 deg
        iris quad + pose        1.65 deg
        every channel, linear   5.04 deg   <- chosen by LOOCV

    That last row is the cautionary one. Including the drifting quality channels
    produced the best leave-one-out score and the worst real error, because a
    fixed stimulus order let them stand in for elapsed time. Randomising the
    presentation order removes the confound at source; excluding them here
    removes the temptation.
    """
    A = X[:, list(iris_idx)]
    cols = [A]
    n = A.shape[1]
    for i in range(n):
        for j in range(i, n):
            cols.append((A[:, i] * A[:, j])[:, None])
    if len(pose_idx):
        cols.append(X[:, list(pose_idx)])
    return np.hstack(cols)


def design_from_channels(X: np.ndarray, channels: Sequence[str], *,
                         use_pose: bool = True) -> np.ndarray:
    """Build the estimator's design matrix from a full feature matrix."""
    idx = {c: i for i, c in enumerate(channels)}
    iris = [idx[c] for c in IRIS_CHANNELS if c in idx]
    pose = [idx[c] for c in POSE_CHANNELS if c in idx] if use_pose else []
    if not iris:
        raise ValueError("no iris channels present; cannot estimate gaze")
    return expand_features(X, iris, pose)


@dataclass(frozen=True)
class TargetSpan:
    """A stimulus target and the master-clock window it was being looked at."""

    stimulus_id: str
    kind: str                # 'calibration_point' | 'validation_point'
    x: float                 # normalised 0..1
    y: float
    start_ts: float          # master clock, ms
    end_ts: float


def target_spans(events: Iterable[dict[str, Any]]) -> list[TargetSpan]:
    """Extract the windows during which each target was actively sampled.

    Reads the ``*_sampling`` events, not the outer target events. The outer one
    opens when the dot APPEARS; the sampling one opens after the saccade
    allowance has elapsed. Pooling from the outer window would include frames
    where the participant was still looking at the previous target, which
    trains the estimator on the wrong association — the exact mistake the
    saccade allowance exists to prevent.
    """
    spans: list[TargetSpan] = []
    for e in events:
        etype = e.get("event_type", "")
        if not etype.endswith("_point_sampling"):
            continue
        onset, offset = e.get("onset_master_ts"), e.get("offset_master_ts")
        if onset is None or offset is None:
            # An unaligned or unclosed event cannot be pooled from. Skipping it
            # loses one target; guessing its span corrupts the fit.
            continue
        meta = e.get("metadata") or {}
        if isinstance(meta, str):
            import json
            meta = json.loads(meta)
        if "x" not in meta or "y" not in meta:
            continue
        spans.append(TargetSpan(
            stimulus_id=e.get("stimulus_id") or etype,
            kind=etype.replace("_sampling", ""),
            x=float(meta["x"]), y=float(meta["y"]),
            start_ts=float(onset), end_ts=float(offset),
        ))
    return spans


def feature_matrix(
    signal_rows: Iterable[dict[str, Any]],
    channels: Sequence[str],
) -> tuple[np.ndarray, np.ndarray]:
    """Pivot long-format signal rows into ``(timestamps, X)``.

    Only timestamps carrying EVERY requested channel are kept. A partial row
    would otherwise have to be imputed, and imputing a feature that the frame
    genuinely did not produce — a closed eye, a lost face — invents evidence
    rather than admitting its absence.
    """
    wanted = set(channels)
    by_ts: dict[float, dict[str, float]] = {}
    for r in signal_rows:
        ch = r.get("channel")
        if ch not in wanted:
            continue
        ts = r.get("master_ts")
        if ts is None:
            continue
        v = r.get("value")
        if v is None:
            continue
        by_ts.setdefault(float(ts), {})[ch] = float(v)

    complete = sorted(ts for ts, d in by_ts.items() if len(d) == len(wanted))
    if not complete:
        return np.empty(0), np.empty((0, len(channels)))

    X = np.array([[by_ts[ts][c] for c in channels] for ts in complete], dtype=float)
    return np.array(complete, dtype=float), X


def pool_spans(
    timestamps: np.ndarray,
    X: np.ndarray,
    spans: Sequence[TargetSpan],
    *,
    min_frames: int = 3,
    trim_fraction: float = 0.25,
) -> tuple[np.ndarray, np.ndarray, list[TargetSpan]]:
    """One feature vector per target, plus the targets that survived.

    MEDIAN over the window, after discarding the first ``trim_fraction`` of it.

    The trim is not tidiness. A dwell window opens the moment the sampling
    period starts, and the eye is still settling for the first part of it — the
    saccade allowance covers the jump, not the drift that follows it. Including
    those frames biases every target toward the previous one, which is a
    systematic error that looks exactly like a poorly-calibrated model.

    The median then handles blinks, which are not noise but brief periods where
    the iris estimate is meaningless.
    """
    kept_rows: list[np.ndarray] = []
    kept_targets: list[list[float]] = []
    kept_spans: list[TargetSpan] = []

    for span in spans:
        window = span.end_ts - span.start_ts
        lo = span.start_ts + window * trim_fraction
        sel = (timestamps >= lo) & (timestamps <= span.end_ts)
        if int(sel.sum()) < min_frames:
            continue
        kept_rows.append(np.median(X[sel], axis=0))
        kept_targets.append([span.x, span.y])
        kept_spans.append(span)

    if not kept_rows:
        return np.empty((0, X.shape[1] if X.size else 0)), np.empty((0, 2)), []

    return np.vstack(kept_rows), np.array(kept_targets, dtype=float), kept_spans


@dataclass
class GazeFitResult:
    model: RidgeGaze | None
    alpha: float | None
    n_calibration_targets: int
    n_validation_targets: int
    validation: ValidationResult | None
    passed: bool
    reasons: list[str]
    refusal: str | None = None


def fit_session(
    timestamps: np.ndarray,
    X: np.ndarray,
    spans: Sequence[TargetSpan],
    *,
    viewport_px: tuple[float, float],
    degrees_per_px: float | None,
    channels: Sequence[str] | None = None,
    use_pose: bool = True,
    criteria: GateCriteria | None = None,
    roi_radius_px: float = 100.0,
    min_calibration_targets: int = 6,
) -> GazeFitResult:
    """Fit on the calibration targets, score on the validation ones.

    Validation targets are never fitted on. §2.1's grid was chosen so the
    validation points fall BETWEEN calibration points; scoring on fitted
    coordinates would measure memorisation, and ridge with a small alpha can
    memorise 13 points almost exactly.
    """
    criteria = criteria or GateCriteria()

    # Expand to the design matrix BEFORE pooling, so the quadratic terms are
    # medianed the same way the linear ones are.
    if channels is not None:
        X = design_from_channels(X, channels, use_pose=use_pose)

    cal = [s for s in spans if s.kind == "calibration_point"]
    val = [s for s in spans if s.kind == "validation_point"]

    Xc, yc, kept_cal = pool_spans(timestamps, X, cal)
    if len(kept_cal) < min_calibration_targets:
        return GazeFitResult(
            None, None, len(kept_cal), 0, None, False,
            [f"only {len(kept_cal)} calibration targets had usable frames"],
            refusal="insufficient_calibration",
        )

    model, alpha, _ = RidgeGaze.fit_with_loocv(Xc, yc)

    Xv, yv, kept_val = pool_spans(timestamps, X, val)
    if len(kept_val) == 0:
        return GazeFitResult(
            model, alpha, len(kept_cal), 0, None, False,
            ["no validation targets had usable frames"],
            refusal="no_validation",
        )

    # One pooled sample per target, so the rate reported here is not a sampling
    # rate. It is computed separately, from the raw feature timestamps.
    pred = model.predict(Xv)
    result = validate(
        yv, pred,
        np.array([s.start_ts for s in kept_val]),
        viewport_px=viewport_px,
        roi_radius_px=roi_radius_px,
        degrees_per_px=degrees_per_px,
    )
    result = ValidationResult(
        average_offset_px=result.average_offset_px,
        average_offset_deg=result.average_offset_deg,
        percent_in_roi=result.percent_in_roi,
        samples_per_sec=effective_rate(timestamps),
        n_samples=result.n_samples,
        n_targets=result.n_targets,
    )

    ok, reasons = gate(result, criteria)
    return GazeFitResult(model, alpha, len(kept_cal), len(kept_val), result, ok, reasons)


def effective_rate(timestamps: np.ndarray) -> float:
    """Feature rate over the span actually covered.

    §5.3's 5Hz exclusion threshold is evaluated against this, so it has to be
    the rate at which gaze was genuinely measurable — not the camera's frame
    rate, which counts frames where the eyes were shut or the face was lost.
    """
    if len(timestamps) < 2:
        return 0.0
    span_s = (timestamps[-1] - timestamps[0]) / 1000.0
    return float(len(timestamps) / span_s) if span_s > 0 else 0.0


# ---------------------------------------------------------------------------
# how far outside its own calibration is the model being asked to guess?
# ---------------------------------------------------------------------------

def extrapolation_distance(
    X_design: np.ndarray, calibration_design: np.ndarray,
) -> np.ndarray:
    """Mahalanobis distance of each sample from the calibration distribution.

    A validation score says how well the model interpolates BETWEEN calibration
    points. It says nothing about what happens when the features leave the range
    the model ever saw — and on the first real session, 34% of predicted gaze
    samples landed off-screen entirely, with 11% beyond twice the screen
    dimensions and one reaching fifteen screen-heights below the bottom.

    Quadratic terms make this worse, not better: they buy curvature inside the
    calibrated region and diverge quickly outside it. So the model is at its
    most confident-looking exactly where it is least supported.

    Distance is measured in the calibration set's own units, so "far" means far
    relative to how much this participant's features actually varied while being
    calibrated. A regularised covariance keeps it defined when there are fewer
    calibration targets than design columns, which with 13 points is normal.
    """
    mu = calibration_design.mean(axis=0)
    centred = calibration_design - mu
    n, d = centred.shape

    cov = (centred.T @ centred) / max(n - 1, 1)
    # Ridge on the covariance for the same reason as on the regression: with 13
    # targets and more columns than that, the empirical covariance is singular.
    cov += np.eye(d) * (np.trace(cov) / d) * 1e-3

    try:
        inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        return np.full(len(X_design), np.nan)

    delta = X_design - mu
    return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", delta, inv, delta), 0.0))


def onscreen_mask(pred: np.ndarray, margin: float = 0.1) -> np.ndarray:
    """Which predictions land on the screen, within a small margin.

    The margin is not generosity — gaze genuinely does land slightly outside a
    screen's bounds near its edges, and the estimator's own error is around a
    degree. Beyond it, the prediction is not a measurement of where someone
    looked; it is the model being asked a question outside its training range.
    """
    return ((pred[:, 0] > -margin) & (pred[:, 0] < 1 + margin)
            & (pred[:, 1] > -margin) & (pred[:, 1] < 1 + margin))

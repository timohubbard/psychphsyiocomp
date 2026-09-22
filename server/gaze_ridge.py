"""Per-participant ridge gaze estimator, and the metrics that judge it.

WHY THIS IS NOT AN ENGINE
-------------------------
Engines are pure functions of ``(media, params)`` that know nothing about the
database, the study runner, or clocks. A calibrated gaze estimator cannot honour
that: fitting it requires knowing which target was on screen at which instant,
and stimulus events live on the master clock — the one thing engines are
explicitly forbidden to reason about (REPORT.md §3.3).

So the work splits in two:

    gaze.mediapipe_features   an engine. video -> eye/iris features, native ts.
                              knows nothing, re-runnable, swappable.

    this module               a pipeline stage, after alignment. joins aligned
                              features to calibration events, fits, and emits
                              gaze.x / gaze.y under its own `source`.

That split buys something beyond tidiness. Features are stored, so a better
estimator re-runs over them without decoding video again — which matters because
§2.1 found human annotation of the *same* webcam video reached 92% where
WebGazer reached 70%. The estimator is the bottleneck, so the estimator is the
part that will be replaced, repeatedly.

WHY RIDGE
---------
This is deliberately the floor, not the ceiling: something honest to measure the
real model against. Thirteen calibration points against a feature vector of
similar size is a regime where ordinary least squares interpolates the noise
exactly and generalises terribly. Ridge is the smallest defensible thing that
does not, it is closed-form, and its regularisation strength can be chosen by
leave-one-out cross-validation at no extra cost — which matters when "leave one
out" means discarding 1/13th of everything you know about this participant.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: §5.3: 5 Hz was applied as an exclusion threshold in a published study,
#: removing 18 of 220 participants. Achieved rates there were mean 19.7Hz
#: (SD 6.4, range 5.5-30.1), so this is a floor, not a target.
MIN_SAMPLING_RATE_HZ = 5.0


# ---------------------------------------------------------------------------
# the estimator
# ---------------------------------------------------------------------------

@dataclass
class RidgeGaze:
    """Ridge regression from eye features to normalised screen coordinates.

    Fitted per participant. A model fitted on one person's calibration says
    nothing about anyone else: the mapping folds in their face geometry, their
    seating position and their camera's optics all at once.
    """

    alpha: float = 1.0
    _w: np.ndarray | None = None
    _mu: np.ndarray | None = None
    _sigma: np.ndarray | None = None

    # -- fitting -----------------------------------------------------------

    def fit(self, X: np.ndarray, y: np.ndarray) -> RidgeGaze:
        """Fit to ``X`` (n_samples, n_features) and ``y`` (n_samples, 2).

        Features are standardised first. Ridge penalises coefficients by their
        magnitude, so without standardisation the penalty falls hardest on
        whichever feature happens to be measured in the smallest units — an
        iris offset in normalised eye-widths and a head yaw in degrees would be
        regularised at wildly different effective strengths purely because of
        the units they arrived in.
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if X.ndim != 2 or y.ndim != 2 or y.shape[1] != 2:
            raise ValueError(f"expected X (n, d) and y (n, 2), got {X.shape} and {y.shape}")
        if len(X) != len(y):
            raise ValueError(f"X has {len(X)} rows, y has {len(y)}")

        self._mu = X.mean(axis=0)
        # A constant feature has zero spread and would divide to infinity. It
        # also carries no information, so mapping it to zero is both safe and
        # correct rather than merely safe.
        self._sigma = X.std(axis=0)
        self._sigma[self._sigma < 1e-12] = 1.0

        Z = self._design(X)
        d = Z.shape[1]

        # The intercept is not penalised. Shrinking it would pull predictions
        # toward the origin — the top-left corner of the screen — rather than
        # toward the data, which is not a prior anyone holds.
        penalty = np.eye(d) * self.alpha
        penalty[0, 0] = 0.0

        self._w = np.linalg.solve(Z.T @ Z + penalty, Z.T @ y)
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self._w is None:
            raise RuntimeError("fit() before predict()")
        return self._design(np.asarray(X, dtype=float)) @ self._w

    def _design(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self._mu) / self._sigma
        return np.hstack([np.ones((len(Z), 1)), Z])

    # -- choosing alpha ----------------------------------------------------

    @staticmethod
    def fit_with_loocv(
        X: np.ndarray,
        y: np.ndarray,
        alphas: np.ndarray | None = None,
    ) -> tuple[RidgeGaze, float, np.ndarray]:
        """Fit, choosing ``alpha`` by leave-one-out cross-validation.

        Returns ``(model, best_alpha, loo_errors_per_alpha)``.

        LOOCV has a closed form for ridge — the hat matrix gives every held-out
        residual from a single fit — so the honest choice costs about as much as
        an arbitrary one. With 13 calibration points that matters: any scheme
        that holds out a *fold* is throwing away a large fraction of everything
        known about this participant, and repeating the fit 13 times naively
        would be the obvious alternative.
        """
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        if alphas is None:
            alphas = np.logspace(-3, 3, 25)

        errors = np.empty(len(alphas))
        for i, a in enumerate(alphas):
            errors[i] = RidgeGaze(alpha=float(a))._loo_error(X, y)

        best = RidgeGaze(alpha=float(alphas[int(np.argmin(errors))])).fit(X, y)
        return best, best.alpha, errors

    def _loo_error(self, X: np.ndarray, y: np.ndarray) -> float:
        """Mean leave-one-out euclidean error, via the hat matrix.

        For a linear smoother y_hat = H y, the leave-one-out residual is the
        ordinary residual divided by (1 - H_ii). No refitting required.
        """
        self.fit(X, y)
        Z = self._design(X)
        d = Z.shape[1]
        penalty = np.eye(d) * self.alpha
        penalty[0, 0] = 0.0

        try:
            H = Z @ np.linalg.solve(Z.T @ Z + penalty, Z.T)
        except np.linalg.LinAlgError:
            return float("inf")

        resid = y - Z @ self._w
        denom = 1.0 - np.clip(np.diag(H), None, 1.0 - 1e-9)
        loo = resid / denom[:, None]
        return float(np.mean(np.hypot(loo[:, 0], loo[:, 1])))


# ---------------------------------------------------------------------------
# validation metrics
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ValidationResult:
    """What a validation block measured. Numbers only — no pass/fail.

    §5.3 is explicit that jsPsych's `webgazer-validate` emits these three and
    **publishes no cutoff**, because every inclusion criterion is the
    researcher's to preregister. Baking a threshold in here would invent a
    standard that does not exist and hide the choice from the person who has to
    defend it. `gate()` takes criteria as an argument for exactly that reason.
    """

    average_offset_px: float
    average_offset_deg: float | None
    percent_in_roi: float
    samples_per_sec: float
    n_samples: int
    n_targets: int


def validate(
    targets: np.ndarray,
    predictions: np.ndarray,
    timestamps_ms: np.ndarray,
    *,
    viewport_px: tuple[float, float],
    roi_radius_px: float,
    degrees_per_px: float | None = None,
) -> ValidationResult:
    """Score predictions against the targets that produced them.

    ``targets`` and ``predictions`` are normalised 0..1 screen coordinates.

    ``degrees_per_px`` comes from the virtual chinrest and is **None when the
    chinrest refused**. The angular figure is then None rather than computed
    from a nominal viewing distance — §5.1 measured distance at mean 47.3cm with
    SD 8.9 across 1,153 participants, so a degree figure from an assumed
    distance is a pixel count wearing a unit. The pixel figure is always
    available and always honest; it is simply not comparable between
    participants, which is the whole reason the angular one is wanted.
    """
    targets = np.asarray(targets, dtype=float)
    predictions = np.asarray(predictions, dtype=float)
    timestamps_ms = np.asarray(timestamps_ms, dtype=float)

    if len(targets) != len(predictions):
        raise ValueError("targets and predictions must be the same length")
    if len(targets) == 0:
        raise ValueError("no samples to validate")

    w, h = viewport_px
    dx = (predictions[:, 0] - targets[:, 0]) * w
    dy = (predictions[:, 1] - targets[:, 1]) * h
    offsets_px = np.hypot(dx, dy)

    mean_px = float(np.mean(offsets_px))
    in_roi = float(np.mean(offsets_px <= roi_radius_px))

    # Rate over the span actually covered, not samples divided by a nominal
    # duration. §2.1 measured 9-39 fps jittering across home setups, so the
    # difference is not academic.
    span_s = (timestamps_ms[-1] - timestamps_ms[0]) / 1000.0 if len(timestamps_ms) > 1 else 0.0
    rate = float(len(timestamps_ms) / span_s) if span_s > 0 else 0.0

    unique_targets = len({(round(x, 6), round(y, 6)) for x, y in targets})

    return ValidationResult(
        average_offset_px=mean_px,
        average_offset_deg=(mean_px * degrees_per_px) if degrees_per_px else None,
        percent_in_roi=in_roi,
        samples_per_sec=rate,
        n_samples=len(targets),
        n_targets=unique_targets,
    )


@dataclass(frozen=True)
class GateCriteria:
    """Inclusion criteria. The researcher's to preregister, not ours to assume."""

    max_offset_deg: float | None = None
    max_offset_px: float | None = None
    min_percent_in_roi: float = 0.0
    min_samples_per_sec: float = MIN_SAMPLING_RATE_HZ


def gate(result: ValidationResult, criteria: GateCriteria) -> tuple[bool, list[str]]:
    """Decide whether a validation block passes. Returns ``(pass, reasons)``.

    Every failure is named, and the pattern §5.1 records from Kaduk et al. is a
    gate with forced RETRY rather than exclusion: nobody is dropped for failing
    this, they are asked to recalibrate. That distinction is why this returns
    reasons rather than a bare bool.
    """
    reasons: list[str] = []

    if criteria.max_offset_deg is not None:
        if result.average_offset_deg is None:
            # Refusing to evaluate an angular criterion without geometry is the
            # point. Silently falling back to the pixel criterion would apply a
            # threshold the researcher did not preregister.
            reasons.append("no_geometry_for_angular_criterion")
        elif result.average_offset_deg > criteria.max_offset_deg:
            reasons.append(
                f"offset {result.average_offset_deg:.2f}deg > {criteria.max_offset_deg}deg"
            )

    if criteria.max_offset_px is not None and result.average_offset_px > criteria.max_offset_px:
        reasons.append(f"offset {result.average_offset_px:.0f}px > {criteria.max_offset_px}px")

    if result.percent_in_roi < criteria.min_percent_in_roi:
        reasons.append(
            f"in-ROI {result.percent_in_roi:.0%} < {criteria.min_percent_in_roi:.0%}"
        )

    if result.samples_per_sec < criteria.min_samples_per_sec:
        reasons.append(
            f"{result.samples_per_sec:.1f}Hz < {criteria.min_samples_per_sec}Hz"
        )

    return (not reasons), reasons

"""Fixation and saccade classification by two-state HMM.

NOT I-VT or I-DT, and that is the single most important thing about this file.
§4.1 is explicit: velocity- and dispersion-threshold detectors reach ~90-92%
accuracy on static stimuli but **~68-70% under real head movement at the same
30 Hz**, and barely better than chance on dynamic video. A webcam pipeline
running at 9-39 Hz on participants who are not chin-rested is exactly the
regime where they fail, and it is the direct engineering reason iMotions built
WebET around HMM classification instead.

The difference is not tuning. A threshold classifies each sample independently,
so a single noisy sample becomes a one-sample "saccade" and the estimate of
fixation count inflates without bound as noise rises. An HMM classifies the
whole sequence jointly: a sample is assigned to the state that best explains it
*given what came before and after*, so isolated noise is absorbed by a fixation
that is otherwise well-supported on both sides. That is the property being
bought, and a test measures it rather than asserting it.

§4.1 also warns that fixation counts and durations are algorithm-dependent, not
just data-dependent, and that every metric should say which processing stage it
reflects. Hence `source` on every event this produces, and the classifier's
parameters recorded alongside.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

FIXATION, SACCADE = 0, 1


@dataclass(frozen=True)
class HMMParams:
    """Two-state model over log gaze velocity.

    Velocity is modelled in LOG space. Gaze speed is strictly positive and
    spans orders of magnitude — a drift of 1 deg/s and a saccade of 300 deg/s
    are both ordinary — so a Gaussian on raw velocity would put meaningful
    probability mass below zero and be dominated by the saccade tail. In log
    space both states are roughly symmetric and comparably scaled.
    """

    #: Mean log-velocity (deg/s) while fixating. Microsaccades and tracker noise
    #: keep this well above zero; ~3 deg/s is a typical resting figure for a
    #: webcam-grade signal.
    fixation_log_mean: float = math.log(3.0)
    fixation_log_sd: float = 1.0

    #: Saccades run 30-500 deg/s. The wide SD is deliberate: a low-rate signal
    #: undersamples the peak, so measured saccade velocity varies hugely with
    #: where the samples happen to land.
    saccade_log_mean: float = math.log(80.0)
    saccade_log_sd: float = 1.2

    #: Expected durations, which set the transition probabilities. Typical
    #: fixations are 200-400ms and saccades 30-80ms; at webcam rates a saccade
    #: often occupies a single sample, so the model must not be surprised by a
    #: one-sample saccade — only by a one-sample *fixation*.
    mean_fixation_ms: float = 250.0
    mean_saccade_ms: float = 50.0

    @staticmethod
    def estimate_from(speed: np.ndarray, *, min_separation_sd: float = 2.5) -> HMMParams:
        """Fit the velocity scales to this session instead of assuming them.

        The defaults on this class describe a research-grade tracker, and using
        them on webcam data is a modelling error rather than a tuning choice.
        A webcam estimator with ~1.65 deg accuracy sampled at 30 Hz produces
        apparent velocities of 30-60 deg/s *while the eye is still* — squarely
        inside the saccade range of a chin-rested setup, so a fixed model
        classifies ordinary fixation jitter as saccades and the fixation count
        explodes.

        Noise differs per participant, per camera and per lighting condition, so
        no single fixed pair of scales can work across a population. Estimating
        from the session's own velocity distribution is what §4.1 means by
        adaptive detection, and it is the difference between this classifier
        working and not.

        Most samples in any trace are fixation, so the median log-velocity
        locates the fixation state and a high percentile locates the saccade
        state. ``min_separation_sd`` then guarantees the two stay distinguishable
        even on a trace containing no saccades at all — without it, a perfectly
        still eye would have its own jitter promoted to "saccade" simply because
        some samples sit at the top of the noise distribution.
        """
        lv = np.log(np.maximum(np.asarray(speed, dtype=float), 1e-3))
        if len(lv) < 4:
            return HMMParams()

        fix_mu = float(np.median(lv))
        mad = float(np.median(np.abs(lv - fix_mu)))
        fix_sd = max(mad * 1.4826, 0.35)

        sac_mu = max(float(np.percentile(lv, 97)), fix_mu + min_separation_sd * fix_sd)

        return HMMParams(
            fixation_log_mean=fix_mu,
            fixation_log_sd=fix_sd,
            saccade_log_mean=sac_mu,
            saccade_log_sd=fix_sd * 1.3,
        )

    def transition_matrix(self, dt_ms: float) -> np.ndarray:
        """Per-sample transition probabilities at this sampling interval.

        Derived from the expected durations rather than hard-coded, because the
        same probability means different things at 9 Hz and 39 Hz — and §2.1
        measured exactly that spread across home setups. A matrix tuned at one
        rate silently changes behaviour at another.
        """
        p_leave_fix = min(0.9, dt_ms / max(self.mean_fixation_ms, 1e-9))
        p_leave_sac = min(0.9, dt_ms / max(self.mean_saccade_ms, 1e-9))
        return np.array([
            [1.0 - p_leave_fix, p_leave_fix],
            [p_leave_sac, 1.0 - p_leave_sac],
        ])


@dataclass
class GazeEvent:
    kind: str                 # 'fixation' | 'saccade'
    onset_ts: float
    offset_ts: float
    n_samples: int
    x: float | None = None    # fixation centroid, normalised screen coords
    y: float | None = None
    amplitude_deg: float | None = None   # saccades only
    peak_velocity_deg_s: float | None = None

    @property
    def duration_ms(self) -> float:
        return self.offset_ts - self.onset_ts


def angular_velocity(
    ts_ms: np.ndarray, x: np.ndarray, y: np.ndarray,
    *, viewport_px: tuple[float, float], degrees_per_px: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-sample angular speed in deg/s, and the interval it was measured over.

    Returns arrays of length ``n-1``, aligned to the LATER sample of each pair.

    Requires real geometry. Velocity thresholds in pixels per second are not
    comparable between participants — §5.1 measured viewing distance at mean
    47.3cm with SD 8.9 — so this refuses to work in pixel space rather than
    producing numbers that look comparable and are not.
    """
    if degrees_per_px is None or degrees_per_px <= 0:
        raise ValueError("angular velocity needs degrees_per_px from the chinrest")

    w, h = viewport_px
    dx = np.diff(x) * w * degrees_per_px
    dy = np.diff(y) * h * degrees_per_px
    dt = np.diff(ts_ms)

    with np.errstate(divide="ignore", invalid="ignore"):
        speed = np.hypot(dx, dy) / (dt / 1000.0)
    speed[~np.isfinite(speed)] = 0.0
    return speed, dt


def _log_gaussian(v: np.ndarray, mean: float, sd: float) -> np.ndarray:
    """Log density of log-velocity under one state."""
    # Floor rather than clip to zero: a genuinely stationary sample has zero
    # measured speed, and log(0) would make its emission probability -inf for
    # BOTH states, letting the transition prior decide alone.
    lv = np.log(np.maximum(v, 1e-3))
    return -0.5 * ((lv - mean) / sd) ** 2 - math.log(sd * math.sqrt(2 * math.pi))


def viterbi(
    speed: np.ndarray, dt_ms: np.ndarray, params: HMMParams,
) -> np.ndarray:
    """Most likely state sequence. Returns one label per velocity sample.

    Joint decoding over the whole sequence is the entire point: a sample is
    assigned to the state that best explains it given its neighbours, so an
    isolated noise spike inside a well-supported fixation does not become a
    one-sample saccade the way a threshold would make it.
    """
    n = len(speed)
    if n == 0:
        return np.empty(0, dtype=int)

    emit = np.column_stack([
        _log_gaussian(speed, params.fixation_log_mean, params.fixation_log_sd),
        _log_gaussian(speed, params.saccade_log_mean, params.saccade_log_sd),
    ])

    # Sessions begin with the participant looking at something.
    delta = np.array([math.log(0.9), math.log(0.1)]) + emit[0]
    backptr = np.zeros((n, 2), dtype=int)

    for i in range(1, n):
        with np.errstate(divide="ignore"):
            log_trans = np.log(params.transition_matrix(float(dt_ms[i - 1])))
        scores = delta[:, None] + log_trans           # from-state -> to-state
        backptr[i] = np.argmax(scores, axis=0)
        delta = np.max(scores, axis=0) + emit[i]

    states = np.zeros(n, dtype=int)
    states[-1] = int(np.argmax(delta))
    for i in range(n - 1, 0, -1):
        states[i - 1] = backptr[i, states[i]]
    return states


@dataclass
class ClassificationResult:
    events: list[GazeEvent] = field(default_factory=list)
    n_fixations: int = 0
    n_saccades: int = 0
    median_fixation_ms: float | None = None
    refusal: str | None = None


def classify(
    ts_ms: Sequence[float], x: Sequence[float], y: Sequence[float],
    *, viewport_px: tuple[float, float], degrees_per_px: float | None,
    params: HMMParams | None = None, min_fixation_ms: float = 60.0,
) -> ClassificationResult:
    """Segment a gaze trace into fixations and saccades.

    Refuses without geometry rather than classifying in pixel space. A velocity
    threshold in px/s means something different for every participant, and the
    resulting fixation counts would not be comparable across a study — which is
    the only thing anyone wants them for.
    """
    ts_ms = np.asarray(ts_ms, dtype=float)
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if len(ts_ms) < 3:
        return ClassificationResult(refusal="too_few_samples")
    if degrees_per_px is None or degrees_per_px <= 0:
        return ClassificationResult(refusal="no_geometry")

    speed, dt = angular_velocity(ts_ms, x, y,
                                 viewport_px=viewport_px, degrees_per_px=degrees_per_px)
    # Adaptive by default. Fixed velocity scales describe a chin-rested tracker
    # and misclassify webcam jitter as saccades — see HMMParams.estimate_from.
    params = params or HMMParams.estimate_from(speed)
    states = viterbi(speed, dt, params)

    # States are aligned to the later sample of each pair, so sample i+1 carries
    # state i. Sample 0 inherits the first state: it cannot have a velocity of
    # its own, and dropping it would lose the start of the first fixation.
    per_sample = np.concatenate([[states[0]], states])

    events: list[GazeEvent] = []
    start = 0
    for i in range(1, len(per_sample) + 1):
        if i < len(per_sample) and per_sample[i] == per_sample[start]:
            continue

        kind = "fixation" if per_sample[start] == FIXATION else "saccade"
        onset, offset = ts_ms[start], ts_ms[i - 1]
        ev = GazeEvent(kind=kind, onset_ts=onset, offset_ts=offset,
                       n_samples=i - start)

        if kind == "fixation":
            # Median, not mean: a fixation that ends with the eye already
            # leaving drags a mean toward the next target.
            ev.x = float(np.median(x[start:i]))
            ev.y = float(np.median(y[start:i]))
        else:
            # Measured from the sample BEFORE the saccade to the sample AFTER
            # it, not across the saccade's own samples. At webcam rates a
            # saccade usually occupies a single sample, and the displacement
            # within one sample is zero by definition — which silently reported
            # every fast saccade as having no amplitude at all.
            a = max(start - 1, 0)
            b = min(i, len(x) - 1)
            dx = (x[b] - x[a]) * viewport_px[0] * degrees_per_px
            dy = (y[b] - y[a]) * viewport_px[1] * degrees_per_px
            ev.amplitude_deg = float(math.hypot(dx, dy))
            seg = speed[max(start - 1, 0):max(i - 1, 1)]
            ev.peak_velocity_deg_s = float(np.max(seg)) if len(seg) else None

        events.append(ev)
        start = i

    # Very short fixations are almost always a saccade the sampling rate split
    # in two. Merging them is a stated processing step, not a silent cleanup —
    # §4.1 insists every metric declares which stage it reflects.
    events = _merge_short_fixations(events, min_fixation_ms)

    fix = [e for e in events if e.kind == "fixation"]
    return ClassificationResult(
        events=events,
        n_fixations=len(fix),
        n_saccades=sum(1 for e in events if e.kind == "saccade"),
        median_fixation_ms=(float(np.median([e.duration_ms for e in fix])) if fix else None),
    )


def _merge_short_fixations(events: list[GazeEvent], min_ms: float) -> list[GazeEvent]:
    out: list[GazeEvent] = []
    for ev in events:
        if (ev.kind == "fixation" and ev.duration_ms < min_ms
                and out and out[-1].kind == "saccade"):
            out[-1] = GazeEvent(
                kind="saccade", onset_ts=out[-1].onset_ts, offset_ts=ev.offset_ts,
                n_samples=out[-1].n_samples + ev.n_samples,
                amplitude_deg=out[-1].amplitude_deg,
                peak_velocity_deg_s=out[-1].peak_velocity_deg_s)
            continue
        out.append(ev)
    return out

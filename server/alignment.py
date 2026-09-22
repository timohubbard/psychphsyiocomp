"""Clock alignment — the one service engines are not allowed to implement.

Every engine emits samples stamped against its OWN native clock and never
converts between clocks. This module is the single place that maps native
timestamps onto a common ``master_ts``.

REPORT.md §3.3 is the reason for that separation. In a browser,
``AudioContext.currentTime`` is a different clock from ``performance.now()``,
video frame timestamps come from the container rather than a wall clock, and
``Date.now()`` is not monotonic. Letting each engine reconcile those itself
means shipping the same subtle bug once per engine.

The other half of §3.3 matters just as much: audio-visual synchrony is the
*least precise* aspect of browser-based timing, and no online experiment system
reliably delivers precisely-timed audio onset. So this module does not pretend
to millisecond truth. It estimates an offset from observed anchors, propagates
an honest uncertainty alongside every converted timestamp, and — critically —
refuses to align at all when it has no evidence, rather than silently assuming
a zero offset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

#: Assumed uncertainty (ms) when a single anchor gives offset but not drift.
#: Browser display timing alone varies ~11.5ms (Chrome) to ~30ms (Safari) per
#: §3.3, so a sub-10ms claim from one anchor would be dishonest.
SINGLE_ANCHOR_UNCERTAINTY_MS = 25.0

#: Floor on reported uncertainty. Even a well-fitted multi-anchor solution
#: cannot beat the platform's own presentation jitter.
MIN_UNCERTAINTY_MS = 5.0


class AlignmentError(Exception):
    """Raised for programming errors, never for 'we lack evidence to align'."""


@dataclass(frozen=True)
class Anchor:
    """One moment observed on two clocks at once.

    The canonical source is the sync clapper: the capture page flashes a
    high-contrast marker at a known ``performance.now()`` and the aligner finds
    that luminance spike in the decoded video. That yields a *measured* offset
    rather than an assumed one.
    """

    clock_a: str
    ts_a: float
    clock_b: str
    ts_b: float
    #: How precisely this coincidence was observed. A clapper detected to the
    #: nearest frame at 30fps is worth no better than ~33ms.
    uncertainty_ms: float
    label: str = ""

    def offset_b_from_a(self) -> float:
        """Offset to add to a ``clock_a`` timestamp to express it in ``clock_b``."""
        return self.ts_b - self.ts_a


@dataclass(frozen=True)
class ClockSolution:
    """How to map one native clock onto the master clock."""

    clock_id: str
    offset_ms: float
    #: Rate ratio (master units per native unit). 1.0 when undetermined.
    rate: float = 1.0
    uncertainty_ms: float = SINGLE_ANCHOR_UNCERTAINTY_MS
    n_anchors: int = 0
    #: Set when the clock could NOT be aligned. master_ts stays NULL and this
    #: explains why — an unaligned stream must be visibly unaligned, not
    #: silently wrong.
    unaligned_reason: str | None = None

    @property
    def aligned(self) -> bool:
        return self.unaligned_reason is None

    def to_master(self, native_ts: float) -> tuple[float | None, float | None]:
        if not self.aligned:
            return None, None
        return native_ts * self.rate + self.offset_ms, self.uncertainty_ms


@dataclass
class ClockRegistry:
    """Solves native-clock -> master-clock mappings from observed anchors."""

    master_clock_id: str
    _anchors: list[Anchor] = field(default_factory=list)
    _known_clocks: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self._known_clocks.add(self.master_clock_id)

    def register_clock(self, clock_id: str) -> None:
        self._known_clocks.add(clock_id)

    def add_anchor(self, anchor: Anchor) -> None:
        if anchor.uncertainty_ms < 0:
            raise AlignmentError("anchor uncertainty must be non-negative")
        self._known_clocks.add(anchor.clock_a)
        self._known_clocks.add(anchor.clock_b)
        self._anchors.append(anchor)

    def anchors_for(self, clock_id: str) -> list[Anchor]:
        """Anchors linking ``clock_id`` to the master clock, normalised.

        Each is oriented so ``clock_a`` is the native clock and ``clock_b`` the
        master, so downstream fitting does not have to care which way round the
        caller supplied it.
        """
        out: list[Anchor] = []
        for a in self._anchors:
            if a.clock_a == clock_id and a.clock_b == self.master_clock_id:
                out.append(a)
            elif a.clock_b == clock_id and a.clock_a == self.master_clock_id:
                out.append(
                    Anchor(
                        clock_a=clock_id, ts_a=a.ts_b,
                        clock_b=self.master_clock_id, ts_b=a.ts_a,
                        uncertainty_ms=a.uncertainty_ms, label=a.label,
                    )
                )
        return out

    def solve(self, clock_id: str) -> ClockSolution:
        """Fit a mapping from ``clock_id`` onto the master clock."""
        if clock_id == self.master_clock_id:
            return ClockSolution(
                clock_id=clock_id, offset_ms=0.0, rate=1.0,
                uncertainty_ms=0.0, n_anchors=0,
            )

        anchors = self.anchors_for(clock_id)

        if not anchors:
            # No evidence. Refusing is the whole point — a zero-offset guess
            # would look aligned and be wrong by an unknown amount, which is
            # strictly worse than a visible NULL.
            return ClockSolution(
                clock_id=clock_id, offset_ms=0.0, uncertainty_ms=math.inf,
                n_anchors=0,
                unaligned_reason=(
                    f"no anchors linking '{clock_id}' to master "
                    f"'{self.master_clock_id}'; master_ts left NULL"
                ),
            )

        if len(anchors) == 1:
            a = anchors[0]
            return ClockSolution(
                clock_id=clock_id,
                offset_ms=a.offset_b_from_a(),
                rate=1.0,  # cannot estimate drift from one point
                uncertainty_ms=max(
                    a.uncertainty_ms, SINGLE_ANCHOR_UNCERTAINTY_MS, MIN_UNCERTAINTY_MS
                ),
                n_anchors=1,
            )

        return self._fit_linear(clock_id, anchors)

    @staticmethod
    def _fit_linear(clock_id: str, anchors: list[Anchor]) -> ClockSolution:
        """Weighted least-squares fit of master = rate * native + offset.

        Two or more anchors let us estimate clock *drift* as well as offset,
        which matters over a long session: consumer clocks routinely differ by
        tens of ppm, so a 30-minute recording can accumulate real skew.
        """
        weights = [1.0 / max(a.uncertainty_ms, MIN_UNCERTAINTY_MS) ** 2 for a in anchors]
        xs = [a.ts_a for a in anchors]
        ys = [a.ts_b for a in anchors]

        sw = sum(weights)
        mean_x = sum(w * x for w, x in zip(weights, xs)) / sw
        mean_y = sum(w * y for w, y in zip(weights, ys)) / sw

        sxx = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, xs))
        sxy = sum(w * (x - mean_x) * (y - mean_y) for w, x, y in zip(weights, xs, ys))

        if sxx <= 0:
            # All anchors landed at the same native timestamp; drift is
            # undetermined, so fall back to offset-only rather than dividing
            # by zero and producing a nonsense rate.
            return ClockSolution(
                clock_id=clock_id, offset_ms=mean_y - mean_x, rate=1.0,
                uncertainty_ms=max(
                    min(a.uncertainty_ms for a in anchors),
                    SINGLE_ANCHOR_UNCERTAINTY_MS,
                ),
                n_anchors=len(anchors),
            )

        rate = sxy / sxx
        offset = mean_y - rate * mean_x

        # Residual spread is the honest uncertainty: if the anchors disagree
        # with the fitted line, that disagreement IS the error bar, regardless
        # of how precise each individual observation claimed to be.
        residuals = [y - (rate * x + offset) for x, y in zip(xs, ys)]
        rms = math.sqrt(sum(r * r for r in residuals) / len(residuals))
        best_anchor = min(a.uncertainty_ms for a in anchors)
        uncertainty = max(rms, best_anchor, MIN_UNCERTAINTY_MS)

        return ClockSolution(
            clock_id=clock_id, offset_ms=offset, rate=rate,
            uncertainty_ms=uncertainty, n_anchors=len(anchors),
        )

    def solve_all(self, clock_ids: Iterable[str] | None = None) -> dict[str, ClockSolution]:
        ids = set(clock_ids) if clock_ids is not None else set(self._known_clocks)
        ids.add(self.master_clock_id)
        return {c: self.solve(c) for c in sorted(ids)}


#: How long the capture page holds the sync flash. Mirrors TIMINGS.clapperFlashMs
#: in web/src/sequence.js — the detector matches on this duration, so the two
#: must agree. A 200ms flash is 6 frames at 30fps, not a single bright frame.
CLAPPER_FLASH_MS = 200.0

#: Rolling-median window for the luminance baseline. Long enough to be unmoved
#: by the flash itself, short enough to track auto-exposure and room-light drift
#: across a session that may run for many minutes.
BASELINE_WINDOW_MS = 3000.0


def _rolling_baseline(ts: list[float], values: list[float], window_ms: float) -> list[float]:
    """Median of a centred time window around each sample.

    A *local* baseline, not the session median, because a webcam's auto-exposure
    walks the whole signal over a long session. Measured on a real capture: the
    baseline sat at 185.9 before the first clapper and 182.8 before the second,
    so a single global median mis-scores one of them no matter where it is set.
    """
    out: list[float] = []
    half = window_ms / 2.0
    lo = hi = 0
    for i, t in enumerate(ts):
        while lo < len(ts) and ts[lo] < t - half:
            lo += 1
        while hi < len(ts) and ts[hi] <= t + half:
            hi += 1
        window = sorted(values[lo:hi]) or [values[i]]
        out.append(window[len(window) // 2])
    return out


def detect_clappers_in_luma(
    luma_by_ts: list[tuple[float, float]],
    *,
    z_threshold: float = 4.0,
    min_absolute_rise: float = 2.5,
    min_samples: int = 10,
    min_edge_fraction: float = 0.4,
    flash_duration_ms: float = CLAPPER_FLASH_MS,
    baseline_window_ms: float = BASELINE_WINDOW_MS,
) -> list[tuple[float, float, float]]:
    """Find every sync-clapper flash in a luminance series.

    Returns ``(native_ts, uncertainty_ms, score)`` per flash, strongest first.

    The flash is a PLATEAU of known length, not a spike, and that is what makes
    it separable from noise. The detector averages each candidate window of
    ``flash_duration_ms`` against a local rolling-median baseline: a sustained
    rise accumulates across the whole window, while single-frame noise is
    divided down by the window length. Scoring a point maximum instead throws
    that discrimination away and forces the threshold so high that real flashes
    are missed.

    Which is exactly what happened. The previous implementation required a
    15-luma rise over the session median and took the global peak. On the first
    real capture the flash was **+8.5 luma** — unmistakable to the eye, a clean
    7-frame plateau at the right instant — and was rejected, leaving every
    server-side row with a NULL ``master_ts``. The tests did not catch it
    because they modelled the flash as one bright frame at 240 against a
    baseline of 100, a contrast no real room produces: a camera already exposed
    for a lit room has little headroom left when the screen turns white.
    """
    n = len(luma_by_ts)
    if n < min_samples:
        return []

    ts = [t for t, _ in luma_by_ts]
    values = [v for _, v in luma_by_ts]
    baseline = _rolling_baseline(ts, values, baseline_window_ms)
    detrended = [v - b for v, b in zip(values, baseline)]

    # Noise scale from successive DIFFERENCES, not from the detrended residual.
    #
    # The residual is the wrong basis: a rolling median tracks the signal so
    # closely that the residual collapses toward zero, the estimated sd with it,
    # and every z-score explodes to meaninglessness. Measured on a real capture,
    # that produced scores of 132 and 76 for a genuine flash and a spurious one
    # alike — the statistical test had stopped participating in the decision and
    # only the absolute threshold was doing any work.
    #
    # Successive differences measure frame-to-frame noise directly and are blind
    # to any drift the baseline already removed. For iid noise the MAD of the
    # differences estimates sigma once scaled by 1.4826/sqrt(2).
    diffs = [b - a for a, b in zip(detrended, detrended[1:])]
    if diffs:
        dmed = sorted(diffs)[len(diffs) // 2]
        dmad = sorted(abs(d - dmed) for d in diffs)[len(diffs) // 2]
        robust_sd = dmad * 1.4826 / math.sqrt(2.0)
    else:
        robust_sd = 0.0

    intervals = [b - a for a, b in zip(ts, ts[1:]) if b > a]
    frame_interval = sorted(intervals)[len(intervals) // 2] if intervals else SINGLE_ANCHOR_UNCERTAINTY_MS
    span = max(1, round(flash_duration_ms / frame_interval)) if frame_interval > 0 else 1

    # Averaging `span` samples reduces noise by sqrt(span); the window mean must
    # be scored against that, not against the single-sample noise.
    window_noise = robust_sd / math.sqrt(span) if robust_sd > 0 else 0.0

    def _mean(lo: int, hi: int) -> float:
        lo, hi = max(0, lo), min(n, hi)
        return sum(detrended[lo:hi]) / (hi - lo) if hi > lo else 0.0

    # Matched filter: mean elevation over a window the length of the flash,
    # required to be a PULSE rather than a step.
    candidates: list[tuple[float, float, float]] = []
    for i in range(n - span + 1):
        rise = _mean(i, i + span)
        if rise < min_absolute_rise:
            continue
        if window_noise > 0 and rise / window_noise < z_threshold:
            continue

        # The clapper goes back down. A stimulus background changing, a lamp
        # switched on, or auto-exposure settling all rise and STAY — and on a
        # real capture one of those scored as high as the flash did. Requiring
        # the level to fall back afterwards is what separates a 200ms pulse from
        # a new steady state, and it costs nothing because we know the flash
        # ends by construction.
        before = _mean(i - span, i)
        after = _mean(i + span, i + 2 * span)
        if before > rise * 0.5 or after > rise * 0.5:
            continue

        # A screen turning white is a STEP: on a real capture the leading edge
        # was 186.6 -> 193.4 between two consecutive frames, 82% of the total
        # rise in one frame interval. Auto-exposure settling and a participant
        # shifting in their seat produce the same size of bump spread over a
        # dozen frames — one such ramp scored as high as the true flash and was
        # otherwise indistinguishable. Edge sharpness is what tells them apart,
        # and it is the one property a screen flash cannot fail to have.
        edge_lo = max(1, i - 1)
        edge_hi = min(n, i + span)
        edge_steps = [
            (detrended[k] - detrended[k - 1], k) for k in range(edge_lo, edge_hi)
        ]
        if not edge_steps:
            continue
        best_step, onset_idx = max(edge_steps)
        if best_step < rise * min_edge_fraction:
            continue

        # Report the first bright frame, not the window start. The matched
        # filter is indifferent to where inside the plateau its window sits, so
        # using the window start smears the anchor by a frame or two — and the
        # anchor is the entire point.
        score = rise / window_noise if window_noise > 0 else float("inf")
        candidates.append(
            (ts[onset_idx], max(frame_interval, MIN_UNCERTAINTY_MS), score)
        )

    if not candidates:
        return []

    # Collapse overlapping windows: one flash produces a run of passing starts,
    # and they are the same event, not several.
    candidates.sort(key=lambda c: c[0])
    merged: list[tuple[float, float, float]] = []
    for c in candidates:
        if merged and c[0] - merged[-1][0] < flash_duration_ms * 2:
            if c[2] > merged[-1][2]:
                merged[-1] = c
        else:
            merged.append(c)

    merged.sort(key=lambda c: c[2], reverse=True)
    return merged


def detect_clapper_in_luma(
    luma_by_ts: list[tuple[float, float]],
    **kwargs,
) -> tuple[float, float] | None:
    """Strongest sync-clapper flash, or None.

    ``None`` is a real outcome, not a failure: the caller then has no anchor and
    must leave the stream unaligned rather than invent an offset.
    """
    found = detect_clappers_in_luma(luma_by_ts, **kwargs)
    if not found:
        return None
    ts, uncertainty, _score = found[0]
    return ts, uncertainty

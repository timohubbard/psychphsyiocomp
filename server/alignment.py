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


def detect_clapper_in_luma(
    luma_by_ts: list[tuple[float, float]],
    *,
    z_threshold: float = 4.0,
    min_absolute_rise: float = 15.0,
    min_samples: int = 10,
) -> tuple[float, float] | None:
    """Find a sync-clapper flash in a luminance time series.

    The capture page flashes the screen white at a known ``performance.now()``.
    That flash reflects off the participant's face and raises frame luminance
    sharply, giving a coincidence observable on both clocks — the browser knows
    when it drew the flash, the video shows when it arrived.

    Returns ``(native_ts_of_peak, uncertainty_ms)`` or ``None`` if no flash
    stands out. Returning ``None`` is a real outcome, not a failure: the
    caller then has no anchor and must leave the stream unaligned rather than
    invent an offset.

    A candidate must clear BOTH criteria: statistically prominent against the
    session's own noise, and absolutely prominent in luma terms. Requiring both
    is what separates a real flash from a lamp being nudged, and it keeps the
    detector working on a clean signal — with a near-noiseless baseline the
    robust deviation collapses toward zero, which would otherwise make the
    easiest possible input undetectable.

    :param luma_by_ts: ``(native_ts_ms, mean_luma)`` in ascending time order
    :param z_threshold: robust standard deviations above the median required
    :param min_absolute_rise: minimum rise over the median, in luma levels
    """
    if len(luma_by_ts) < min_samples:
        return None

    values = [v for _, v in luma_by_ts]
    median = sorted(values)[len(values) // 2]

    # Median absolute deviation — robust to the flash itself, which a plain
    # standard deviation would be inflated by.
    deviations = sorted(abs(v - median) for v in values)
    mad = deviations[len(deviations) // 2]
    robust_sd = mad * 1.4826

    peak_ts, peak_value = None, -math.inf
    for ts, v in luma_by_ts:
        if v > peak_value:
            peak_ts, peak_value = ts, v

    if peak_ts is None:
        return None

    rise = peak_value - median
    if rise < min_absolute_rise:
        return None

    # With a noiseless baseline the z-score is unbounded (or undefined); the
    # absolute-rise test above already carried the decision, so only apply the
    # statistical test when there is actual noise to measure against.
    if robust_sd > 0:
        if rise / robust_sd < z_threshold:
            return None

    # Uncertainty is one frame interval: we cannot localise the flash more
    # precisely than the sampling grid it was observed on.
    intervals = [
        b[0] - a[0] for a, b in zip(luma_by_ts, luma_by_ts[1:]) if b[0] > a[0]
    ]
    frame_interval = (
        sorted(intervals)[len(intervals) // 2] if intervals else SINGLE_ANCHOR_UNCERTAINTY_MS
    )
    return peak_ts, max(frame_interval, MIN_UNCERTAINTY_MS)

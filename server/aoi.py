"""Areas of interest, and the metrics computed over them.

Two findings shape every decision in this file.

**AOI hit rates are a property of the boundaries, not only of the tracker.**
§4.2 records one tool's hit-rate metric moving 77% -> 88% -> 93% purely from
iteratively refining the *same* AOI definitions on the *same* gaze data. That
is a larger swing than most effects anyone would report. So an AOI set carries
a version and a content hash, every metric is returned with the definition that
produced it, and nothing here will compute a hit rate without being able to say
which boundaries it used.

**Pixel-tight boxes are wrong.** §4.2 says to pad AOIs to the measured spatial
error budget (~3-4.5 deg), because a fixation estimated one degree off a button
was still a fixation on that button. Padding is therefore mandatory and
explicit: `pad_deg` has no default, and the padded geometry is reported back.

Metric names follow Holmqvist et al.'s taxonomy, which §4.1 is emphatic treats
these as *distinct, separately-operationalised constructs* rather than synonyms:
"first fixation duration in an AOI", "dwell time", "total dwell time" and
"first/second-pass dwell time" are four different measures, and "entry time" is
a fifth thing again. They are named apart here for that reason.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal, Sequence

Shape = Literal["rect", "circle", "polygon"]


@dataclass(frozen=True)
class AOI:
    """One area of interest, in normalised screen coordinates (0..1).

    Normalised rather than pixels so a definition survives a participant with a
    different display, which is the ordinary case in remote collection.
    """

    aoi_id: str
    shape: Shape
    #: rect: (x0, y0, x1, y1) · circle: (cx, cy, r) · polygon: flat x,y pairs
    coords: tuple[float, ...]
    label: str | None = None

    def __post_init__(self) -> None:
        n = len(self.coords)
        if self.shape == "rect" and n != 4:
            raise ValueError(f"rect needs 4 coords, got {n}")
        if self.shape == "circle" and n != 3:
            raise ValueError(f"circle needs 3 coords, got {n}")
        if self.shape == "polygon" and (n < 6 or n % 2):
            raise ValueError(f"polygon needs >=3 xy pairs, got {n} coords")


@dataclass(frozen=True)
class AOISet:
    """A named, versioned collection of AOIs.

    The version is not decoration. §4.2's 77/88/93 finding means a hit rate is
    only interpretable alongside the boundaries that produced it, and a set that
    can be edited without its identity changing makes two runs silently
    incomparable. `content_hash` is derived from the geometry, so editing a
    boundary changes the hash whether or not anyone remembers to bump `version`.
    """

    name: str
    version: str
    aois: tuple[AOI, ...]
    #: None: the AOIs are in normalised SCREEN (stage) coordinates, as every
    #: set was before stimuli existed. Set: they are fractions of that
    #: stimulus's own image, and are placed on a session's screen through the
    #: `rect_norm` its `stimulus` event recorded — see `to_stage`. Drawn once
    #: on the picture, they then follow it wherever a participant's display put
    #: it, which is what makes them comparable across displays.
    stimulus_id: str | None = None

    def content_hash(self) -> str:
        geometry = [[a.aoi_id, a.shape, list(a.coords)]
                    for a in sorted(self.aois, key=lambda a: a.aoi_id)]
        # The stimulus is part of the identity — the same boxes on a different
        # picture are a different question — but only when set, so every set
        # saved before stimuli existed keeps the hash its results recorded.
        payload = json.dumps(
            geometry if self.stimulus_id is None
            else {"stimulus_id": self.stimulus_id, "aois": geometry},
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def provenance(self) -> dict[str, Any]:
        """What must travel with any metric computed from this set."""
        out = {
            "aoi_set": self.name,
            "aoi_version": self.version,
            "aoi_content_hash": self.content_hash(),
            "n_aois": len(self.aois),
        }
        if self.stimulus_id is not None:
            out["stimulus_id"] = self.stimulus_id
        return out


def to_stage(aoi: AOI, rect_norm: dict[str, float]) -> AOI:
    """Map a stimulus-space AOI onto the stage, where this stimulus was shown.

    `rect_norm` is the stimulus's box in stage fractions ({x0, y0, x1, y1}),
    recorded in its `stimulus` event. A circle's radius is a fraction of the
    stimulus WIDTH, and becomes a fraction of the stage width — the axis the
    screen-space hit test measures radii against.
    """
    x0, y0 = rect_norm["x0"], rect_norm["y0"]
    sx, sy = rect_norm["x1"] - x0, rect_norm["y1"] - y0
    if sx <= 0 or sy <= 0:
        raise ValueError(f"degenerate stimulus rect {rect_norm}")
    c = aoi.coords
    if aoi.shape == "circle":
        coords = (x0 + c[0] * sx, y0 + c[1] * sy, c[2] * sx)
    else:
        coords = tuple(x0 + v * sx if i % 2 == 0 else y0 + v * sy for i, v in enumerate(c))
    return AOI(aoi_id=aoi.aoi_id, shape=aoi.shape, coords=coords, label=aoi.label)


# ---------------------------------------------------------------------------
# padding and hit testing
# ---------------------------------------------------------------------------

def pad_fraction(pad_deg: float, degrees_per_px: float, extent_px: float) -> float:
    """Convert an angular padding budget into a fraction of one screen axis."""
    if degrees_per_px is None or degrees_per_px <= 0:
        raise ValueError("padding needs degrees_per_px from the chinrest")
    return (pad_deg / degrees_per_px) / extent_px


def hit(
    x: float, y: float, aoi: AOI, *,
    pad_x: float = 0.0, pad_y: float = 0.0,
) -> bool:
    """Is this point inside the AOI, once padded?

    Padding is applied to the SHAPE rather than by testing a disc around the
    point, because the two differ at corners and the shape version is the one
    §4.2 describes. A rect padded by d is a rect grown by d on every side.
    """
    if aoi.shape == "rect":
        x0, y0, x1, y1 = aoi.coords
        lo_x, hi_x = min(x0, x1) - pad_x, max(x0, x1) + pad_x
        lo_y, hi_y = min(y0, y1) - pad_y, max(y0, y1) + pad_y
        return lo_x <= x <= hi_x and lo_y <= y <= hi_y

    if aoi.shape == "circle":
        cx, cy, r = aoi.coords
        # Anisotropic padding on a circle would make it an ellipse; the mean is
        # the honest scalar when the two axes disagree, and they only disagree
        # because the screen is not square.
        rr = r + (pad_x + pad_y) / 2.0
        return ((x - cx) ** 2 + (y - cy) ** 2) <= rr * rr

    return _point_in_polygon(x, y, aoi.coords, pad_x, pad_y)


def _point_in_polygon(x: float, y: float, coords: Sequence[float],
                      pad_x: float, pad_y: float) -> bool:
    """Ray casting, with padding applied by scaling about the centroid.

    Scaling is an approximation to a true offset polygon. It is right for
    convex shapes and close enough for the near-convex ones AOIs actually are;
    a correct Minkowski offset would need a polygon-clipping dependency, and
    §4.2's point is that padding must exist and be *reported*, not that it must
    be exact to the pixel.
    """
    pts = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]

    if pad_x or pad_y:
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        span_x = max(abs(p[0] - cx) for p in pts) or 1e-9
        span_y = max(abs(p[1] - cy) for p in pts) or 1e-9
        sx, sy = 1.0 + pad_x / span_x, 1.0 + pad_y / span_y
        pts = [(cx + (px - cx) * sx, cy + (py - cy) * sy) for px, py in pts]

    inside = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            t = (y - y0) / (y1 - y0)
            if x < x0 + t * (x1 - x0):
                inside = not inside
    return inside


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------

@dataclass
class AOIMetrics:
    """Holmqvist-taxonomy measures for one AOI.

    Deliberately not collapsed into a single "attention" number. §4.1 treats
    these as distinct constructs, and a composite would hide which one a result
    actually rests on.
    """

    aoi_id: str
    n_fixations: int = 0
    #: A dwell is one uninterrupted run of fixations inside the AOI. Distinct
    #: from fixation count: four fixations in one visit is one dwell.
    n_dwells: int = 0
    total_dwell_ms: float = 0.0
    first_fixation_duration_ms: float | None = None
    #: Latency from the start of the analysis window to the first fixation here.
    #: None when the AOI was never entered — which is a finding, not a zero.
    entry_time_ms: float | None = None
    first_pass_dwell_ms: float | None = None
    second_pass_dwell_ms: float | None = None


@dataclass
class AOIResult:
    metrics: dict[str, AOIMetrics] = field(default_factory=dict)
    #: Fraction of fixations landing in at least one AOI. The §4.2 number.
    hit_rate: float = 0.0
    n_fixations: int = 0
    n_hits: int = 0
    pad_deg: float = 0.0
    pad_x: float = 0.0
    pad_y: float = 0.0
    provenance: dict[str, Any] = field(default_factory=dict)
    refusal: str | None = None


def analyse(
    fixations: Iterable[Any],
    aoi_set: AOISet,
    *,
    pad_deg: float,
    degrees_per_px: float | None,
    viewport_px: tuple[float, float],
    window_start_ms: float | None = None,
) -> AOIResult:
    """Compute AOI metrics over a sequence of fixations.

    ``fixations`` are objects with ``x``, ``y``, ``onset_ts``, ``offset_ts`` —
    the events `fixations.classify` produces.

    Refuses without geometry rather than padding in pixels. A pixel pad means a
    different angular tolerance for every participant, so hit rates computed
    that way are not comparable across a study — and comparison is the only
    reason to compute them.

    Overlapping AOIs each get credit for the same fixation. That is deliberate
    and is why per-AOI dwell times can sum to more than the session: assigning a
    fixation to one "winning" AOI would bury the overlap, and a researcher who
    has drawn overlapping regions usually meant them to nest.
    """
    if degrees_per_px is None or degrees_per_px <= 0:
        return AOIResult(refusal="no_geometry", provenance=aoi_set.provenance())
    if pad_deg < 0:
        raise ValueError("pad_deg must not be negative")

    w, h = viewport_px
    pad_x = pad_fraction(pad_deg, degrees_per_px, w)
    pad_y = pad_fraction(pad_deg, degrees_per_px, h)

    fixations = [f for f in fixations
                 if getattr(f, "kind", "fixation") == "fixation"
                 and f.x is not None and f.y is not None]
    if not fixations:
        return AOIResult(refusal="no_fixations", provenance=aoi_set.provenance(),
                         pad_deg=pad_deg, pad_x=pad_x, pad_y=pad_y)

    t0 = window_start_ms if window_start_ms is not None else fixations[0].onset_ts

    metrics = {a.aoi_id: AOIMetrics(aoi_id=a.aoi_id) for a in aoi_set.aois}
    in_dwell = {a.aoi_id: False for a in aoi_set.aois}
    dwell_start = {a.aoi_id: 0.0 for a in aoi_set.aois}
    passes: dict[str, list[float]] = {a.aoi_id: [] for a in aoi_set.aois}

    n_hits = 0
    for f in fixations:
        hit_any = False
        for a in aoi_set.aois:
            m = metrics[a.aoi_id]
            if hit(f.x, f.y, a, pad_x=pad_x, pad_y=pad_y):
                hit_any = True
                m.n_fixations += 1
                m.total_dwell_ms += f.offset_ts - f.onset_ts
                if m.first_fixation_duration_ms is None:
                    m.first_fixation_duration_ms = f.offset_ts - f.onset_ts
                    m.entry_time_ms = f.onset_ts - t0
                if not in_dwell[a.aoi_id]:
                    in_dwell[a.aoi_id] = True
                    dwell_start[a.aoi_id] = f.onset_ts
                    m.n_dwells += 1
            elif in_dwell[a.aoi_id]:
                in_dwell[a.aoi_id] = False
                passes[a.aoi_id].append(f.onset_ts - dwell_start[a.aoi_id])
        if hit_any:
            n_hits += 1

    # Close any dwell still open at the end of the trace.
    last = fixations[-1].offset_ts
    for aoi_id, open_ in in_dwell.items():
        if open_:
            passes[aoi_id].append(last - dwell_start[aoi_id])

    for aoi_id, runs in passes.items():
        if runs:
            metrics[aoi_id].first_pass_dwell_ms = runs[0]
        if len(runs) > 1:
            metrics[aoi_id].second_pass_dwell_ms = runs[1]

    return AOIResult(
        metrics=metrics,
        hit_rate=n_hits / len(fixations),
        n_fixations=len(fixations),
        n_hits=n_hits,
        pad_deg=pad_deg,
        pad_x=pad_x,
        pad_y=pad_y,
        provenance={**aoi_set.provenance(), "pad_deg": pad_deg},
    )


def from_calibration_grid(points: Sequence[Sequence[float]], radius: float = 0.05) -> AOISet:
    """An AOI set built from the calibration grid, for sanity checking.

    Useful precisely because the answer is known: a working pipeline should show
    fixations landing on the calibration targets that were on screen. It is a
    diagnostic, not a study design.
    """
    return AOISet(
        name="calibration_grid", version="1",
        aois=tuple(AOI(aoi_id=f"target_{i}", shape="circle",
                       coords=(float(p[0]), float(p[1]), radius),
                       label=f"calibration point {i}")
                   for i, p in enumerate(points)),
    )

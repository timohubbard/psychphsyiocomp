"""Inter-engine agreement, and within-participant relative proportions.

Both come from one §2.2 finding, which is the most consequential thing the
evidence base says about facial measurement:

    Engine choice alone swings data yield by ~20 points and expression counts by
    3-4x on IDENTICAL video. Valid-face-frame rate was 43% (iMotions/AFFDEX) vs
    62-63% (FaceReader/Py-Feat); Py-Feat detected expressions in 3-4x as many
    frames as the other two. Per-child agreement on happiness proportion between
    engines: **r = 0.37-0.75**.

Two instructions follow, and this module implements both.

**Never single-engine on facial.** That r = 0.37-0.75 spread is not a nuisance,
it is the free uncertainty estimate — the only empirical handle on how much of
a result is the face and how much is the detector. Running one engine does not
remove that uncertainty, it only removes your ability to see it. So when a
channel has one source, `agreement` returns an explicit
`single_source` verdict rather than an empty result, because "no disagreement
measured" and "no disagreement" are different claims and only one of them is
true.

**Report relative within-participant proportions, never absolute counts.** The
one constructive finding in that study: relative proportions were robust across
engines even where absolute counts were not. An AU intensity of 0.44 means
almost nothing on its own; that same participant's brow being more active during
condition A than condition B survives a change of detector.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

#: §2.2's measured between-engine agreement on the same recordings. Quoted
#: wherever an agreement figure is reported, so a reader has something to
#: compare against rather than an unanchored correlation.
PUBLISHED_INTER_ENGINE_R = (0.37, 0.75)

#: Below this spread, a channel did not move and its correlation is
#: uninformative rather than low.
#:
#: Measured on a real session: `blendshape.jawRight` correlated at r = 0.065
#: between two placements of the SAME engine on the SAME pixels, which looks
#: alarming until you see that its mean was 0.0003 and its sd 0.010 — the
#: participant never moved their jaw sideways. Both engines correctly reported
#: nothing, and correlating two near-zero noise series gives approximately zero.
#: Reporting that as disagreement would invent a measurement problem out of a
#: movement that never happened.
#:
#: Tuned for 0..1 intensity channels (blendshapes, AUs). A channel in other
#: units should pass its own floor.
MIN_INFORMATIVE_SD = 0.01


def comparison_kind(source_a: str, source_b: str) -> str:
    """What two sources actually differ in: 'placements', 'versions', 'engines'.

    This decides how a correlation should be READ, and getting it wrong is worse
    than not computing one. `engine@version+placement` run in two placements
    should agree very closely — the same model over the same pixels — so a low r
    there is a placement bug. Two different engines are the §2.2 case, where
    r = 0.37-0.75 was normal and the disagreement IS the uncertainty estimate.

    Measured on a real session, the same engine across browser-live and
    server-batch agreed at median r = 0.83. Presenting that against the
    inter-engine benchmark would read as unusually good agreement between
    engines, when no two engines were involved at all.
    """
    def parts(src: str) -> tuple[str, str, str]:
        engine, _, rest = src.partition("@")
        version, _, placement = rest.partition("+")
        return engine, version, placement

    ea, va, _ = parts(source_a)
    eb, vb, _ = parts(source_b)
    if ea != eb:
        return "engines"
    if va != vb:
        return "versions"
    return "placements"


@dataclass(frozen=True)
class Agreement:
    channel: str
    source_a: str
    source_b: str
    r: float | None
    n_overlapping: int
    #: 'ok' | 'single_source' | 'no_overlap' | 'degenerate'
    verdict: str
    detail: str | None = None
    #: 'placements' | 'versions' | 'engines' — how to read `r`. Only 'engines'
    #: is comparable against §2.2's published spread.
    kind: str = "engines"
    #: Each source's own spread. Reported because a correlation cannot be read
    #: without it — see the `low_variance` verdict.
    sd_a: float | None = None
    sd_b: float | None = None


def _series(rows: Iterable[dict[str, Any]], channel: str, source: str):
    pairs = sorted(
        (float(r["master_ts"]), float(r["value"]))
        for r in rows
        if r.get("channel") == channel and r.get("source") == source
        and r.get("master_ts") is not None and r.get("value") is not None
    )
    if not pairs:
        return np.empty(0), np.empty(0)
    ts, v = zip(*pairs)
    return np.array(ts), np.array(v)


def channel_agreement(
    rows: Sequence[dict[str, Any]], channel: str, source_a: str, source_b: str,
    *, min_overlap: int = 10, min_sd: float = MIN_INFORMATIVE_SD,
) -> Agreement:
    """Pearson r between two sources for one channel, on a common time grid.

    The denser series is resampled onto the sparser one's timestamps rather than
    onto a synthetic grid. Both engines already carry a master timestamp, and
    inventing a third grid would interpolate both of them — adding smoothing to
    the thing being measured, which is how a disagreement quietly becomes an
    agreement.
    """
    ta, va = _series(rows, channel, source_a)
    tb, vb = _series(rows, channel, source_b)

    kind = comparison_kind(source_a, source_b)

    if len(ta) == 0 or len(tb) == 0:
        return Agreement(channel, source_a, source_b, None, 0, "no_overlap",
                         "one source produced nothing for this channel", kind)

    # Resample the denser onto the sparser.
    if len(ta) <= len(tb):
        grid, base, other_t, other_v = ta, va, tb, vb
    else:
        grid, base, other_t, other_v = tb, vb, ta, va

    lo, hi = max(ta[0], tb[0]), min(ta[-1], tb[-1])
    sel = (grid >= lo) & (grid <= hi)
    grid, base = grid[sel], base[sel]

    if len(grid) < min_overlap:
        return Agreement(channel, source_a, source_b, None, int(len(grid)),
                         "no_overlap", f"{len(grid)} overlapping samples", kind)

    resampled = np.interp(grid, other_t, other_v)
    sd_a, sd_b = float(np.std(base)), float(np.std(resampled))

    # A constant series has no variance, so correlation is undefined rather than
    # zero. AU20 does this in practice: the detector emits a flat 0.0.
    if sd_a < 1e-12 or sd_b < 1e-12:
        return Agreement(channel, source_a, source_b, None, int(len(grid)),
                         "degenerate",
                         "one source is constant; correlation is undefined, not zero",
                         kind, sd_a, sd_b)

    # Barely moved is not the same as disagreed. Both sources can be correct and
    # still correlate at zero if what they are correlating is noise around a
    # value that never changed.
    if max(sd_a, sd_b) < min_sd:
        return Agreement(channel, source_a, source_b, None, int(len(grid)),
                         "low_variance",
                         f"sd {max(sd_a, sd_b):.4f} < {min_sd} — this channel barely "
                         "moved, so a correlation measures noise against noise. Not "
                         "a disagreement: nothing happened to agree about.",
                         kind, sd_a, sd_b)

    r = float(np.corrcoef(base, resampled)[0, 1])
    return Agreement(channel, source_a, source_b, r, int(len(grid)), "ok",
                     None, kind, sd_a, sd_b)


def agreement_for_channel(
    rows: Sequence[dict[str, Any]], channel: str,
) -> list[Agreement]:
    """Every source pair for one channel, or an explicit single-source verdict.

    Returning a verdict rather than an empty list is the point. §2.2's whole
    warning is that a single engine's output looks exactly as confident as a
    corroborated one, and an empty result reads as "nothing to report".
    """
    sources = sorted({r["source"] for r in rows if r.get("channel") == channel})

    if len(sources) < 2:
        only = sources[0] if sources else "none"
        return [Agreement(
            channel, only, only, None, 0, "single_source",
            "one engine only — the inter-engine spread §2.2 measured at "
            f"r={PUBLISHED_INTER_ENGINE_R[0]}-{PUBLISHED_INTER_ENGINE_R[1]} is "
            "the uncertainty estimate, and it is unavailable here. Not measuring "
            "the disagreement does not remove it.",
            "engines",
        )]

    out: list[Agreement] = []
    for i, a in enumerate(sources):
        for b in sources[i + 1:]:
            out.append(channel_agreement(rows, channel, a, b))
    return out


def summarise(agreements: Sequence[Agreement]) -> dict[str, Any]:
    """Headline figures across many channels, for a session summary."""
    ok = [a for a in agreements if a.verdict == "ok" and a.r is not None]

    # Split by kind. Pooling a placement comparison with an engine comparison
    # would produce a median that answers neither question, and the published
    # benchmark only applies to one of them.
    def stats(subset):
        vals = [a.r for a in subset]
        return {
            "n": len(vals),
            "median_r": float(np.median(vals)) if vals else None,
            "min_r": float(np.min(vals)) if vals else None,
        }

    return {
        "n_channels": len({a.channel for a in agreements}),
        "n_measured": len(ok),
        "n_single_source": sum(1 for a in agreements if a.verdict == "single_source"),
        "n_degenerate": sum(1 for a in agreements if a.verdict == "degenerate"),
        "n_low_variance": sum(1 for a in agreements if a.verdict == "low_variance"),
        "between_engines": stats([a for a in ok if a.kind == "engines"]),
        "between_placements": stats([a for a in ok if a.kind == "placements"]),
        "between_versions": stats([a for a in ok if a.kind == "versions"]),
        # Applies to `between_engines` ONLY.
        "published_range": PUBLISHED_INTER_ENGINE_R,
    }


# ---------------------------------------------------------------------------
# relative, within-participant proportions
# ---------------------------------------------------------------------------

def relative_proportion(values: Sequence[float]) -> np.ndarray:
    """Each value's percentile rank within this participant's own distribution.

    §2.2's one constructive finding: relative within-participant proportions
    were robust across engines even where absolute counts were not. An AU
    intensity of 0.44 means almost nothing by itself — different detectors put
    the same face at different absolute levels — but "this participant's brow
    was in the top decile of its own range here" survives a change of detector.

    Percentile rank rather than a z-score or min-max, because AU intensity
    distributions are heavily skewed and often zero-inflated. A z-score would
    imply a symmetry that is not there; min-max would hand the entire scale to
    whichever single frame happened to be the most extreme.
    """
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return np.empty(0)

    order = np.argsort(v, kind="stable")
    ranks = np.empty(len(v), dtype=float)
    ranks[order] = np.arange(len(v), dtype=float)

    # Ties share the mean rank, so a flat channel maps to a constant 0.5 rather
    # than to an arbitrary ordering of identical values.
    unique, inverse, counts = np.unique(v, return_inverse=True, return_counts=True)
    if len(unique) < len(v):
        sums = np.zeros(len(unique))
        np.add.at(sums, inverse, ranks)
        ranks = (sums / counts)[inverse]

    return ranks / max(len(v) - 1, 1) if len(v) > 1 else np.full(1, 0.5)


def condition_contrast(
    values_a: Sequence[float], values_b: Sequence[float],
) -> dict[str, Any]:
    """Compare one participant's channel between two conditions.

    This is the shape §2.2 says results should take: a within-participant,
    relative, condition-contrast claim ("more brow-furrow during X than Y"),
    never an absolute state claim ("this participant felt happy").

    Reports the difference in median relative rank, which is unit-free and
    therefore comparable across detectors, plus the raw medians for anyone who
    needs them.
    """
    a = np.asarray(values_a, dtype=float)
    b = np.asarray(values_b, dtype=float)
    if len(a) == 0 or len(b) == 0:
        return {"comparable": False, "reason": "a condition has no samples"}

    pooled = relative_proportion(np.concatenate([a, b]))
    rel_a, rel_b = pooled[:len(a)], pooled[len(a):]

    return {
        "comparable": True,
        "relative_median_a": float(np.median(rel_a)),
        "relative_median_b": float(np.median(rel_b)),
        "relative_difference": float(np.median(rel_a) - np.median(rel_b)),
        "absolute_median_a": float(np.median(a)),
        "absolute_median_b": float(np.median(b)),
        "n_a": int(len(a)),
        "n_b": int(len(b)),
    }

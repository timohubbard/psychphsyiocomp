"""Inferential statistics for a cohort: declared contrasts between two arms.

Nothing here is chosen after the data is seen. A contrast is declared in the
study's analysis plan (analysis.contrasts, hashed by cohort.analysis_hash) with
its epoch set, channel, the two arms, the window, the number of permutations and
the seed. Every random step is drawn from that seed, so the same plan on the
same data gives the same numbers to the last digit.

**Participants, not epochs, are the unit.** A person who contributed ten epochs
is still one person. Averaging epochs first would let whoever sat longest
dominate the result, and would treat the ten as independent evidence when they
are one person's repeated responses. So each participant's epochs are averaged
into one curve, and the tests run on those curves. (REPORT.md §4.4; the random-
effects debate there is why a mixed model is exported as an R script rather
than guessed at here — see export.py.)

**Two tests, both by permutation.**

- *Window test.* Each participant's mean over the declared window; the
  difference in arm means; a p-value by permuting arm labels (exact
  enumeration when the number of arrangements is within the permutation
  budget); a bootstrap CI within each arm; Hedges' g. Holm-corrected across
  every contrast in the plan, because a plan with five contrasts has five
  chances.
- *Cluster-based permutation over time* (Maris & Oostenveld 2007). A Welch t
  at every time point, thresholded; contiguous supra-threshold runs of one sign
  form clusters, scored by their summed t; the null is the largest cluster mass
  under permuted labels. This controls the family-wise error across the whole
  time course without assuming where the effect is. The p-value belongs to a
  cluster, not to its edges: "the arms differ, and this is where the
  difference is largest" — not "the effect starts at 312 ms".

**Refusals, not small numbers.** Fewer than 3 participants in an arm is
refused. So is a design where even a perfect separation could not reach alpha
(two arms of 3 give 20 arrangements, so the smallest two-sided p is 0.10): that
is `underpowered_by_construction`, derived from the arithmetic of permutation
tests rather than from a guessed sample size.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

import numpy as np

MIN_PER_ARM = 3
BOOTSTRAP_BANDS = 1000          # pointwise bands for display only
ANONYMOUS = ("anonymous", None, "")


# ---------------------------------------------------------------------------
# participants first
# ---------------------------------------------------------------------------

def participant_key(row: dict[str, Any]) -> str:
    """Who a row belongs to. Self-tests share the participant id 'anonymous'
    without being one person, so each of those sessions counts as its own unit."""
    pid = row.get("participant_id")
    return f"session:{row['session_id']}" if pid in ANONYMOUS else str(pid)


@dataclass
class ParticipantCurves:
    grid: np.ndarray                         # t_ms
    by_participant: dict[str, np.ndarray]    # NaN where that participant has no value
    arm: dict[str, str | None]
    n_epochs: dict[str, int]
    refusals: list[dict[str, Any]] = field(default_factory=list)


def participant_curves(rows: Iterable[dict[str, Any]], channel: str) -> ParticipantCurves:
    """Each participant's mean baseline-corrected curve for one channel.

    A participant recorded in two arms is refused: between-subject arms are
    the design, and a person in both would be counted as evidence for each.
    """
    rows = [r for r in rows if r["channel"] == channel]
    grid = np.array(sorted({r["t_ms"] for r in rows}), dtype=float)
    col = {t: i for i, t in enumerate(grid)}
    acc: dict[str, dict[tuple[str, int], np.ndarray]] = {}
    arms: dict[str, set] = {}
    for r in rows:
        p = participant_key(r)
        key = (r["session_id"], r["epoch"])
        acc.setdefault(p, {}).setdefault(key, np.full(len(grid), np.nan))[col[r["t_ms"]]] = r["value_bc"]
        arms.setdefault(p, set()).add(r.get("condition"))
    out = ParticipantCurves(grid, {}, {}, {})
    for p, ep in acc.items():
        if len(arms[p]) > 1:
            out.refusals.append({"participant": p, "reason": "mixed_arm_participant",
                                 "detail": f"recorded in {sorted(map(str, arms[p]))}"})
            continue
        stack = np.vstack(list(ep.values()))
        with np.errstate(all="ignore"):
            out.by_participant[p] = np.nanmean(stack, axis=0)
        out.arm[p] = next(iter(arms[p]))
        out.n_epochs[p] = len(ep)
    return out


def pooled_mean(curves: ParticipantCurves) -> list[dict[str, float]]:
    """Mean of participant means at each time point, with how many contributed."""
    if not curves.by_participant:
        return []
    m = np.vstack(list(curves.by_participant.values()))
    n = np.sum(~np.isnan(m), axis=0)
    with np.errstate(all="ignore"):
        mean = np.nanmean(m, axis=0)
    return [{"t_ms": float(t), "mean": float(v), "n": int(k)}
            for t, v, k in zip(curves.grid, mean, n) if k > 0]


# ---------------------------------------------------------------------------
# the window test
# ---------------------------------------------------------------------------

def hedges_g(a: np.ndarray, b: np.ndarray) -> float:
    """Standardised difference with the small-sample correction J."""
    n1, n2 = len(a), len(b)
    sp2 = ((n1 - 1) * np.var(a, ddof=1) + (n2 - 1) * np.var(b, ddof=1)) / (n1 + n2 - 2)
    if sp2 <= 0:
        return float("nan")
    d = (np.mean(a) - np.mean(b)) / math.sqrt(sp2)
    return float(d * (1 - 3 / (4 * (n1 + n2) - 9)))


def _tail_stat(x: np.ndarray, tail: str) -> np.ndarray:
    return np.abs(x) if tail == "two" else (x if tail == "greater" else -x)


def label_permutations(n1: int, n2: int, n_permutations: int, rng: np.random.Generator):
    """Index sets for arm A under the null. Exact when there are few enough.

    Returns (list of index arrays, exact). The exact list includes the
    observed labelling, so p = share of arrangements at least as extreme.
    """
    n = n1 + n2
    total = math.comb(n, n1)
    if total <= n_permutations:
        return [np.array(c) for c in itertools.combinations(range(n), n1)], True
    return [rng.permutation(n)[:n1] for _ in range(n_permutations)], False


def permutation_p(values: np.ndarray, n1: int, observed: float, perms, exact: bool, tail: str) -> float:
    stats = np.array([values[idx].mean() - np.delete(values, idx).mean() for idx in perms])
    extreme = np.sum(_tail_stat(stats, tail) >= _tail_stat(np.array(observed), tail) - 1e-12)
    return float(extreme / len(perms)) if exact else float((extreme + 1) / (len(perms) + 1))


def bootstrap_diff_ci(a: np.ndarray, b: np.ndarray, alpha: float, n: int,
                      rng: np.random.Generator) -> tuple[float, float]:
    """Percentile CI of mean(a) - mean(b), resampling within each arm."""
    ia = rng.integers(0, len(a), (n, len(a)))
    ib = rng.integers(0, len(b), (n, len(b)))
    diffs = a[ia].mean(axis=1) - b[ib].mean(axis=1)
    return float(np.quantile(diffs, alpha / 2)), float(np.quantile(diffs, 1 - alpha / 2))


def smallest_possible_p(n1: int, n2: int, tail: str) -> float:
    return (2 if tail == "two" else 1) / math.comb(n1 + n2, n1)


def holm(pvalues: list[float | None]) -> list[float | None]:
    """Holm step-down adjustment; None stays None and is not counted."""
    idx = [i for i, p in enumerate(pvalues) if p is not None]
    order = sorted(idx, key=lambda i: pvalues[i])
    m, out, running = len(order), list(pvalues), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        out[i] = running
    return out


# ---------------------------------------------------------------------------
# cluster-based permutation over time
# ---------------------------------------------------------------------------

def welch_t(A: np.ndarray, B: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Welch t and df per column, NaN-aware (a participant may lack a time point)."""
    with np.errstate(all="ignore"):
        na, nb = np.sum(~np.isnan(A), axis=0), np.sum(~np.isnan(B), axis=0)
        ma, mb = np.nanmean(A, axis=0), np.nanmean(B, axis=0)
        va, vb = np.nanvar(A, axis=0, ddof=1), np.nanvar(B, axis=0, ddof=1)
        se2 = va / na + vb / nb
        t = (ma - mb) / np.sqrt(se2)
        df = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return t, df


def clusters_of(t: np.ndarray, thresh: np.ndarray, usable: np.ndarray, tail: str) -> list[tuple[int, int, float]]:
    """(start, end inclusive, mass) of contiguous supra-threshold runs of one sign.

    A time point that could not be tested (too few participants) breaks a run:
    a cluster is contiguous evidence, not two stretches joined across a gap.
    """
    out, i, n = [], 0, len(t)
    signs = [1, -1] if tail == "two" else ([1] if tail == "greater" else [-1])
    for sign in signs:
        i = 0
        while i < n:
            if usable[i] and sign * t[i] > thresh[i]:
                j = i
                while j + 1 < n and usable[j + 1] and sign * t[j + 1] > thresh[j + 1]:
                    j += 1
                out.append((i, j, float(np.sum(t[i:j + 1]))))
                i = j + 1
            else:
                i += 1
    return out


def cluster_test(M: np.ndarray, is_a: np.ndarray, *, p_threshold: float, tail: str, perms, exact: bool):
    """M: participants x time. Returns (clusters with p, threshold per point, usable mask)."""
    from scipy.stats import t as tdist

    A, B = M[is_a], M[~is_a]
    usable = (np.sum(~np.isnan(A), axis=0) >= MIN_PER_ARM) & (np.sum(~np.isnan(B), axis=0) >= MIN_PER_ARM)
    t, df = welch_t(A, B)
    q = 1 - (p_threshold / 2 if tail == "two" else p_threshold)
    thresh = np.where(usable, tdist.ppf(q, np.where(np.isfinite(df), df, 1)), np.inf)
    observed = clusters_of(t, thresh, usable, tail)

    null = []
    n = len(M)
    for idx in perms:
        mask = np.zeros(n, bool)
        mask[idx] = True
        tp, _ = welch_t(M[mask], M[~mask])
        masses = [abs(m) if tail == "two" else (m if tail == "greater" else -m)
                  for _, _, m in clusters_of(tp, thresh, usable, tail)]
        null.append(max(masses, default=0.0))
    null = np.array(null)
    found = []
    for s, e, mass in observed:
        stat = abs(mass) if tail == "two" else (mass if tail == "greater" else -mass)
        k = int(np.sum(null >= stat - 1e-12))
        p = k / len(null) if exact else (k + 1) / (len(null) + 1)
        found.append({"start_index": s, "end_index": e, "mass": mass, "p": float(p),
                      "sign": "a>b" if mass > 0 else "a<b"})
    return found, thresh, usable


# ---------------------------------------------------------------------------
# one declared contrast
# ---------------------------------------------------------------------------

def band(M: np.ndarray, alpha: float, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pointwise mean and bootstrap percentile band (uncorrected — for display)."""
    with np.errstate(all="ignore"):
        mean = np.nanmean(M, axis=0)
        idx = rng.integers(0, len(M), (BOOTSTRAP_BANDS, len(M)))
        boots = np.nanmean(M[idx], axis=1)
        lo = np.nanquantile(boots, alpha / 2, axis=0)
        hi = np.nanquantile(boots, 1 - alpha / 2, axis=0)
    return mean, lo, hi


def run_contrast(contrast: dict[str, Any], curves: ParticipantCurves) -> dict[str, Any]:
    """Everything one declared contrast produces, or a refusal saying why not."""
    a_arm, b_arm = contrast["arms"]
    alpha = float(contrast.get("alpha", 0.05))
    tail = contrast.get("tail", "two")
    n_perm = int(contrast["n_permutations"])
    seed = int(contrast["seed"])
    base = {"name": contrast["name"], "epochs": contrast["epochs"], "channel": contrast["channel"],
            "arms": [a_arm, b_arm], "window_ms": list(contrast["window_ms"]), "alpha": alpha,
            "tail": tail, "seed": seed, "n_permutations": n_perm,
            "participant_refusals": curves.refusals}

    ids = [p for p, arm in curves.arm.items() if arm in (a_arm, b_arm)]
    ids.sort(key=lambda p: (curves.arm[p] != a_arm, p))     # A first, stable order for the seed
    n = {a_arm: sum(curves.arm[p] == a_arm for p in ids), b_arm: sum(curves.arm[p] == b_arm for p in ids)}
    base["n"] = n
    if not any(curves.arm.values()):
        return {**base, "refusal": {"reason": "no_conditions",
                                    "detail": "no session records a condition; there is nothing to contrast"}}
    if min(n.values()) < MIN_PER_ARM:
        return {**base, "refusal": {"reason": "too_few_per_arm",
                                    "detail": f"{n[a_arm]} vs {n[b_arm]} participants; each arm needs {MIN_PER_ARM}"}}
    floor = smallest_possible_p(n[a_arm], n[b_arm], tail)
    if floor > alpha:
        return {**base, "refusal": {"reason": "underpowered_by_construction",
                                    "detail": f"with {n[a_arm]} and {n[b_arm]} participants the smallest "
                                              f"p a permutation test can return is {floor:.3f}, above alpha {alpha}"}}

    M = np.vstack([curves.by_participant[p] for p in ids])
    is_a = np.array([curves.arm[p] == a_arm for p in ids])
    rng = np.random.default_rng(seed)
    perms, exact = label_permutations(int(is_a.sum()), int((~is_a).sum()), n_perm, rng)

    # Window: each participant's mean over the window.
    lo_ms, hi_ms = contrast["window_ms"]
    inwin = (curves.grid >= lo_ms) & (curves.grid <= hi_ms)
    with np.errstate(all="ignore"):
        w = np.nanmean(M[:, inwin], axis=1)
    keep = ~np.isnan(w)
    wa, wb = w[keep & is_a], w[keep & ~is_a]
    window = None
    if min(len(wa), len(wb)) >= MIN_PER_ARM:
        vals = np.concatenate([wa, wb])
        diff = float(wa.mean() - wb.mean())
        wperms, wexact = (perms, exact) if keep.all() else label_permutations(len(wa), len(wb), n_perm, rng)
        window = {"mean_a": float(wa.mean()), "mean_b": float(wb.mean()), "diff": diff,
                  "ci": bootstrap_diff_ci(wa, wb, alpha, n_perm, rng),
                  "p": permutation_p(vals, len(wa), diff, wperms, wexact, tail),
                  "hedges_g": hedges_g(wa, wb), "exact": wexact,
                  "arrangements": len(wperms), "n_a": len(wa), "n_b": len(wb)}

    cluster = None
    if contrast.get("cluster") is not None:
        found, thresh, usable = cluster_test(M, is_a, p_threshold=float(contrast["cluster"].get("p_threshold", 0.05)),
                                             tail=tail, perms=perms, exact=exact)
        cluster = {
            "p_threshold": float(contrast["cluster"].get("p_threshold", 0.05)),
            "clusters": [{**c, "start_ms": float(curves.grid[c["start_index"]]),
                          "end_ms": float(curves.grid[c["end_index"]]),
                          "significant": c["p"] <= alpha} for c in found],
            "untested_ms": [float(t) for t, u in zip(curves.grid, usable) if not u],
        }

    bands = {}
    for arm, sel in ((a_arm, is_a), (b_arm, ~is_a)):
        mean, lo, hi = band(M[sel], alpha, rng)
        bands[arm] = {"t_ms": [float(t) for t in curves.grid], "mean": _clean(mean),
                      "lo": _clean(lo), "hi": _clean(hi)}

    return {**base, "window": window, "cluster": cluster, "curves": bands,
            "exact": exact, "arrangements": len(perms), "refusal": None}


def _clean(a: np.ndarray) -> list[float | None]:
    return [None if not np.isfinite(v) else float(v) for v in a]


def run_contrasts(plan: dict[str, Any], rows_by_set: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Every contrast in the plan, Holm-adjusted together across their window tests."""
    results = []
    for c in plan.get("contrasts") or []:
        curves = participant_curves(rows_by_set.get(c["epochs"], []), c["channel"])
        results.append(run_contrast(c, curves))
    adjusted = holm([r["window"]["p"] if r.get("window") else None for r in results])
    for r, p in zip(results, adjusted):
        if r.get("window"):
            r["window"]["p_holm"] = p
    return results


def as_rows(results: list[dict[str, Any]], analysis_hash: str) -> tuple[list[dict], list[dict]]:
    """Flat rows for contrasts.csv and clusters.csv, each stamped with the plan it came from."""
    contrasts, clusters = [], []
    for r in results:
        w = r.get("window") or {}
        contrasts.append({
            "contrast": r["name"], "epochs": r["epochs"], "channel": r["channel"],
            "arm_a": r["arms"][0], "arm_b": r["arms"][1],
            "n_a": r["n"].get(r["arms"][0]), "n_b": r["n"].get(r["arms"][1]),
            "window_ms": f"{r['window_ms'][0]}..{r['window_ms'][1]}", "tail": r["tail"],
            "mean_a": w.get("mean_a"), "mean_b": w.get("mean_b"), "diff": w.get("diff"),
            "ci_low": (w.get("ci") or [None, None])[0], "ci_high": (w.get("ci") or [None, None])[1],
            "hedges_g": w.get("hedges_g"), "p": w.get("p"), "p_holm": w.get("p_holm"),
            "exact": w.get("exact"), "arrangements": w.get("arrangements"),
            "alpha": r["alpha"], "seed": r["seed"], "n_permutations": r["n_permutations"],
            "refusal": (r.get("refusal") or {}).get("reason"),
            "refusal_detail": (r.get("refusal") or {}).get("detail"),
            "analysis_hash": analysis_hash,
        })
        for c in ((r.get("cluster") or {}).get("clusters") or []):
            clusters.append({"contrast": r["name"], "start_ms": c["start_ms"], "end_ms": c["end_ms"],
                             "mass": c["mass"], "p": c["p"], "significant": c["significant"],
                             "direction": c["sign"], "analysis_hash": analysis_hash,
                             "seed": r["seed"], "n_permutations": r["n_permutations"]})
    return contrasts, clusters


def participant_rows(curves: ParticipantCurves, epoch_set: str, channel: str) -> list[dict[str, Any]]:
    """The per-participant curves, long format — what every test above ran on."""
    out = []
    for p, v in curves.by_participant.items():
        for t, x in zip(curves.grid, v):
            if np.isfinite(x):
                out.append({"participant": p, "condition": curves.arm[p], "epoch_set": epoch_set,
                            "channel": channel, "t_ms": float(t), "value_bc": float(x),
                            "n_epochs": curves.n_epochs[p]})
    return out

"""Cohort analysis: which sessions count, why the others do not, and event-locked epochs.

Everything before this looked at one session at a time. A study is a cohort,
and the first cohort question is not "what is the effect" but "which sessions
are in, and why are the rest out" — REPORT.md §5.3 puts webcam attrition at
46–66%, most of it at exclusion, so the funnel IS a result.

Three rules, each a refusal rather than a guess:

**Only one protocol per cohort.** Sessions whose recorded content hash differs
from the study file on disk ran a different protocol (an edit, even a typo in
the disclosure) and are excluded with that reason unless `allow_mixed` is
asked for explicitly.

**Self-tests are not participants.** Sessions recorded with audience
`developer`, or with no audience recorded at all (the pilots), are left out
unless `include_developer` is asked for.

**A criterion nobody measured is not a criterion met.** Exclusions are
declared in the study (`analysis.exclusions`) so they are fixed before the
data is seen. A session whose metric was never measured — no validation
because gaze was refused, say — is excluded as `not_measured`, distinctly from
`failed`, and the funnel shows both.

Epochs are cut on the master clock only: an event or signal without a master
timestamp is a refusal row, never re-timed from its native clock. A channel
produced by more than one source must be told which one to use.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pyarrow.compute as pc

ROOT = Path(__file__).resolve().parents[1]
# Run as a script as well as imported: the same two paths process_bundle sets.
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

from study import content_hash, load_study  # noqa: E402
from tables import SESSIONS_SCHEMA, read_session  # noqa: E402
SESSION_COLUMNS = {f.name for f in SESSIONS_SCHEMA}


# ---------------------------------------------------------------------------
# who is in
# ---------------------------------------------------------------------------

@dataclass
class FunnelStep:
    label: str
    remaining: int
    excluded: list[tuple[str, str]] = field(default_factory=list)  # (session_id, reason)


@dataclass
class Cohort:
    study_id: str
    content_hash: str
    analysis_hash: str
    included: list[dict[str, Any]]
    funnel: list[FunnelStep]


def analysis_hash(study: dict[str, Any]) -> str:
    """The analysis plan's own identity. Kept OUT of the study content hash —
    changing an exclusion does not change what participants did — but stamped
    on every result so two analyses of one protocol stay distinguishable."""
    payload = json.dumps(study.get("analysis") or {}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def study_sessions(out: str | Path, study_id: str) -> list[dict[str, Any]]:
    rows = []
    for d in sorted(Path(out).glob("session_id=*")):
        try:
            t = read_session(out, d.name.split("=", 1)[1], "sessions")
        except FileNotFoundError:
            continue
        rows += [r for r in t.to_pylist() if r.get("study_id") == study_id]
    return rows


def session_metric(out: str | Path, row: dict[str, Any], metric: str) -> float | None:
    """A sessions-table column, or the median of that quality metric."""
    if metric in SESSION_COLUMNS:
        v = row.get(metric)
        return None if v is None else float(v)
    try:
        q = read_session(out, row["session_id"], "quality")
    except FileNotFoundError:
        return None
    vals = [r["value"] for r in q.filter(pc.equal(q["metric"], metric)).to_pylist()
            if r["value"] is not None and not math.isnan(r["value"])]
    return float(np.median(vals)) if vals else None


def select(out: str | Path, study: dict[str, Any], *, include_developer: bool = False,
           allow_mixed: bool = False) -> Cohort:
    """Apply the declared exclusions, in order, and keep the funnel."""
    sid = study["study_id"]
    current = content_hash(study)
    rows = study_sessions(out, sid)
    funnel = [FunnelStep(f"recorded under {sid}", len(rows))]

    def step(label, keep):
        nonlocal rows
        kept, gone = [], []
        for r in rows:
            reason = keep(r)
            (gone.append((r["session_id"], reason)) if reason else kept.append(r))
        rows = kept
        funnel.append(FunnelStep(label, len(rows), gone))

    if not include_developer:
        step("run on participants", lambda r: None if r.get("audience") == "participants"
             else f"audience {r.get('audience') or 'not recorded'}")
    if not allow_mixed:
        step(f"protocol matches studies/{sid}.json ({current})",
             lambda r: None if r.get("study_content_hash") == current
             else f"protocol {r.get('study_content_hash') or 'not recorded'}")

    for rule in (study.get("analysis") or {}).get("exclusions", []):
        metric, lo, hi = rule["metric"], rule.get("min"), rule.get("max")

        def keep(r, metric=metric, lo=lo, hi=hi):
            v = session_metric(out, r, metric)
            if v is None:
                return f"not_measured: {metric}"
            if lo is not None and v < lo:
                return f"failed: {metric} {v:.3g} < {lo}"
            if hi is not None and v > hi:
                return f"failed: {metric} {v:.3g} > {hi}"
            return None

        bounds = " and ".join(p for p in (f">= {lo}" if lo is not None else "",
                                          f"<= {hi}" if hi is not None else "") if p)
        step(f"{metric} {bounds}", keep)

    return Cohort(sid, current, analysis_hash(study), rows, funnel)


# ---------------------------------------------------------------------------
# epochs
# ---------------------------------------------------------------------------

@dataclass
class EpochSpec:
    name: str
    event_type: str
    channels: list[str]
    pre_ms: float
    post_ms: float
    baseline_ms: tuple[float, float] | None = (-200.0, 0.0)
    resample_hz: float = 30.0
    source: str | None = None
    stimulus_id: str | None = None
    #: Two samples further apart than this are not interpolated across.
    max_gap_ms: float = 250.0
    #: An epoch with less of its grid covered than this is refused.
    min_coverage: float = 0.5

    @classmethod
    def from_study(cls, d: dict[str, Any]) -> "EpochSpec":
        b = d.get("baseline_ms", [-200, 0])
        return cls(name=d["name"], event_type=d["event_type"], channels=list(d["channels"]),
                   pre_ms=float(d["pre_ms"]), post_ms=float(d["post_ms"]),
                   baseline_ms=None if b is None else (float(b[0]), float(b[1])),
                   resample_hz=float(d.get("resample_hz", 30)), source=d.get("source"),
                   stimulus_id=d.get("stimulus_id"))


def _series(signals, source, channel):
    t = signals.filter(pc.and_(pc.equal(signals["channel"], channel),
                               pc.equal(signals["source"], source)))
    ts = np.asarray(t["master_ts"].to_pylist(), dtype=float)
    vs = np.asarray(t["value"].to_pylist(), dtype=float)
    ok = ~(np.isnan(ts) | np.isnan(vs))
    order = np.argsort(ts[ok])
    return ts[ok][order], vs[ok][order]


def resample(ts: np.ndarray, vs: np.ndarray, grid: np.ndarray, max_gap_ms: float) -> np.ndarray:
    """Linear interpolation onto `grid`, NaN wherever the bracketing samples are
    missing or further apart than `max_gap_ms` — a gap is not filled in."""
    out = np.full(len(grid), np.nan)
    if len(ts) == 0:
        return out
    right = np.searchsorted(ts, grid, side="left")
    for i, (g, r) in enumerate(zip(grid, right)):
        if r < len(ts) and ts[r] == g:
            out[i] = vs[r]
            continue
        if r == 0 or r == len(ts):
            continue
        t0, t1 = ts[r - 1], ts[r]
        if t1 - t0 > max_gap_ms:
            continue
        out[i] = vs[r - 1] + (vs[r] - vs[r - 1]) * (g - t0) / (t1 - t0)
    return out


def epochs(out: str | Path, sessions: Iterable[dict[str, Any]],
           spec: EpochSpec) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Cut, resample and baseline-correct. Returns (rows, refusals)."""
    step = 1000.0 / spec.resample_hz
    rel = np.arange(-spec.pre_ms, spec.post_ms + step / 2, step)
    rows: list[dict[str, Any]] = []
    refusals: list[dict[str, Any]] = []

    for s in sessions:
        sid = s["session_id"]
        base = {"session_id": sid, "participant_id": s.get("participant_id"),
                "condition": s.get("condition"), "epoch_set": spec.name}
        try:
            signals = read_session(out, sid, "signals")
            events = read_session(out, sid, "events").to_pylist()
        except FileNotFoundError as exc:
            refusals.append({**base, "reason": "no_data", "detail": str(exc)})
            continue

        sources = {}
        for ch in spec.channels:
            have = sorted(set(signals.filter(pc.equal(signals["channel"], ch))["source"].to_pylist()))
            if spec.source:
                sources[ch] = spec.source if spec.source in have else None
            elif len(have) == 1:
                sources[ch] = have[0]
            else:
                sources[ch] = None
                if len(have) > 1:
                    refusals.append({**base, "channel": ch, "reason": "ambiguous_source",
                                     "detail": f"{ch} comes from {have}; name a source"})
                    continue
            if sources[ch] is None:
                refusals.append({**base, "channel": ch, "reason": "no_signal",
                                 "detail": f"no {ch} from {spec.source or 'any source'}"})
        series = {ch: _series(signals, src, ch) for ch, src in sources.items() if src}

        matched = [e for e in events if e["event_type"] == spec.event_type
                   and (spec.stimulus_id is None or e.get("stimulus_id") == spec.stimulus_id)]
        for k, e in enumerate(matched):
            ev = {**base, "epoch": k, "stimulus_id": e.get("stimulus_id")}
            onset = e.get("onset_master_ts")
            if onset is None:
                refusals.append({**ev, "reason": "unaligned_event",
                                 "detail": "the event has no master timestamp"})
                continue
            for ch, (ts, vs) in series.items():
                vals = resample(ts, vs, onset + rel, spec.max_gap_ms)
                coverage = float(np.mean(~np.isnan(vals)))
                if coverage < spec.min_coverage:
                    refusals.append({**ev, "channel": ch, "reason": "low_coverage",
                                     "detail": f"{coverage:.0%} of the window has samples"})
                    continue
                offset = 0.0
                if spec.baseline_ms is not None:
                    inb = (rel >= spec.baseline_ms[0]) & (rel <= spec.baseline_ms[1])
                    b = vals[inb & ~np.isnan(vals)]
                    if not len(b):
                        refusals.append({**ev, "channel": ch, "reason": "no_baseline",
                                         "detail": "no samples in the baseline window"})
                        continue
                    offset = float(np.mean(b))
                for t, v in zip(rel, vals):
                    if not np.isnan(v):
                        rows.append({**ev, "channel": ch, "source": sources[ch],
                                     "t_ms": float(t), "value": float(v),
                                     "value_bc": float(v - offset)})
    return rows, refusals


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def attrition_rows(cohort: Cohort) -> list[dict[str, Any]]:
    out = []
    for s in cohort.funnel:
        out.append({"step": s.label, "remaining": s.remaining, "excluded": len(s.excluded)})
        out += [{"step": s.label, "session_id": sid, "reason": why} for sid, why in s.excluded]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("study_id")
    ap.add_argument("--out", type=Path, default=ROOT / "out")
    ap.add_argument("--studies", type=Path, default=ROOT / "studies")
    ap.add_argument("--include-developer", action="store_true",
                    help="also count self-test sessions (never for real analysis)")
    ap.add_argument("--allow-mixed", action="store_true",
                    help="include sessions recorded under an edited protocol")
    ap.add_argument("--csv-dir", type=Path, default=None)
    args = ap.parse_args(argv)

    study = load_study(args.studies, args.study_id)
    cohort = select(args.out, study, include_developer=args.include_developer,
                    allow_mixed=args.allow_mixed)
    print(f"\n  COHORT  {cohort.study_id}  protocol {cohort.content_hash}  "
          f"analysis {cohort.analysis_hash}")
    print("  " + "-" * 72)
    for s in cohort.funnel:
        print(f"  {s.remaining:>5}  {s.label}" + (f"   (-{len(s.excluded)})" if s.excluded else ""))
        reasons: dict[str, int] = {}
        for _, why in s.excluded:
            key = why.split(":")[0] if why.startswith(("failed", "not_measured")) else why
            reasons[key] = reasons.get(key, 0) + 1
        for why, n in sorted(reasons.items()):
            print(f"           {n} × {why}")

    all_rows, all_refusals = {}, []
    for d in (study.get("analysis") or {}).get("epochs", []):
        spec = EpochSpec.from_study(d)
        rows, refusals = epochs(args.out, cohort.included, spec)
        all_rows[spec.name] = rows
        all_refusals += refusals
        n_epochs = len({(r["session_id"], r["epoch"]) for r in rows})
        print(f"\n  epochs {spec.name}: {n_epochs} epoch(s) on {spec.event_type}, "
              f"{len(refusals)} refusal(s)")
        by: dict[str, int] = {}
        for r in refusals:
            by[r["reason"]] = by.get(r["reason"], 0) + 1
        for why, n in sorted(by.items()):
            print(f"           {n} × {why}")

    if args.csv_dir:
        args.csv_dir.mkdir(parents=True, exist_ok=True)
        _write_csv(args.csv_dir / "attrition.csv", attrition_rows(cohort))
        _write_csv(args.csv_dir / "sessions.csv", cohort.included)
        for name, rows in all_rows.items():
            _write_csv(args.csv_dir / f"epochs_{name}.csv", rows)
        _write_csv(args.csv_dir / "epoch_refusals.csv", all_refusals)
        print(f"\n  written to {args.csv_dir}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

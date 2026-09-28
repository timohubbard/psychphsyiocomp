"""Offline gaze benchmark: re-fit every calibrated session from its stored features.

    npm run bench:gaze                 # table + decisions
    npm run bench:gaze -- --json r.json

Reads `out/` and writes nothing there. Each (session, feature source) is a UNIT:
the eye/head features the engine stored, the calibration and validation dwell
windows, and the session's geometry. Every candidate change to the estimator (a
LEVER) is fitted on every unit and scored three ways:

  primary     fit on the 13 calibration targets, error on the 5 validation
              targets — the figure the pipeline reports.
  secondary   leave one target out across all 18, alpha chosen inside each
              fold. A second opinion on the same question with more targets.
  gate        the held-out hit rate at 4.5 deg that verify_gaze.py gates on,
              from fixations classified on this config's predictions.

The levers and the rule that decides them are fixed in this file BEFORE any of
them is run (git history is the pre-registration). With five units from four
people, a rule written after seeing the numbers would find a winner in noise.

The benchmark refuses to report unless the shipped configuration reproduces
every stored figure to 0.01 deg — otherwise it is measuring something other
than the pipeline, and its verdicts would be about that.

Drift correction (gaze_drift.py) is judged here too, on a different metric:
error on a LATE validation block that the correction never sees, under the
same RULE. Sessions without a late block cannot be scored on it and say so.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages" / "engine-contract" / "python"))
sys.path.insert(0, str(ROOT / "server"))

import numpy as np  # noqa: E402
import pyarrow.compute as pc  # noqa: E402

from fixations import classify  # noqa: E402
from gaze_drift import anchor_windows, is_late, late_error_deg, measure  # noqa: E402
from gaze_stage import (EstimatorConfig, TargetSpan, effective_rate, feature_matrix,  # noqa: E402
                        fit_session, onscreen_mask, target_spans)
from store import list_sessions, session_detail  # noqa: E402
from tables import read_session  # noqa: E402
from verify_gaze import GATE_PAD_DEG, hit_table  # noqa: E402

SERVER_SOURCE = "gaze.mediapipe_features@0.1.0+server-batch"
BROWSER_SOURCE = "gaze.mediapipe_features@0.1.0+browser-live"
ESTIMATOR_SOURCE = "gaze.ridge@0.1.0+server-fit"


# ---------------------------------------------------------------------------
# the levers, and the rule — fixed before any result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Lever:
    name: str
    config: EstimatorConfig
    hypothesis: str
    expect: str
    scope: str = "all"          # 'all' | 'server' | 'browser' — which units it applies to
    sweep: str | None = None    # levers sharing a sweep are one search over k values


LEVERS: tuple[Lever, ...] = (
    Lever("pose_off", EstimatorConfig(use_pose=False),
          "Three pose columns fitted on 13 points add variance when the head barely moves; "
          "the pilot measured 1.30 deg without pose against 1.65 with it.",
          "lower held-out error"),
    Lever("pose_off_browser", EstimatorConfig(use_pose=False),
          "The browser's pose comes from the same landmarks at live-video quality; if pose "
          "hurts anywhere it hurts there first.",
          "lower held-out error on browser units", scope="browser"),
    Lever("trim_0.1", EstimatorConfig(trim_fraction=0.1),
          "At ~30 fps the eye settles well inside the first quarter of a dwell; keeping more "
          "frames lowers the median's noise.",
          "lower held-out error", sweep="trim"),
    Lever("trim_0.4", EstimatorConfig(trim_fraction=0.4),
          "Settling drift lasts longer than a quarter of the dwell; dropping more removes a "
          "bias toward the previous target.",
          "lower held-out error", sweep="trim"),
    Lever("per_frame", EstimatorConfig(per_frame=True),
          "Thirteen medians discard the within-target spread that tells ridge which feature "
          "directions are noise; fitting frames (alpha by leave-one-target-out) keeps it.",
          "lower held-out error"),
    Lever("dy_norm", EstimatorConfig(dy_norm=True),
          "The lid hides the iris when looking down, so vertical offset per eye WIDTH "
          "understates vertical gaze; s_mujrz6x7's error is almost all vertical (+0.087).",
          "lower held-out error, mostly vertical"),
    Lever("clamp", EstimatorConfig(clamp_features=True),
          "Quadratic terms diverge outside the calibrated range (34% off-screen on the pilot); "
          "clamping the inputs bounds them.",
          "higher on-screen rate; held-out error unchanged"),
    Lever("bias", EstimatorConfig(bias_correction=True),
          "A systematic validation offset is a shift of the whole map (posture change between "
          "calibration and validation) that one subtraction removes.",
          "lower held-out error"),
)

#: Considered and not run, with the reason, so the absence is a result.
NOT_TESTED = {
    "roll de-rotation": "head roll's SD during dwell windows is 0.15-0.27 deg in every session, "
                        "which rotates the iris vector by <0.5% — below the measurement noise",
    "fixation-model tuning for 20 fps": "fixations.HMMParams already adapts its transition "
                                        "matrix to the sample interval and fits velocity scales "
                                        "per session; one 20 fps session cannot tune it",
}


@dataclass(frozen=True)
class Rule:
    """When a lever is adopted. Every threshold is here, and was here first."""

    max_worse_units: int = 1          # at most one voting session may get worse …
    max_worse_deg: float = 0.10       # … and by no more than this
    min_gain_deg: float = 0.20        # mean improvement across voting sessions
    min_gain_fraction: float = 0.08   # … and as a share of the default's mean error
    min_sessions_per_source: int = 3  # for a lever scoped to one feature source
    max_adopted: int = 2              # then their combination is tested once


RULE = Rule()


# ---------------------------------------------------------------------------
# units
# ---------------------------------------------------------------------------

@dataclass
class Unit:
    session_id: str
    source: str                      # the feature source fitted on
    seeded: bool                     # presentation order was randomised (sequence_seed event)
    ts: np.ndarray
    X: np.ndarray
    channels: tuple[str, ...]
    spans: list[TargetSpan]
    viewport: tuple[float, float]
    dpp: float
    fps: float
    stored_deg: float | None = None  # the pipeline's own figure, if this unit is the one it fitted
    anchors: list = field(default_factory=list)   # gaze_drift.AnchorWindow: crosses looked at

    @property
    def label(self) -> str:
        return f"{self.session_id}/{'browser' if 'browser' in self.source else 'server'}"


def feature_channels() -> tuple[str, ...]:
    """The channel list the pipeline fits with — its own constant, not a copy."""
    from engine_contract.loader import load_engine_module
    return tuple(load_engine_module("gaze.mediapipe_features").FEATURE_CHANNELS)


def load_units(out: str | Path) -> tuple[list[Unit], list[str]]:
    """Every (session, feature source) with calibration AND validation windows."""
    channels = feature_channels()
    units, skipped = [], []
    for s in list_sessions(out):
        sid = s["session_id"]
        d = session_detail(out, sid)
        m = d["meta"]
        if not m.get("px_per_mm") or not m.get("viewing_distance_mm"):
            skipped.append(f"{sid}: no geometry")
            continue
        dpp = float(np.degrees(np.arctan2(1.0 / m["px_per_mm"], m["viewing_distance_mm"])))
        viewport = (float(m["screen_width_px"]), float(m["screen_height_px"]))
        ev = read_session(out, sid, "events").to_pylist()
        spans = target_spans(ev)
        if not any(sp.kind == "validation_point" for sp in spans):
            skipped.append(f"{sid}: no calibration/validation windows")
            continue
        seeded = any(e["event_type"] == "sequence_seed" for e in ev)
        sig = read_session(out, sid, "signals")
        for source in (SERVER_SOURCE, BROWSER_SOURCE):
            rows = sig.filter(pc.equal(sig["source"], source)).select(["channel", "master_ts", "value"]).to_pylist()
            if not rows:
                continue
            ts, X = feature_matrix(rows, channels)
            if not len(ts):
                continue
            units.append(Unit(sid, source, seeded, ts, X, channels, spans, viewport, dpp, effective_rate(ts),
                              anchors=anchor_windows(ev)))
        q = read_session(out, sid, "quality")
        stored = q.filter(pc.and_(pc.equal(q["metric"], "gaze_average_offset_deg"),
                                  pc.equal(q["source"], ESTIMATOR_SOURCE)))["value"].to_pylist()
        if stored:
            # Which unit the pipeline fitted is recorded in its params, not the
            # quality row; the self-check below matches the figure to the unit.
            for u in units:
                if u.session_id == sid:
                    u.stored_deg = float(stored[-1])
    return units, skipped


# ---------------------------------------------------------------------------
# scoring one config on one unit
# ---------------------------------------------------------------------------

@dataclass
class Score:
    primary_deg: float | None
    secondary_deg: float | None
    gate_rate: float | None
    onscreen: float | None
    bias_dx_deg: float | None = None
    bias_dy_deg: float | None = None
    refusal: str | None = None


def _fit(unit: Unit, spans: list[TargetSpan], config: EstimatorConfig):
    return fit_session(unit.ts, unit.X, spans, viewport_px=unit.viewport, degrees_per_px=unit.dpp,
                       channels=list(unit.channels), config=config)


def primary(unit: Unit, config: EstimatorConfig):
    return _fit(unit, unit.spans, config)


def secondary(unit: Unit, config: EstimatorConfig) -> float | None:
    """Leave one target out over all 18: fit on 17 (as calibration), score the one left.

    None for the bias lever, whose correction needs several held-out points to
    estimate — there is no one-point version of it to score.
    """
    if config.bias_correction:
        return None
    errs = []
    for i, held in enumerate(unit.spans):
        train = [replace(s, kind="calibration_point") for j, s in enumerate(unit.spans) if j != i]
        fit = _fit(unit, train + [replace(held, kind="validation_point")], config)
        if fit.validation is not None and fit.validation.average_offset_deg is not None:
            errs.append(fit.validation.average_offset_deg)
    return float(np.mean(errs)) if errs else None


def score(unit: Unit, config: EstimatorConfig) -> Score:
    fit = primary(unit, config)
    if fit.refusal or fit.validation is None:
        return Score(None, None, None, None, refusal=fit.refusal or "no_validation")
    pred = fit.predict(unit.X)
    ok = np.all(np.isfinite(pred), axis=1)
    ts, pred = unit.ts[ok], pred[ok]
    on = onscreen_mask(pred)
    fixations = [e for e in classify(ts[on], pred[on, 0], pred[on, 1], viewport_px=unit.viewport,
                                     degrees_per_px=unit.dpp).events if e.kind == "fixation"]
    held = [(s.x, s.y, s.start_ts, s.end_ts) for s in unit.spans if s.kind == "validation_point"]
    _, hits, checked, _ = next(r for r in hit_table(fixations, held, dpp=unit.dpp, viewport=unit.viewport,
                                                     pads=(GATE_PAD_DEG,)))
    # Signed validation error, for where the error is — not for deciding anything.
    val = [s for s in unit.spans if s.kind == "validation_point"]
    vpred = np.array([np.median(pred[(ts >= s.start_ts + (s.end_ts - s.start_ts) * config.trim_fraction)
                                     & (ts <= s.end_ts)], axis=0) for s in val])
    d = vpred - np.array([[s.x, s.y] for s in val])
    return Score(
        primary_deg=fit.validation.average_offset_deg,
        secondary_deg=secondary(unit, config),
        gate_rate=hits / checked if checked else None,
        onscreen=float(on.mean()),
        bias_dx_deg=float(np.nanmean(d[:, 0]) * unit.viewport[0] * unit.dpp),
        bias_dy_deg=float(np.nanmean(d[:, 1]) * unit.viewport[1] * unit.dpp),
    )


# ---------------------------------------------------------------------------
# the decision
# ---------------------------------------------------------------------------

@dataclass
class Decision:
    lever: str
    verdict: str                       # 'adopt' | 'reject' | 'candidate'
    reasons: list[str] = field(default_factory=list)
    mean_gain_deg: float | None = None
    per_session_delta: dict[str, float] = field(default_factory=dict)


def _by_session(units: list[Unit], values: dict[str, float | None]) -> dict[str, float]:
    """One number per voting session: sources of one session are averaged, not counted twice."""
    acc: dict[str, list[float]] = {}
    for u in units:
        v = values.get(u.label)
        if v is not None and u.seeded:
            acc.setdefault(u.session_id, []).append(v)
    return {s: float(np.mean(v)) for s, v in acc.items()}


def decide(lever: Lever, units: list[Unit], base: dict[str, Score], mine: dict[str, Score],
           rule: Rule = RULE) -> Decision:
    """Apply the rule to one lever. Pure: numbers in, verdict out, every reason named."""
    scoped = [u for u in units if lever.scope == "all" or lever.scope in u.source]
    d_prim = _by_session(scoped, {u.label: (mine[u.label].primary_deg - base[u.label].primary_deg)
                                  if mine[u.label].primary_deg is not None and base[u.label].primary_deg is not None
                                  else None for u in scoped})
    base_prim = _by_session(scoped, {u.label: base[u.label].primary_deg for u in scoped})
    d_sec = _by_session(scoped, {u.label: (mine[u.label].secondary_deg - base[u.label].secondary_deg)
                                 if mine[u.label].secondary_deg is not None and base[u.label].secondary_deg is not None
                                 else None for u in scoped})
    d_gate = _by_session(scoped, {u.label: (mine[u.label].gate_rate - base[u.label].gate_rate)
                                  if mine[u.label].gate_rate is not None and base[u.label].gate_rate is not None
                                  else None for u in scoped})
    out = Decision(lever.name, "reject", per_session_delta=d_prim)
    if not d_prim:
        out.reasons.append("no voting session (none seeded) to decide on")
        return out
    gain = -float(np.mean(list(d_prim.values())))
    out.mean_gain_deg = gain
    reasons = []
    worse = [s for s, v in d_prim.items() if v > 0]
    if len(worse) > rule.max_worse_units or any(d_prim[s] > rule.max_worse_deg for s in worse):
        reasons.append(f"worse on {', '.join(f'{s} (+{d_prim[s]:.2f} deg)' for s in worse)}")
    base_mean = float(np.mean(list(base_prim.values())))
    bar = max(rule.min_gain_deg, rule.min_gain_fraction * base_mean)
    if gain < bar:
        reasons.append(f"mean gain {gain:+.2f} deg is under the bar of {bar:.2f} deg "
                       f"(the larger of {rule.min_gain_deg} deg and {rule.min_gain_fraction:.0%} "
                       f"of the default's {base_mean:.2f})")
    if not d_sec:
        reasons.append("no secondary figure to corroborate it")
    elif np.mean(list(d_sec.values())) >= 0:
        reasons.append(f"the leave-one-target-out figure does not agree ({np.mean(list(d_sec.values())):+.2f} deg)")
    fell = [s for s, v in d_gate.items() if v < 0]
    if fell:
        reasons.append(f"held-out gate hit rate fell on {', '.join(fell)}")
    if lever.sweep and any(v >= 0 for v in d_prim.values()):
        reasons.append("a swept value must beat the default on every session")
    if lever.scope != "all" and len(d_prim) < rule.min_sessions_per_source:
        out.verdict = "candidate" if not reasons else "reject"
        out.reasons = reasons or [f"only {len(d_prim)} {lever.scope} session(s) vote; "
                                  f"the rule needs {rule.min_sessions_per_source}"]
        return out
    out.verdict = "reject" if reasons else "adopt"
    out.reasons = reasons or ["passes every condition"]
    return out


# ---------------------------------------------------------------------------
# running it
# ---------------------------------------------------------------------------

def drift_score(unit: Unit, config: EstimatorConfig = EstimatorConfig()) -> dict[str, Any]:
    """Late-block error before and after drift correction, for one unit.

    The model is fitted on calibration exactly as shipped; the late block is
    kept out of the fit's own validation so nothing in the fit has seen it.
    """
    late = [s for s in unit.spans if is_late(s)]
    cal_end = max((s.end_ts for s in unit.spans if s.kind == "calibration_point"), default=None)
    if not late:
        return {"evaluable": False, "reason": "no late validation block"}
    if cal_end is None:
        return {"evaluable": False, "reason": "no calibration"}
    fit = _fit(unit, [s for s in unit.spans if not is_late(s)], config)
    if fit.refusal:
        return {"evaluable": False, "reason": fit.refusal}
    pred = fit.predict(unit.X)
    drift = measure(unit.ts, pred, unit.anchors, t0=cal_end, viewport=unit.viewport, dpp=unit.dpp)
    if not drift.used:
        return {"evaluable": False, "reason": "no usable anchor (no logged cross looked at steadily)",
                "abstained": [a.abstain for a in drift.anchors]}
    corrected = drift.apply(unit.ts, pred)

    def gate(p):
        ok = np.all(np.isfinite(p), axis=1)
        on = onscreen_mask(p[ok])
        fx = [e for e in classify(unit.ts[ok][on], p[ok][on, 0], p[ok][on, 1], viewport_px=unit.viewport,
                                  degrees_per_px=unit.dpp).events if e.kind == "fixation"]
        _, hits, checked, _ = next(r for r in hit_table(fx, [(s.x, s.y, s.start_ts, s.end_ts) for s in late],
                                                         dpp=unit.dpp, viewport=unit.viewport,
                                                         pads=(GATE_PAD_DEG,)))
        return hits / checked if checked else None

    kw = {"viewport": unit.viewport, "dpp": unit.dpp, "trim": config.trim_fraction}
    return {"evaluable": True, "before_deg": late_error_deg(unit.ts, pred, late, **kw),
            "after_deg": late_error_deg(unit.ts, corrected, late, **kw),
            "gate_before": gate(pred), "gate_after": gate(corrected),
            "anchors_used": len(drift.used), "anchors_abstained": len(drift.anchors) - len(drift.used),
            "slope_deg_per_min": drift.slope_deg_per_min}


def drift_decision(units: list[Unit], scores: dict[str, dict[str, Any]], rule: Rule = RULE) -> Decision:
    """The same RULE, on late-block error. One vote per seeded session."""
    ev = [u for u in units if scores[u.label].get("evaluable")]
    delta = _by_session(ev, {u.label: scores[u.label]["after_deg"] - scores[u.label]["before_deg"]
                             for u in ev if scores[u.label]["after_deg"] is not None
                             and scores[u.label]["before_deg"] is not None})
    before = _by_session(ev, {u.label: scores[u.label]["before_deg"] for u in ev})
    d_gate = _by_session(ev, {u.label: scores[u.label]["gate_after"] - scores[u.label]["gate_before"]
                              for u in ev if scores[u.label]["gate_after"] is not None
                              and scores[u.label]["gate_before"] is not None})
    out = Decision("drift_correction", "reject", per_session_delta=delta)
    if len(delta) < rule.min_sessions_per_source:
        out.verdict = "not_evaluable"
        out.reasons = [f"{len(delta)} seeded session(s) have a late validation block and a usable anchor; "
                       f"the rule needs {rule.min_sessions_per_source}. Record sessions under "
                       "studies/drift-example.json to make it evaluable."]
        return out
    gain = -float(np.mean(list(delta.values())))
    out.mean_gain_deg = gain
    reasons = []
    worse = [s for s, v in delta.items() if v > 0]
    if len(worse) > rule.max_worse_units or any(delta[s] > rule.max_worse_deg for s in worse):
        reasons.append(f"worse on {', '.join(f'{s} (+{delta[s]:.2f} deg)' for s in worse)}")
    bar = max(rule.min_gain_deg, rule.min_gain_fraction * float(np.mean(list(before.values()))))
    if gain < bar:
        reasons.append(f"mean gain {gain:+.2f} deg is under the bar of {bar:.2f} deg")
    fell = [s for s, v in d_gate.items() if v < 0]
    if fell:
        reasons.append(f"late-block gate hit rate fell on {', '.join(fell)}")
    out.verdict = "reject" if reasons else "adopt"
    out.reasons = reasons or ["passes every condition"]
    return out


def rest_drift(unit: Unit, config: EstimatorConfig = EstimatorConfig()) -> dict[str, Any] | None:
    """Diagnostic only: drift across the rest cross, the one late-ish anchor stored sessions have."""
    rest = [w for w in unit.anchors if w.kind == "rest_fixation"]
    cal_end = max((s.end_ts for s in unit.spans if s.kind == "calibration_point"), default=None)
    if not rest or cal_end is None:
        return None
    fit = _fit(unit, unit.spans, config)
    if fit.refusal:
        return None
    d = measure(unit.ts, fit.predict(unit.X), rest, t0=cal_end, viewport=unit.viewport, dpp=unit.dpp)
    if not d.used:
        return {"used": 0, "abstained": len(d.anchors)}
    return {"used": len(d.used), "abstained": len(d.anchors) - len(d.used),
            "minutes": [round((a.t - cal_end) / 60000, 2) for a in d.used],
            "error_deg": [round(a.error_deg, 2) for a in d.used],
            "slope_deg_per_min": d.slope_deg_per_min}


def self_check(units: list[Unit], base: dict[str, Score]) -> list[str]:
    """The shipped config must reproduce every stored figure, or nothing here counts."""
    problems = []
    by_session: dict[str, list[Unit]] = {}
    for u in units:
        by_session.setdefault(u.session_id, []).append(u)
    for sid, us in by_session.items():
        stored = us[0].stored_deg
        if stored is None:
            continue
        got = [base[u.label].primary_deg for u in us if base[u.label].primary_deg is not None]
        if not any(abs(g - stored) <= 0.01 for g in got):
            problems.append(f"{sid}: stored {stored:.3f} deg, re-fit gives {', '.join(f'{g:.3f}' for g in got)}")
    return problems


def run(out: str | Path, levers=LEVERS) -> dict[str, Any]:
    units, skipped = load_units(out)
    base_cfg = EstimatorConfig()
    base = {u.label: score(u, base_cfg) for u in units}
    problems = self_check(units, base)
    if problems:
        return {"refused": "default_does_not_reproduce_stored_figures", "problems": problems,
                "units": [u.label for u in units], "skipped": skipped}
    results = {lv.name: {u.label: (score(u, lv.config) if lv.scope == "all" or lv.scope in u.source else None)
                         for u in units} for lv in levers}
    decisions = []
    for lv in levers:
        mine = {k: v for k, v in results[lv.name].items() if v is not None}
        decisions.append(decide(lv, [u for u in units if u.label in mine], base, mine))
    adopted = sorted([d for d in decisions if d.verdict == "adopt"], key=lambda d: -(d.mean_gain_deg or 0))
    combination = None
    if len(adopted) > RULE.max_adopted:
        for d in adopted[RULE.max_adopted:]:
            d.verdict, d.reasons = "reject", [f"more than {RULE.max_adopted} levers passed; kept the larger gains"]
        adopted = adopted[:RULE.max_adopted]
    if len(adopted) == 2:
        a, b = (next(lv for lv in levers if lv.name == d.lever) for d in adopted)
        merged = replace(a.config, **b.config.changed())
        combo = Lever(f"{a.name}+{b.name}", merged, "the two adopted levers together", "lower than either alone")
        mine = {u.label: score(u, merged) for u in units}
        combination = decide(combo, units, base, mine)
        results[combo.name] = mine
    return {
        "units": [{"unit": u.label, "seeded": u.seeded, "fps": round(u.fps, 1), "stored_deg": u.stored_deg}
                  for u in units],
        "skipped": skipped,
        "default": {k: asdict(v) for k, v in base.items()},
        "levers": {name: {k: asdict(v) for k, v in r.items() if v is not None} for name, r in results.items()},
        "decisions": [asdict(d) for d in decisions],
        "combination": asdict(combination) if combination else None,
        "drift": _drift_section(units),
        "not_tested": NOT_TESTED,
        "rule": asdict(RULE),
    }


def _drift_section(units: list[Unit]) -> dict[str, Any]:
    scores = {u.label: drift_score(u) for u in units}
    return {"scores": scores, "decision": asdict(drift_decision(units, scores)),
            "rest": {u.label: r for u in units if (r := rest_drift(u)) is not None}}


def _fmt(v, spec=".2f"):
    return "—" if v is None else format(v, spec)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", type=Path, default=ROOT / "out")
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()

    r = run(args.data)
    if args.json:
        args.json.write_text(json.dumps(r, indent=2, default=float), encoding="utf-8")
    print("\n  GAZE BENCHMARK — held-out error in degrees (lower is better)")
    print("  " + "-" * 92)
    if "refused" in r:
        print(f"  REFUSED: {r['refused']}")
        for p in r["problems"]:
            print(f"    {p}")
        return 1
    units = [u["unit"] for u in r["units"]]
    print("  " + f"{'config':<18}" + "".join(f"{u:>22}" for u in units))
    print("  " + f"{'shipped (default)':<18}" + "".join(
        f"{_fmt(r['default'][u]['primary_deg']):>13} gate {_fmt(r['default'][u]['gate_rate'], '.0%'):>4}" for u in units))
    for name, res in r["levers"].items():
        print("  " + f"{name:<18}" + "".join(
            (f"{_fmt(res[u]['primary_deg']):>13} gate {_fmt(res[u]['gate_rate'], '.0%'):>4}" if u in res else f"{'n/a':>22}")
            for u in units))
    print("\n  units: " + ", ".join(f"{u['unit']} ({u['fps']} fps{'' if u['seeded'] else ', not seeded — does not vote'})"
                                    for u in r["units"]))
    print("\n  DECISIONS (rule fixed before any result — see gaze_bench.RULE)")
    for d in r["decisions"] + ([r["combination"]] if r["combination"] else []):
        print(f"  {d['verdict'].upper():<10} {d['lever']:<22} gain {_fmt(d['mean_gain_deg'], '+.2f')} deg — "
              + "; ".join(d["reasons"]))
    for k, why in r["not_tested"].items():
        print(f"  {'NOT RUN':<10} {k:<22} {why}")

    dr = r["drift"]
    print("\n  DRIFT — late validation block, before and after correcting from the crosses")
    for u, s in dr["scores"].items():
        if s.get("evaluable"):
            print(f"  {u:<26} {s['before_deg']:.2f} -> {s['after_deg']:.2f} deg   gate "
                  f"{_fmt(s['gate_before'], '.0%')} -> {_fmt(s['gate_after'], '.0%')}   "
                  f"{s['anchors_used']} anchors ({s['anchors_abstained']} abstained)")
        else:
            print(f"  {u:<26} not evaluable: {s['reason']}")
    d = dr["decision"]
    print(f"  {d['verdict'].upper():<10} drift_correction       " + "; ".join(d["reasons"]))
    if dr["rest"]:
        print("\n  Diagnostic only — error to the rest cross (straight after validation), per 5 s piece:")
        for u, x in dr["rest"].items():
            if x.get("used"):
                slope = x["slope_deg_per_min"]
                print(f"  {u:<26} " + " ".join(f"{e:.2f}" for e in x["error_deg"])
                      + f" deg   slope {_fmt(slope, '+.2f')} deg/min   ({x['abstained']} abstained)")
            else:
                print(f"  {u:<26} every piece abstained ({x['abstained']})")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

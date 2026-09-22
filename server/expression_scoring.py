"""Score AU engines against posed movements: did the right unit move when asked?

This is the positive control the facial engines lacked. On the M0 pilot the face
was neutral throughout, so two engines "disagreeing" at median r = 0.14 were
correlating noise — an agreement figure is only as informative as the behaviour
in the recording. The `au-expressions` study makes the behaviour happen and
stamps what was asked for (`target_aus`) into every `expression_hold` event.

Three questions, kept apart because they have different answers:

**Sensitivity** — for AU k, are the engine's values during holds that ASK for k
higher than during the neutral "get ready" phase of the same trials? Scored as
an AUC (the probability a random target hold outranks a random neutral window),
which is unit-free, so two engines on different scales are comparable. The
neutral windows are the same face seconds earlier, not a session average, so
slow drift in lighting or posture cannot masquerade as a response.

**Specificity** — are target holds higher than holds of OTHER movements? Kept
separate because it is not the same claim, and it is legitimately lower: a broad
smile opens the lips (AU25) and recruits the cheeks (AU06), so "not requested"
is not "absent". A low specificity for AU25 is anatomy; a low sensitivity is the
engine.

**Agreement on behaviour that happened** — the between-engine correlation of
per-trial hold values, across all holds. This is the §2.2 comparison done on
material where there was something to agree about.

What this is NOT: a measure of accuracy. `target_aus` records what was
REQUESTED. People pose unevenly, and a participant who could not wrinkle their
nose on cue will make every engine look insensitive to AU09. Human annotation
(server/evaluation.py) stays the reference standard; this is the check that can
run the moment a recording exists.

Trial counts are small by design — each AU is targeted by one or two movements,
repeated twice — so every figure carries its n, and an AUC from fewer than
MIN_TARGET_TRIALS target trials is refused rather than reported.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import numpy as np

#: Skip this much of each hold before scoring it. The hold cue appears, and the
#: face takes a reaction time plus a ramp to reach the posed configuration;
#: including that ramp dilutes every hold with frames of a face still on its
#: way there. Simple reaction time is ~250 ms, but voluntary facial movement to
#: a verbal cue is slower, and at the AU engines' ~2 Hz stride one second costs
#: about two frames of a four-second hold.
HOLD_ONSET_SKIP_MS = 1000.0

#: Below this many target trials an AUC is two or three numbers ranked, and
#: reported as a score it would carry authority it does not have.
MIN_TARGET_TRIALS = 2

#: Minimum frames inside a window for it to yield a trial value at all.
MIN_FRAMES_PER_WINDOW = 1


@dataclass(frozen=True)
class Trial:
    stimulus_id: str
    expression: str
    target_aus: tuple[int, ...]
    ready: tuple[float, float]   # master-clock window, neutral baseline
    hold: tuple[float, float]    # master-clock window, scored part of the hold


@dataclass
class AUScore:
    source: str
    au: str
    n_target: int
    n_neutral: int
    n_other: int
    sensitivity_auc: float | None
    specificity_auc: float | None
    target_median: float | None
    neutral_median: float | None
    verdict: str                      # 'ok' | 'too_few_trials' | 'no_data'
    detail: str | None = None


@dataclass
class EngineAgreement:
    au: str
    source_a: str
    source_b: str
    r: float | None
    n_trials: int
    verdict: str
    detail: str | None = None


@dataclass
class ExpressionReport:
    n_trials: int
    trials_by_expression: dict[str, int]
    scores: list[AUScore] = field(default_factory=list)
    agreement: list[EngineAgreement] = field(default_factory=list)
    refusal: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_trials": self.n_trials,
            "trials_by_expression": self.trials_by_expression,
            "scores": [vars(s) for s in self.scores],
            "agreement": [vars(a) for a in self.agreement],
            "refusal": self.refusal,
            "hold_onset_skip_ms": HOLD_ONSET_SKIP_MS,
            "min_target_trials": MIN_TARGET_TRIALS,
        }


# ---------------------------------------------------------------------------
# trials from events
# ---------------------------------------------------------------------------

def _meta(e: dict[str, Any]) -> dict[str, Any]:
    m = e.get("metadata")
    if isinstance(m, str):
        try:
            return json.loads(m) or {}
        except json.JSONDecodeError:
            return {}
    return m or {}


def trials_from_events(events: Iterable[dict[str, Any]]) -> list[Trial]:
    """Pair each trial's prompt with its hold, on the master clock.

    A trial is only usable when both are closed spans on the master clock. An
    unaligned event is dropped rather than scored on its native clock: the
    signals are on the master clock, and mixing clocks would compare a hold
    with frames from a different moment.
    """
    prompts: dict[str, dict[str, Any]] = {}
    holds: dict[str, dict[str, Any]] = {}
    for e in events:
        sid = e.get("stimulus_id")
        if not sid:
            continue
        if e.get("event_type") == "expression_prompt":
            prompts[sid] = e
        elif e.get("event_type") == "expression_hold":
            holds[sid] = e

    trials: list[Trial] = []
    for sid, h in sorted(holds.items()):
        p = prompts.get(sid)
        if p is None:
            continue
        on_p, on_h, off_h = p.get("onset_master_ts"), h.get("onset_master_ts"), h.get("offset_master_ts")
        if on_p is None or on_h is None or off_h is None or not (on_p < on_h < off_h):
            continue
        meta = _meta(h)
        targets = tuple(int(a) for a in meta.get("target_aus") or ())
        if not targets:
            continue
        hold_start = min(on_h + HOLD_ONSET_SKIP_MS, off_h)
        trials.append(Trial(
            stimulus_id=sid, expression=str(meta.get("expression", sid)),
            target_aus=targets, ready=(float(on_p), float(on_h)),
            hold=(float(hold_start), float(off_h))))
    return trials


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def _channel(au: int) -> str:
    return f"au.AU{au:02d}"


def _window_value(ts: np.ndarray, v: np.ndarray, window: tuple[float, float]) -> float | None:
    sel = (ts >= window[0]) & (ts <= window[1])
    if int(sel.sum()) < MIN_FRAMES_PER_WINDOW:
        return None
    # Median, not mean: one blink or motion-blurred frame inside a four-second
    # hold should not move the trial's value.
    return float(np.median(v[sel]))


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    """P(random positive > random negative), ties counted half. Mann-Whitney U / (n1 n2)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if len(pos) == 0 or len(neg) == 0:
        return None
    greater = (pos[:, None] > neg[None, :]).sum()
    ties = (pos[:, None] == neg[None, :]).sum()
    return float((greater + 0.5 * ties) / (len(pos) * len(neg)))


def _series(rows: Sequence[dict[str, Any]], source: str, channel: str):
    pairs = sorted((float(r["master_ts"]), float(r["value"])) for r in rows
                   if r.get("source") == source and r.get("channel") == channel
                   and r.get("master_ts") is not None and r.get("value") is not None)
    if not pairs:
        return np.empty(0), np.empty(0)
    t, v = zip(*pairs)
    return np.asarray(t), np.asarray(v)


def score_session(
    signal_rows: Sequence[dict[str, Any]], events: Iterable[dict[str, Any]],
    sources: Sequence[str] | None = None,
) -> ExpressionReport:
    """Sensitivity, specificity and on-behaviour agreement for every AU engine."""
    trials = trials_from_events(events)
    by_expr: dict[str, int] = {}
    for t in trials:
        by_expr[t.expression] = by_expr.get(t.expression, 0) + 1

    if not trials:
        return ExpressionReport(0, {}, refusal=(
            "no scorable expression trials — this session has no closed, aligned "
            "expression_prompt/expression_hold pairs with target_aus. Only sessions "
            "recorded under a study with the expression_prompts task can be scored."))

    au_rows = [r for r in signal_rows if str(r.get("channel", "")).startswith("au.")]
    all_sources = sorted({r["source"] for r in au_rows})
    sources = list(sources) if sources is not None else all_sources
    if not sources:
        return ExpressionReport(len(trials), by_expr, refusal=(
            "no AU engine output in this session — run the pipeline with --aus"))

    targeted = sorted({a for t in trials for a in t.target_aus})
    report = ExpressionReport(len(trials), by_expr)

    # Per-trial hold values, kept for the agreement pass.
    hold_values: dict[tuple[str, int], dict[str, float]] = {}

    for source in sources:
        for au in targeted:
            ts, v = _series(au_rows, source, _channel(au))
            if len(ts) == 0:
                report.scores.append(AUScore(source, f"AU{au:02d}", 0, 0, 0, None, None,
                                             None, None, "no_data",
                                             "this engine does not emit this AU"))
                continue

            target, other, neutral = [], [], []
            per_trial: dict[str, float] = {}
            for t in trials:
                hv = _window_value(ts, v, t.hold)
                nv = _window_value(ts, v, t.ready)
                if nv is not None:
                    neutral.append(nv)
                if hv is None:
                    continue
                per_trial[t.stimulus_id] = hv
                (target if au in t.target_aus else other).append(hv)
            hold_values[(source, au)] = per_trial

            base = dict(source=source, au=f"AU{au:02d}", n_target=len(target),
                        n_neutral=len(neutral), n_other=len(other),
                        target_median=float(np.median(target)) if target else None,
                        neutral_median=float(np.median(neutral)) if neutral else None)
            if len(target) < MIN_TARGET_TRIALS or not neutral:
                report.scores.append(AUScore(
                    **base, sensitivity_auc=None, specificity_auc=None,
                    verdict="too_few_trials",
                    detail=(f"{len(target)} target trial(s) with frames; an AUC needs "
                            f"at least {MIN_TARGET_TRIALS}")))
                continue
            report.scores.append(AUScore(
                **base, sensitivity_auc=auc(target, neutral),
                specificity_auc=auc(target, other) if other else None, verdict="ok"))

    # Agreement between engines, on held movements only.
    for au in targeted:
        present = [s for s in sources if (s, au) in hold_values]
        for i, a in enumerate(present):
            for b in present[i + 1:]:
                va, vb = hold_values[(a, au)], hold_values[(b, au)]
                common = sorted(set(va) & set(vb))
                x = np.array([va[k] for k in common])
                y = np.array([vb[k] for k in common])
                if len(common) < 3:
                    report.agreement.append(EngineAgreement(
                        f"AU{au:02d}", a, b, None, len(common), "too_few_trials"))
                elif np.std(x) < 1e-12 or np.std(y) < 1e-12:
                    report.agreement.append(EngineAgreement(
                        f"AU{au:02d}", a, b, None, len(common), "degenerate",
                        "one engine gave the same value for every hold"))
                else:
                    report.agreement.append(EngineAgreement(
                        f"AU{au:02d}", a, b, float(np.corrcoef(x, y)[0, 1]),
                        len(common), "ok"))
    return report


def summarise(report: ExpressionReport) -> dict[str, Any]:
    """Per-engine headline: median sensitivity AUC over AUs it could be scored on."""
    out: dict[str, Any] = {}
    for s in report.scores:
        e = out.setdefault(s.source, {"sens": [], "spec": [], "unscored": 0})
        if s.verdict == "ok":
            e["sens"].append(s.sensitivity_auc)
            if s.specificity_auc is not None:
                e["spec"].append(s.specificity_auc)
        else:
            e["unscored"] += 1
    return {src: {
        "n_aus_scored": len(e["sens"]),
        "median_sensitivity_auc": float(np.median(e["sens"])) if e["sens"] else None,
        "median_specificity_auc": float(np.median(e["spec"])) if e["spec"] else None,
        "n_aus_unscored": e["unscored"],
    } for src, e in out.items()}

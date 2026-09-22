"""Evaluation against human labels, and the ceiling those labels impose.

`agreement.py` compares two engines to each other. This compares an engine to
people, which is a different question with a different trap: an engine measured
against one person's labels is measured against that person, and calling the
result accuracy launders a single opinion into ground truth.

§2.1 is why this module exists at all. On the same webcam video, human coders
reached 92% where WebGazer reached 70% — so a human arm is both the reference
standard worth having and a reminder that the reference is itself a
measurement with error. Three things follow, and they are the whole design:

**Inter-rater agreement is the ceiling, not a footnote.** If two coders agree
at 0.70, an engine agreeing with them at 0.68 is at 97% of what a person
achieves on the same material. Reporting 0.68 as though 1.0 were reachable
makes an engine at the ceiling look like a failure, and — worse the other way
— makes a task where coders barely agree look like a task an engine is bad at.
Every report here carries the ceiling beside the score.

**Kappa is not accuracy, and kappa lies in a known direction.** Two coders who
agree on 95% of frames can score kappa near zero when one category dominates,
because kappa divides out the agreement expected by chance and skewed
prevalence makes almost all agreement "expected". That is the kappa paradox,
and it is not a rare edge case in behavioural coding — most AUs are absent in
most frames. So prevalence and bias indices ship alongside every kappa, and a
kappa computed on skewed data is labelled as such rather than quietly
reported.

**One rater is not a reference standard.** `reference_from` refuses a single
rater. Not warns — refuses, with a reason, in the same way the chinrest
refuses an implausible distance.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

#: The paradox is DETECTED DIRECTLY rather than through a proxy on prevalence.
#: It is defined as what it is — high observed agreement sitting under a low
#: kappa — because a threshold on the prevalence index has to be guessed, and
#: the first guess here (0.80) missed the textbook case at 0.75 while the
#: phenomenon it was standing in for was plainly present.
#:
#: These two are the conventional reading boundaries: 0.80 is where observed
#: agreement starts being described as high, and 0.60 is the bottom of
#: "substantial" on the Landis-Koch scale people actually quote. A pair that
#: clears the first and fails the second is the paradox by construction —
#: with balanced categories, 80% agreement gives kappa 0.60 exactly, so the
#: gap can only open up when prevalence is skewed.
PARADOX_MIN_AGREEMENT = 0.80
PARADOX_MAX_KAPPA = 0.60

#: Fewer items than this and an agreement coefficient is an anecdote. Chosen to
#: match the smallest N at which a kappa confidence interval is narrower than
#: the range of verdicts people draw from kappa.
MIN_ITEMS = 30

#: Two raters is the minimum for a reference standard. Three is where you can
#: start telling "the task is hard" from "one coder is an outlier", and that
#: distinction is reported rather than assumed.
MIN_RATERS = 2


@dataclass(frozen=True)
class Refusal:
    """Why no number is being returned."""

    reason: str
    detail: str | None = None

    def __bool__(self) -> bool:  # so `if result:` reads as "did it work"
        return False


@dataclass(frozen=True)
class KappaResult:
    """Cohen's kappa with the things that make it interpretable.

    `paradox_risk` is true when prevalence is skewed enough that a high
    observed agreement can coexist with a near-zero kappa. When it is true,
    `observed_agreement` is the number to read and kappa is the number to
    explain.
    """

    kappa: float
    observed_agreement: float
    expected_agreement: float
    n_items: int
    n_categories: int
    prevalence_index: float
    bias_index: float
    paradox_risk: bool
    #: Which of the two is doing the damage when `paradox_risk` is set:
    #: "prevalence" (the categories are lopsided) or "bias" (the raters use
    #: them at different rates). They need different responses — the first is
    #: a property of the behaviour being coded, the second of the coders.
    dominant_cause: str | None
    ci95: tuple[float, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "kappa": round(self.kappa, 4),
            "observed_agreement": round(self.observed_agreement, 4),
            "expected_agreement": round(self.expected_agreement, 4),
            "n_items": self.n_items,
            "n_categories": self.n_categories,
            "prevalence_index": round(self.prevalence_index, 4),
            "bias_index": round(self.bias_index, 4),
            "paradox_risk": self.paradox_risk,
            "dominant_cause": self.dominant_cause,
            "ci95": [round(self.ci95[0], 4), round(self.ci95[1], 4)],
        }


def cohens_kappa(a: Sequence[Any], b: Sequence[Any]) -> KappaResult | Refusal:
    """Chance-corrected agreement between two raters on categorical labels.

    Returns a `Refusal` rather than a number when the data cannot support one.
    """
    if len(a) != len(b):
        return Refusal("length_mismatch", f"{len(a)} vs {len(b)}")
    n = len(a)
    if n < MIN_ITEMS:
        return Refusal("too_few_items", f"{n} < {MIN_ITEMS}")

    categories = sorted({*a, *b}, key=repr)
    if len(categories) < 2:
        # Both raters used one label for everything. Agreement is perfect and
        # means nothing — there was no decision to agree about.
        return Refusal("single_category",
                       f"every item labelled {categories[0]!r}")

    index = {c: i for i, c in enumerate(categories)}
    k = len(categories)
    table = np.zeros((k, k), dtype=float)
    for x, y in zip(a, b):
        table[index[x], index[y]] += 1

    po = float(np.trace(table)) / n
    row = table.sum(axis=1) / n
    col = table.sum(axis=0) / n
    pe = float(np.dot(row, col))

    if math.isclose(pe, 1.0):
        return Refusal("no_chance_variation",
                       "expected agreement is 1.0; kappa is undefined")

    kappa = (po - pe) / (1.0 - pe)

    # Byrt, Bishop & Carlin's indices. Prevalence is about the categories
    # themselves being lopsided; bias is about the two raters using them at
    # different rates. They explain different halves of a low kappa sitting
    # under a high observed agreement.
    if k == 2:
        prevalence = abs(table[0, 0] - table[1, 1]) / n
        bias = abs(table[0, 1] - table[1, 0]) / n
    else:
        # Generalised: how far the marginals sit from uniform, and how far the
        # two raters' marginals sit from each other.
        prevalence = float(np.max(row + col) / 2.0 - 1.0 / k) * k / (k - 1)
        bias = float(np.abs(row - col).sum() / 2.0)

    paradox = bool(po >= PARADOX_MIN_AGREEMENT and kappa < PARADOX_MAX_KAPPA)
    cause = None
    if paradox:
        cause = "prevalence" if prevalence >= bias else "bias"

    # Standard error per Fleiss, Cohen & Everitt. Approximate, and wide at
    # small N by design — the width is the honest part.
    se = math.sqrt(max(po * (1 - po), 1e-12) / (n * (1 - pe) ** 2))
    half = 1.96 * se
    return KappaResult(
        kappa=kappa, observed_agreement=po, expected_agreement=pe,
        n_items=n, n_categories=k,
        # float() rather than the numpy scalars these arrive as: a numpy bool
        # is not `is False`, and a caller writing the obvious identity check
        # would silently get the wrong answer.
        prevalence_index=float(prevalence), bias_index=float(bias),
        paradox_risk=paradox, dominant_cause=cause,
        ci95=(max(kappa - half, -1.0), min(kappa + half, 1.0)),
    )


@dataclass(frozen=True)
class ReferenceStandard:
    """Labels agreed by several coders, plus how much they agreed.

    `ceiling` is the mean pairwise agreement between the humans. It is the
    number an engine should be read against: agreement above it is not better
    than human, it is over-fitting to whatever the majority happened to pick.
    """

    labels: tuple[Any, ...]
    n_raters: int
    ceiling: float
    pairwise: tuple[float, ...]
    unanimous_fraction: float
    outlier_rater: int | None
    ceiling_kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_items": len(self.labels),
            "n_raters": self.n_raters,
            "ceiling": round(self.ceiling, 4),
            "ceiling_kind": self.ceiling_kind,
            "pairwise": [round(p, 4) for p in self.pairwise],
            "unanimous_fraction": round(self.unanimous_fraction, 4),
            "outlier_rater": self.outlier_rater,
        }


def reference_from(raters: Sequence[Sequence[Any]],
                   *, use: str = "kappa") -> ReferenceStandard | Refusal:
    """Build a reference standard from several coders' labels.

    ``use`` selects the ceiling statistic: ``"kappa"`` for chance-corrected
    agreement, ``"raw"`` for the proportion of items two coders label the same.
    Raw is the right choice when prevalence is skewed enough that kappa is
    being driven by the base rate — the choice is the caller's and is recorded
    in ``ceiling_kind`` either way.

    Refuses a single rater. One person's labels are one person's labels, and
    the word "ground truth" does a lot of quiet work in a results section.
    """
    if len(raters) < MIN_RATERS:
        return Refusal("single_rater",
                       "one coder's labels are not a reference standard; "
                       f"need at least {MIN_RATERS}")

    lengths = {len(r) for r in raters}
    if len(lengths) != 1:
        return Refusal("ragged_raters", f"item counts differ: {sorted(lengths)}")
    n = lengths.pop()
    if n < MIN_ITEMS:
        return Refusal("too_few_items", f"{n} < {MIN_ITEMS}")

    pairwise: list[float] = []
    per_rater: list[list[float]] = [[] for _ in raters]
    for i in range(len(raters)):
        for j in range(i + 1, len(raters)):
            score = _pair_score(raters[i], raters[j], use)
            if isinstance(score, Refusal):
                return score
            pairwise.append(score)
            per_rater[i].append(score)
            per_rater[j].append(score)

    # Majority label per item. Ties resolve to the first rater's choice, which
    # is arbitrary and recorded as non-unanimous rather than hidden.
    labels: list[Any] = []
    unanimous = 0
    for idx in range(n):
        votes = Counter(r[idx] for r in raters)
        top, count = votes.most_common(1)[0]
        if count == len(raters):
            unanimous += 1
        if sum(1 for _, c in votes.items() if c == count) > 1:
            top = raters[0][idx]
        labels.append(top)

    # An outlier is a coder who agrees with everyone else noticeably less than
    # they agree with each other. Worth naming: "the task is hard" and "one
    # coder read the instructions differently" look identical in a mean.
    means = [float(np.mean(p)) for p in per_rater]
    outlier = None
    if len(raters) >= 3:
        lowest = int(np.argmin(means))
        others = [m for i, m in enumerate(means) if i != lowest]
        if means[lowest] < float(np.mean(others)) - 0.15:
            outlier = lowest

    return ReferenceStandard(
        labels=tuple(labels), n_raters=len(raters),
        ceiling=float(np.mean(pairwise)), pairwise=tuple(pairwise),
        unanimous_fraction=unanimous / n, outlier_rater=outlier,
        ceiling_kind=use,
    )


def _pair_score(a: Sequence[Any], b: Sequence[Any], use: str):
    if use == "raw":
        return float(np.mean([x == y for x, y in zip(a, b)]))
    if use != "kappa":
        return Refusal("unknown_ceiling_statistic", use)
    result = cohens_kappa(a, b)
    if isinstance(result, Refusal):
        return result
    return result.kappa


@dataclass
class EngineEvaluation:
    """How an engine did, against people, with the ceiling attached."""

    engine_score: float
    ceiling: float
    n_items: int
    kappa: KappaResult | None
    ceiling_kind: str
    notes: list[str] = field(default_factory=list)

    @property
    def fraction_of_ceiling(self) -> float | None:
        """Engine score as a fraction of what humans achieve.

        None when the ceiling is at or below zero: dividing by it would produce
        a large positive number from a task where coders did not agree at all,
        which is the most flattering possible way to report a failure.
        """
        if self.ceiling <= 0:
            return None
        return self.engine_score / self.ceiling

    def as_dict(self) -> dict[str, Any]:
        return {
            "engine_score": round(self.engine_score, 4),
            "ceiling": round(self.ceiling, 4),
            "ceiling_kind": self.ceiling_kind,
            "fraction_of_ceiling": (None if self.fraction_of_ceiling is None
                                    else round(self.fraction_of_ceiling, 4)),
            "n_items": self.n_items,
            "kappa": self.kappa.as_dict() if self.kappa else None,
            "notes": list(self.notes),
        }


def evaluate_against(predictions: Sequence[Any],
                     reference: ReferenceStandard) -> EngineEvaluation | Refusal:
    """Score an engine against a human reference standard.

    The score uses the same statistic the ceiling does, because comparing a
    kappa to a raw-agreement ceiling is comparing two different quantities and
    the ratio would be meaningless.
    """
    if len(predictions) != len(reference.labels):
        return Refusal("length_mismatch",
                       f"{len(predictions)} predictions vs "
                       f"{len(reference.labels)} reference items")

    score = _pair_score(predictions, reference.labels, reference.ceiling_kind)
    if isinstance(score, Refusal):
        return score

    kappa = cohens_kappa(predictions, reference.labels)
    notes: list[str] = []

    if isinstance(kappa, Refusal):
        notes.append(f"kappa unavailable: {kappa.reason}")
        kappa = None
    elif kappa.paradox_risk and kappa.dominant_cause == "prevalence":
        notes.append(
            f"prevalence is skewed (index {kappa.prevalence_index:.2f}), so "
            f"kappa {kappa.kappa:.2f} understates agreement of "
            f"{kappa.observed_agreement:.0%} — read the raw agreement and "
            f"explain the kappa, not the other way round")
    elif kappa.paradox_risk:
        notes.append(
            f"kappa {kappa.kappa:.2f} sits well below agreement of "
            f"{kappa.observed_agreement:.0%} because the two label sets are "
            f"used at different rates (bias index {kappa.bias_index:.2f}). "
            f"Unlike skewed prevalence this is a fact about the raters, not "
            f"about the behaviour — check whether they read the same codebook")

    if reference.outlier_rater is not None:
        notes.append(
            f"rater {reference.outlier_rater} agrees with the others "
            f"noticeably less than they agree with each other; the ceiling may "
            f"be depressed by one coder rather than by the task")

    if score > reference.ceiling:
        # Not celebrated. §2.1's whole point is that humans set the bar; an
        # engine above it is agreeing with the majority vote more than the
        # people who cast it do, which is a property of majority voting.
        notes.append(
            f"engine agreement {score:.3f} exceeds the human ceiling "
            f"{reference.ceiling:.3f} — this is what over-fitting to a majority "
            f"label looks like, not superhuman performance")

    return EngineEvaluation(
        engine_score=score, ceiling=reference.ceiling,
        n_items=len(reference.labels), kappa=kappa,
        ceiling_kind=reference.ceiling_kind, notes=notes,
    )

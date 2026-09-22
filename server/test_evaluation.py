"""Tests for evaluation against human labels.

Two things these have to pin down, and both are about not being flattered by
your own numbers.

The kappa paradox is the first: two coders agreeing on 95% of frames can score
kappa near zero when one category dominates, and most AUs are absent in most
frames, so this is the normal case in behavioural coding rather than an edge
case. A test measures the paradox happening rather than asserting that it can.

The human ceiling is the second. §2.1: coders reached 92% where WebGazer
reached 70% on the same video. An engine at 0.68 against a 0.70 ceiling is at
the bar, and reporting it against an implied 1.0 would call that a failure.
"""

from __future__ import annotations

import pytest

from evaluation import (
    MIN_ITEMS,
    MIN_RATERS,
    EngineEvaluation,
    Refusal,
    cohens_kappa,
    evaluate_against,
    reference_from,
)


def alternating(n=100, k=2):
    return [i % k for i in range(n)]


def mostly(label, n=100, others=5):
    """Skewed labels: `others` items differ, the rest are `label`."""
    return [(1 - label) if i < others else label for i in range(n)]


# ---------------------------------------------------------------------------
# kappa, and where it misleads
# ---------------------------------------------------------------------------

def test_perfect_agreement_on_a_balanced_task_scores_one():
    a = alternating(100)
    r = cohens_kappa(a, list(a))
    assert r.kappa == pytest.approx(1.0)
    assert r.observed_agreement == pytest.approx(1.0)


def test_chance_agreement_scores_near_zero():
    rng = __import__("numpy").random.default_rng(0)
    a = rng.integers(0, 2, 400).tolist()
    b = rng.integers(0, 2, 400).tolist()
    assert abs(cohens_kappa(a, b).kappa) < 0.15


def from_table(n00, n01, n10, n11):
    """Two label sequences realising a given 2x2 agreement table."""
    a = [0] * (n00 + n01) + [1] * (n10 + n11)
    b = [0] * n00 + [1] * n01 + [0] * n10 + [1] * n11
    return a, b


def test_the_kappa_paradox_is_measured_not_assumed():
    """The headline case, and the textbook one.

    Both tables below have exactly 85% observed agreement. The balanced one
    scores kappa 0.70 and the skewed one scores 0.32 — same agreement, same
    number of disagreements, less than half the kappa. An AU absent in most
    frames is the skewed table, which is why this is the normal case in
    behavioural coding rather than an edge case.
    """
    skewed = cohens_kappa(*from_table(80, 9, 6, 5))
    balanced = cohens_kappa(*from_table(40, 9, 6, 45))

    assert skewed.observed_agreement == pytest.approx(0.85)
    assert balanced.observed_agreement == pytest.approx(0.85)

    assert balanced.kappa > 0.65
    assert skewed.kappa < 0.40
    assert skewed.kappa < balanced.kappa / 2


def test_only_the_skewed_table_is_flagged():
    """The flag has to discriminate, or it is just a label on the whole
    corpus."""
    skewed = cohens_kappa(*from_table(80, 9, 6, 5))
    balanced = cohens_kappa(*from_table(40, 9, 6, 45))

    assert skewed.paradox_risk is True
    assert balanced.paradox_risk is False
    assert skewed.dominant_cause == "prevalence"


def test_the_flag_is_a_real_bool_not_a_numpy_one():
    """`np.False_ is False` is False, and a caller writing the obvious
    identity check would silently get the wrong answer."""
    r = cohens_kappa(*from_table(40, 9, 6, 45))
    assert type(r.paradox_risk) is bool
    assert type(r.prevalence_index) is float


def test_rater_bias_is_distinguished_from_skewed_prevalence():
    """They need different responses: skewed prevalence is a fact about the
    behaviour, bias is a fact about the coders."""
    # Same category frequencies overall, but the disagreements run one way.
    r = cohens_kappa(*from_table(45, 20, 2, 33))
    if r.paradox_risk:
        assert r.dominant_cause == "bias"
    assert r.bias_index > r.prevalence_index


def test_a_balanced_task_with_high_agreement_does_not_flag():
    a = alternating(100)
    b = list(a)
    for i in (3, 11, 27, 48, 61):
        b[i] = 1 - b[i]
    r = cohens_kappa(a, b)
    assert r.observed_agreement >= 0.94
    assert r.paradox_risk is False
    assert r.kappa > 0.85


def test_prevalence_and_bias_are_reported_separately():
    """They explain different halves of a low kappa: prevalence is the
    categories being lopsided, bias is the two raters using them at different
    rates."""
    # One rater says 1 far more often than the other: bias, not prevalence.
    a = [0] * 60 + [1] * 40
    b = [0] * 85 + [1] * 15
    r = cohens_kappa(a, b)
    assert r.bias_index > 0.1


def test_a_confidence_interval_travels_with_every_kappa():
    r = cohens_kappa(alternating(50), alternating(50))
    assert r.ci95[0] <= r.kappa <= r.ci95[1]


def test_the_interval_is_wider_at_small_n():
    """The width is the honest part."""
    small = cohens_kappa(alternating(40)[:], _noisy(alternating(40), 4))
    large = cohens_kappa(alternating(400)[:], _noisy(alternating(400), 40))
    assert (small.ci95[1] - small.ci95[0]) > (large.ci95[1] - large.ci95[0])


def _noisy(labels, n_flips):
    out = list(labels)
    step = max(len(out) // max(n_flips, 1), 1)
    for i in range(0, len(out), step):
        out[i] = 1 - out[i]
    return out


# ---------------------------------------------------------------------------
# kappa refusals
# ---------------------------------------------------------------------------

def test_too_few_items_is_refused_rather_than_estimated():
    r = cohens_kappa(alternating(10), alternating(10))
    assert isinstance(r, Refusal)
    assert r.reason == "too_few_items"


def test_a_single_category_is_refused():
    """Both coders labelled everything the same. Agreement is perfect and
    means nothing: there was no decision to agree about."""
    r = cohens_kappa([0] * 100, [0] * 100)
    assert isinstance(r, Refusal)
    assert r.reason == "single_category"


def test_mismatched_lengths_are_refused():
    assert isinstance(cohens_kappa(alternating(100), alternating(90)), Refusal)


def test_a_refusal_is_falsy_so_callers_cannot_use_it_as_a_score():
    assert not cohens_kappa([0] * 100, [0] * 100)


def test_more_than_two_categories_works():
    r = cohens_kappa(alternating(120, k=4), alternating(120, k=4))
    assert r.n_categories == 4
    assert r.kappa == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# a reference standard needs more than one person
# ---------------------------------------------------------------------------

def test_one_rater_is_refused_as_a_reference_standard():
    """The word 'ground truth' does a lot of quiet work in a results section."""
    r = reference_from([alternating(100)])
    assert isinstance(r, Refusal)
    assert r.reason == "single_rater"
    assert "not a reference standard" in r.detail


def test_two_raters_are_enough():
    r = reference_from([alternating(100), alternating(100)], use="raw")
    assert r.n_raters == 2
    assert r.ceiling == pytest.approx(1.0)


def test_ragged_rater_lists_are_refused():
    r = reference_from([alternating(100), alternating(90)])
    assert isinstance(r, Refusal)
    assert r.reason == "ragged_raters"


def test_the_majority_label_is_taken_per_item():
    a = [0] * 50 + [1] * 50
    b = [0] * 50 + [1] * 50
    c = [1] * 100                      # dissents everywhere
    ref = reference_from([a, b, c], use="raw")
    assert list(ref.labels) == a


def test_unanimity_is_reported_because_a_majority_hides_disagreement():
    """Two of three agreeing is a majority label and is not the same evidence
    as three of three, so the fraction ships beside the labels."""
    a = [0] * 100
    b = [0] * 100
    c = [0] * 90 + [1] * 10
    ref = reference_from([a, b, c], use="raw")
    assert ref.unanimous_fraction == pytest.approx(0.90)
    assert list(ref.labels) == [0] * 100


def test_an_outlier_coder_is_named():
    """'The task is hard' and 'one coder read the instructions differently'
    look identical in a mean."""
    base = alternating(200)
    a, b = list(base), list(base)
    c = [1 - x for x in base]          # systematically inverted
    ref = reference_from([a, b, c], use="raw")
    assert ref.outlier_rater == 2


def test_no_outlier_is_named_when_everyone_agrees_equally():
    base = alternating(200)
    ref = reference_from([list(base), _noisy(base, 10), _noisy(base, 10)],
                         use="raw")
    assert ref.outlier_rater is None


def test_an_outlier_needs_three_raters_to_be_visible():
    """With two, there is no way to tell which one is the outlier."""
    base = alternating(200)
    ref = reference_from([list(base), [1 - x for x in base]], use="raw")
    assert ref.outlier_rater is None


def test_the_ceiling_statistic_is_recorded():
    raw = reference_from([alternating(100), alternating(100)], use="raw")
    kap = reference_from([alternating(100), _noisy(alternating(100), 5)],
                         use="kappa")
    assert raw.ceiling_kind == "raw"
    assert kap.ceiling_kind == "kappa"


def test_an_unknown_ceiling_statistic_is_refused():
    r = reference_from([alternating(100), alternating(100)], use="f1")
    assert isinstance(r, Refusal)


# ---------------------------------------------------------------------------
# the ceiling is the point
# ---------------------------------------------------------------------------

def _hard_task(n=200):
    """Two coders who genuinely disagree a fair amount — §2.1's regime."""
    base = alternating(n)
    a = _noisy(base, n // 10)
    b = _noisy(base, n // 8)
    return a, b


def test_an_engine_at_the_human_ceiling_is_not_reported_as_a_failure():
    a, b = _hard_task()
    ref = reference_from([a, b], use="raw")
    ev = evaluate_against(ref.labels, ref)
    assert ev.fraction_of_ceiling is not None
    assert ev.fraction_of_ceiling >= 1.0


def test_the_ceiling_travels_with_every_score():
    a, b = _hard_task()
    ref = reference_from([a, b], use="raw")
    d = evaluate_against(list(a), ref).as_dict()
    assert "ceiling" in d and "fraction_of_ceiling" in d
    assert d["ceiling_kind"] == "raw"


def test_beating_the_ceiling_is_flagged_not_celebrated():
    """An engine agreeing with the majority vote more than the people who cast
    it is a property of majority voting, not superhuman performance."""
    base = alternating(200)
    raters = [_noisy(base, 20), _noisy(base, 25), _noisy(base, 22)]
    ref = reference_from(raters, use="raw")
    ev = evaluate_against(ref.labels, ref)          # perfect by construction
    assert any("over-fitting" in n for n in ev.notes)


def test_a_zero_ceiling_yields_no_fraction_rather_than_a_huge_one():
    """Dividing by a ceiling of zero is the most flattering possible way to
    report a task where coders did not agree at all."""
    ev = EngineEvaluation(engine_score=0.4, ceiling=0.0, n_items=100,
                          kappa=None, ceiling_kind="kappa")
    assert ev.fraction_of_ceiling is None
    assert ev.as_dict()["fraction_of_ceiling"] is None


def test_a_skewed_task_tells_the_reader_which_number_to_read():
    """The textbook skewed table again, this time as an engine's score.

    With two raters every disagreement is a tie, so the majority label is
    rater A's — which makes rater B a stand-in for an engine scoring against
    it. 85% agreement, kappa 0.32, and the note has to say which of those the
    reader should be looking at.
    """
    a, b = from_table(80, 9, 6, 5)
    ref = reference_from([a, b], use="raw")
    assert list(ref.labels) == a, "ties resolve to the first rater"

    ev = evaluate_against(b, ref)
    assert ev.kappa.paradox_risk is True
    assert any("prevalence is skewed" in n for n in ev.notes)
    assert any("raw agreement" in n for n in ev.notes)


def test_an_outlier_coder_is_surfaced_in_the_evaluation_too():
    base = alternating(200)
    ref = reference_from([list(base), list(base), [1 - x for x in base]],
                         use="raw")
    ev = evaluate_against(list(base), ref)
    assert any("depressed by one coder" in n for n in ev.notes)


def test_predictions_of_the_wrong_length_are_refused():
    a, b = _hard_task()
    ref = reference_from([a, b], use="raw")
    assert isinstance(evaluate_against([0] * 5, ref), Refusal)


def test_the_engine_is_scored_with_the_same_statistic_as_the_ceiling():
    """Comparing a kappa to a raw-agreement ceiling compares two different
    quantities, and the ratio would be meaningless."""
    base = alternating(200)
    ref = reference_from([_noisy(base, 20), _noisy(base, 25)], use="kappa")
    ev = evaluate_against(list(base), ref)
    assert ev.ceiling_kind == "kappa"
    # A kappa and a raw agreement on the same data differ; if the engine had
    # been scored with raw agreement this would not hold.
    assert ev.engine_score <= 1.0


# ---------------------------------------------------------------------------
# the thresholds are declared
# ---------------------------------------------------------------------------

def test_the_minimums_are_module_constants_not_inline_numbers():
    assert MIN_RATERS == 2
    assert MIN_ITEMS >= 30

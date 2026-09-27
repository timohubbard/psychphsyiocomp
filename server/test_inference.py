"""The cohort statistics, held to answers known in advance.

Each test plants something (an effect, no effect, a known difference) and
checks the method recovers it — or, for the null, that it does not find more
than it should. A statistics module that is only checked for running without
error has not been checked.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from inference import (MIN_PER_ARM, hedges_g, holm, participant_curves, pooled_mean,
                       run_contrast, run_contrasts, smallest_possible_p)

GRID = np.arange(-500, 1501, 50.0)


def rows_for(curves_by_participant: dict[str, tuple[str, list[np.ndarray]]], channel="c"):
    """Epoch rows as cohort.epochs writes them, one participant per session."""
    rows = []
    for pid, (arm, epochs) in curves_by_participant.items():
        for k, curve in enumerate(epochs):
            for t, v in zip(GRID, curve):
                rows.append({"session_id": f"s-{pid}", "participant_id": pid, "condition": arm,
                             "epoch": k, "channel": channel, "t_ms": float(t), "value_bc": float(v)})
    return rows


def cohort(n_a, n_b, *, effect=0.0, window=(300, 800), sd=1.0, seed=0, epochs=3):
    rng = np.random.default_rng(seed)
    out = {}
    bump = ((GRID >= window[0]) & (GRID <= window[1])).astype(float) * effect
    for i in range(n_a):
        out[f"a{i}"] = ("A", [rng.normal(0, sd, len(GRID)) + bump for _ in range(epochs)])
    for i in range(n_b):
        out[f"b{i}"] = ("B", [rng.normal(0, sd, len(GRID)) for _ in range(epochs)])
    return rows_for(out)


def contrast(**over):
    c = {"name": "c", "epochs": "e", "channel": "c", "arms": ["A", "B"], "window_ms": [300, 800],
         "n_permutations": 2000, "seed": 7, "alpha": 0.05, "cluster": {"p_threshold": 0.05}}
    c.update(over)
    return c


def run(rows, **over):
    return run_contrast(contrast(**over), participant_curves(rows, "c"))


def test_a_planted_effect_is_found_where_it_was_planted():
    r = run(cohort(12, 12, effect=1.5))
    assert r["refusal"] is None
    assert r["window"]["p"] < 0.01 and r["window"]["diff"] > 1.0
    sig = [c for c in r["cluster"]["clusters"] if c["significant"]]
    assert sig, r["cluster"]
    best = max(sig, key=lambda c: abs(c["mass"]))
    # The cluster sits over the planted window. (Its edges are not claimed to be
    # the effect's onset — only that the arms differ, most around here.)
    assert best["start_ms"] >= 150 and best["end_ms"] <= 950
    assert best["start_ms"] <= 400 and best["end_ms"] >= 700
    assert best["sign"] == "a>b"


def test_on_null_data_the_window_test_errs_about_alpha_of_the_time():
    """100 null cohorts at alpha .05: expect ~5 rejections; 99% binomial
    upper bound is 11. More would mean the test is anticonservative."""
    rejections = 0
    for seed in range(100):
        r = run(cohort(8, 8, seed=seed, epochs=1), n_permutations=1000, seed=seed, cluster=None)
        rejections += r["window"]["p"] < 0.05
    assert rejections <= 11


def test_on_null_data_the_cluster_test_controls_the_whole_time_course():
    rejections = 0
    for seed in range(60):
        r = run(cohort(8, 8, seed=1000 + seed, epochs=1), n_permutations=500, seed=seed)
        rejections += any(c["significant"] for c in r["cluster"]["clusters"])
    # Family-wise over ~40 time points, still ~alpha: 60 runs, 99% bound 8.
    assert rejections <= 8


def test_the_bootstrap_interval_covers_the_true_difference():
    covered = 0
    for seed in range(150):
        rng = np.random.default_rng(seed)
        out = {**{f"a{i}": ("A", [np.full(len(GRID), rng.normal(1.0, 1.0))]) for i in range(15)},
               **{f"b{i}": ("B", [np.full(len(GRID), rng.normal(0.0, 1.0))]) for i in range(15)}}
        r = run(rows_for(out), n_permutations=1000, seed=seed, cluster=None)
        lo, hi = r["window"]["ci"]
        covered += lo <= 1.0 <= hi
    assert covered / 150 >= 0.88


def test_the_same_seed_gives_the_same_numbers():
    rows = cohort(6, 6, effect=0.8)
    a, b = run(rows), run(rows)
    assert a["window"] == b["window"] and a["cluster"] == b["cluster"]
    assert run(rows, seed=8)["window"]["ci"] != a["window"]["ci"]


def test_participants_are_weighted_equally_whatever_their_epoch_count():
    """Ten epochs from one person and one from another is two people, not eleven."""
    rows = rows_for({"p1": ("A", [np.full(len(GRID), 10.0)] * 10),
                     "p2": ("A", [np.full(len(GRID), 0.0)])})
    pooled = pooled_mean(participant_curves(rows, "c"))
    assert pooled[0]["mean"] == pytest.approx(5.0)   # not (100 + 0) / 11
    assert pooled[0]["n"] == 2


def test_self_test_sessions_are_not_one_person():
    rows = rows_for({"anonymous": ("A", [np.zeros(len(GRID))])})
    rows += [{**r, "session_id": "other"} for r in rows]
    assert len(participant_curves(rows, "c").by_participant) == 2


def test_a_participant_in_both_arms_is_refused():
    rows = rows_for({"p1": ("A", [np.zeros(len(GRID))])})
    rows += [{**r, "condition": "B", "session_id": "s2"} for r in rows]
    c = participant_curves(rows, "c")
    assert "p1" not in c.by_participant
    assert c.refusals[0]["reason"] == "mixed_arm_participant"


def test_too_few_participants_are_refused_not_reported():
    r = run(cohort(MIN_PER_ARM - 1, 5))
    assert r["refusal"]["reason"] == "too_few_per_arm"


def test_a_design_that_cannot_reach_alpha_is_refused_by_arithmetic():
    """3 vs 3: 20 arrangements, so the smallest two-sided p is 0.10."""
    assert smallest_possible_p(3, 3, "two") == pytest.approx(0.1)
    r = run(cohort(3, 3, effect=5))
    assert r["refusal"]["reason"] == "underpowered_by_construction"
    assert run(cohort(3, 3, effect=5), tail="greater")["refusal"] is None  # 1/20 = .05


def test_no_conditions_is_refused():
    rows = [{**r, "condition": None} for r in cohort(5, 5)]
    assert run(rows)["refusal"]["reason"] == "no_conditions"


def test_small_designs_are_enumerated_exactly():
    r = run(cohort(4, 5, effect=3), n_permutations=1000)
    assert r["window"]["exact"] and r["window"]["arrangements"] == math.comb(9, 4)
    # An exact p is a count over the arrangements.
    assert (r["window"]["p"] * math.comb(9, 4)) == pytest.approx(round(r["window"]["p"] * math.comb(9, 4)))


def test_holm_steps_down():
    assert holm([0.01, 0.04, None, 0.03]) == pytest.approx([0.03, 0.06, None, 0.06])


def test_hedges_g_matches_its_definition():
    a, b = np.array([2.0, 3.0, 4.0, 5.0]), np.array([1.0, 2.0, 3.0, 4.0])
    sp = math.sqrt((3 * np.var(a, ddof=1) + 3 * np.var(b, ddof=1)) / 6)
    assert hedges_g(a, b) == pytest.approx((1.0 / sp) * (1 - 3 / (4 * 8 - 9)))


def test_every_contrast_in_a_plan_is_corrected_together():
    rows = cohort(8, 8, effect=1.0)
    plan = {"contrasts": [contrast(name="one", cluster=None), contrast(name="two", window_ms=[-400, -100],
                                                                        cluster=None)]}
    out = run_contrasts(plan, {"e": rows})
    ps = [r["window"]["p"] for r in out]
    assert [r["window"]["p_holm"] for r in out] == pytest.approx(holm(ps))

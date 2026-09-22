"""Tests for scoring AU engines against posed movements.

Synthetic sessions with known answers: one engine that responds to exactly the
requested units, one that is blind to one of them, one that responds to
everything. The scoring has to tell those three apart, and has to refuse when
there is nothing to score.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from expression_scoring import (
    HOLD_ONSET_SKIP_MS,
    MIN_TARGET_TRIALS,
    auc,
    score_session,
    summarise,
    trials_from_events,
)

PLAN = [("smile", [6, 12, 25]), ("brow_raise", [1, 2]), ("jaw_drop", [25, 26]),
        ("brow_lower", [4])] * 2
READY, HOLD, RELAX = 2500.0, 4000.0, 3000.0


def session(plan=PLAN, t0=10_000.0, aligned=True):
    events, spans, t = [], [], t0
    for i, (expr, aus) in enumerate(plan):
        sid = f"expr_{i + 1:02d}_{expr}"
        meta = {"expression": expr, "target_aus": aus}
        on_p, on_h = t, t + READY
        off_h, off_p = on_h + HOLD, on_h + HOLD + RELAX
        events.append(dict(event_type="expression_prompt", stimulus_id=sid,
                           onset_master_ts=on_p if aligned else None, offset_master_ts=off_p,
                           metadata=json.dumps(meta)))
        events.append(dict(event_type="expression_hold", stimulus_id=sid,
                           onset_master_ts=on_h if aligned else None, offset_master_ts=off_h,
                           metadata=json.dumps(meta)))
        spans.append((on_h, off_h, set(aus)))
        t = off_p
    return events, spans, t


def signals(spans, t_end, source, respond, aus=(1, 2, 4, 6, 12, 25, 26), rate_hz=2.0, seed=0):
    """`respond(au, requested) -> level during a hold`; neutral is ~0.1."""
    rng = np.random.default_rng(seed)
    rows = []
    for ts in np.arange(0.0, t_end, 1000.0 / rate_hz):
        active = next((s for s in spans if s[0] + 600 <= ts <= s[1]), None)
        for au in aus:
            level = 0.1 if active is None else respond(au, au in active[2])
            rows.append(dict(source=source, channel=f"au.AU{au:02d}", master_ts=float(ts),
                             value=float(np.clip(level + rng.normal(0, 0.02), 0, 1))))
    return rows


def perfect(au, requested):
    return 0.8 if requested else 0.1


def blind_to_au4(au, requested):
    return 0.1 if au == 4 else perfect(au, requested)


def fires_on_everything(au, requested):
    return 0.8


# ---------------------------------------------------------------------------

def test_auc_is_the_probability_a_positive_outranks_a_negative():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 2], [1, 2]) == 0.5
    assert auc([], [1]) is None


def test_trials_pair_prompt_and_hold_and_skip_the_reaction_time():
    events, _, _ = session()
    trials = trials_from_events(events)
    assert len(trials) == len(PLAN)
    t = trials[0]
    assert t.ready[1] - t.ready[0] == READY
    assert t.hold[1] - t.hold[0] == HOLD - HOLD_ONSET_SKIP_MS
    assert t.target_aus == (6, 12, 25)


def test_unaligned_events_are_dropped_not_scored_on_the_wrong_clock():
    events, _, _ = session(aligned=False)
    assert trials_from_events(events) == []


def test_a_perfect_engine_scores_full_sensitivity_on_every_requested_au():
    events, spans, t_end = session()
    rep = score_session(signals(spans, t_end, "e@1+x", perfect), events)
    ok = {s.au: s for s in rep.scores if s.verdict == "ok"}
    assert set(ok) == {"AU01", "AU02", "AU04", "AU06", "AU12", "AU25", "AU26"}
    assert all(s.sensitivity_auc == 1.0 for s in ok.values())


def test_an_engine_blind_to_one_unit_is_caught_on_that_unit_only():
    events, spans, t_end = session()
    rep = score_session(signals(spans, t_end, "blind@1+x", blind_to_au4), events)
    by = {s.au: s for s in rep.scores}
    assert by["AU04"].sensitivity_auc < 0.8
    assert by["AU12"].sensitivity_auc == 1.0


def test_an_engine_that_fires_on_everything_is_sensitive_but_not_specific():
    """Why the two are reported apart: this engine would look perfect on
    sensitivity alone."""
    events, spans, t_end = session()
    rep = score_session(signals(spans, t_end, "loud@1+x", fires_on_everything), events)
    au12 = next(s for s in rep.scores if s.au == "AU12")
    assert au12.sensitivity_auc == 1.0
    # At identical levels the ranking is decided by noise, so with 2 target
    # trials against 6 it can land anywhere — the claim is only that it does
    # not look like discrimination. Checked over seeds so one lucky draw
    # cannot pass or fail it.
    specs = [next(s for s in score_session(
        signals(spans, t_end, "loud@1+x", fires_on_everything, seed=k), events).scores
        if s.au == "AU12").specificity_auc for k in range(20)]
    assert 0.25 < float(np.mean(specs)) < 0.75


def test_too_few_target_trials_is_refused_not_scored():
    plan = [("smile", [12]), ("brow_raise", [1, 2]), ("brow_raise", [1, 2])]
    events, spans, t_end = session(plan)
    rep = score_session(signals(spans, t_end, "e@1+x", perfect), events)
    au12 = next(s for s in rep.scores if s.au == "AU12")
    assert au12.verdict == "too_few_trials"
    assert au12.sensitivity_auc is None
    assert str(MIN_TARGET_TRIALS) in au12.detail


def test_a_session_without_expression_trials_is_refused_with_a_reason():
    rep = score_session([], [dict(event_type="fixation", onset_master_ts=0.0)])
    assert rep.n_trials == 0
    assert "expression_prompts" in rep.refusal


def test_a_session_without_au_output_says_to_run_the_au_engines():
    events, _, _ = session()
    rep = score_session([], events)
    assert "--aus" in rep.refusal


def test_an_au_an_engine_does_not_emit_is_no_data_not_zero():
    events, spans, t_end = session()
    rows = signals(spans, t_end, "e@1+x", perfect, aus=(12,))
    rep = score_session(rows, events)
    au4 = next(s for s in rep.scores if s.au == "AU04")
    assert au4.verdict == "no_data"


def test_two_engines_that_both_track_the_movement_agree_on_holds():
    events, spans, t_end = session()
    rows = (signals(spans, t_end, "a@1+x", perfect, seed=1)
            + signals(spans, t_end, "b@1+x", perfect, seed=2))
    rep = score_session(rows, events)
    au12 = next(a for a in rep.agreement if a.au == "AU12")
    assert au12.verdict == "ok"
    assert au12.r > 0.9
    assert au12.n_trials == len(PLAN)


def test_agreement_with_a_blind_engine_is_low_on_the_unit_it_misses():
    events, spans, t_end = session()
    rows = (signals(spans, t_end, "a@1+x", perfect, seed=1)
            + signals(spans, t_end, "b@1+x", blind_to_au4, seed=2))
    rep = score_session(rows, events)
    au4 = next(a for a in rep.agreement if a.au == "AU04")
    assert au4.r is None or au4.r < 0.5


def test_summary_reports_each_engine_separately():
    events, spans, t_end = session()
    rows = (signals(spans, t_end, "a@1+x", perfect, seed=1)
            + signals(spans, t_end, "b@1+x", blind_to_au4, seed=2))
    s = summarise(score_session(rows, events))
    assert s["a@1+x"]["median_sensitivity_auc"] == 1.0
    assert s["b@1+x"]["n_aus_scored"] == 7


def test_report_serialises():
    events, spans, t_end = session()
    d = score_session(signals(spans, t_end, "e@1+x", perfect), events).to_dict()
    json.dumps(d)
    assert d["hold_onset_skip_ms"] == HOLD_ONSET_SKIP_MS

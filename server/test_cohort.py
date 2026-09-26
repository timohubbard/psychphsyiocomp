"""Cohort selection and epochs, on sessions written through the real writer."""

from __future__ import annotations

import numpy as np
import pytest

from alignment import ClockSolution
from cohort import EpochSpec, analysis_hash, epochs, resample, select
from engine_contract import Chunk, EventRow, QualityRow, SignalRow
from study import content_hash
from tables import CanonicalWriter, SessionContext

MASTER = ClockSolution(clock_id="performance.now", offset_ms=0.0, rate=1.0,
                       uncertainty_ms=0.0, n_anchors=0)

STUDY = {
    "study_id": "c1", "name": "Cohort", "version": "1.0.0",
    "disclosure": {"retention_days": 30, "secondary_use": "Team only.", "contact": "a@b.ac.uk"},
    "consent_tiers": ["features_only"], "modalities": ["face"],
    "analysis": {
        "exclusions": [{"metric": "achieved_fps", "min": 5},
                       {"metric": "face_detect_rate", "min": 0.5}],
    },
}
H = content_hash(STUDY)


def session(out, sid, *, audience="participants", chash=H, fps=30.0, face_rate=0.9,
            condition=None, signals=(), events=()):
    w = CanonicalWriter(out, SessionContext(sid, f"p_{sid}", "c1"))
    w.set_session_metadata({"study": {"study_id": "c1", "study_content_hash": chash,
                                      "audience": audience},
                            "achieved_fps": fps, "condition": condition})
    quality = () if face_rate is None else (QualityRow(
        stream="face", metric="face_detect_rate", window_start_native_ts=0.0,
        window_end_native_ts=1000.0, value=face_rate),)
    # `signals` is rows, or {source: rows} for a channel from several sources:
    # the writer stamps the source per add_chunks call, not per row.
    by_source = signals if isinstance(signals, dict) else {"test@1": list(signals)}
    for i, (src, rows) in enumerate(by_source.items()):
        w.add_chunks([Chunk(signals=tuple(rows), events=tuple(events) if i == 0 else (),
                            quality=quality if i == 0 else ())],
                     source=src, params={}, solution=MASTER)
    if not by_source:
        w.add_chunks([Chunk(events=tuple(events), quality=quality)],
                     source="test@1", params={}, solution=MASTER)
    w.close()


def sig(channel, ts, vs):
    return [SignalRow(stream="face", channel=channel, native_clock_id="performance.now",
                      native_ts=float(t), value=float(v), reliability_tier="high")
            for t, v in zip(ts, vs)]


def ev(onset, event_type="stimulus", stimulus_id="x"):
    return EventRow(event_type=event_type, native_clock_id="performance.now",
                    onset_native_ts=onset, offset_native_ts=onset + 1000.0,
                    stimulus_id=stimulus_id, metadata=None)


def test_the_funnel_names_every_exclusion_in_order(tmp_path):
    session(tmp_path, "ok")
    session(tmp_path, "selftest", audience="developer")
    session(tmp_path, "edited", chash="0" * 16)
    session(tmp_path, "slow", fps=3.0)
    session(tmp_path, "unmeasured", face_rate=None)

    c = select(tmp_path, STUDY)
    assert [r["session_id"] for r in c.included] == ["ok"]
    assert [s.remaining for s in c.funnel] == [5, 4, 3, 2, 1]
    reasons = {sid: why for s in c.funnel for sid, why in s.excluded}
    assert reasons["selftest"] == "audience developer"
    assert reasons["edited"].startswith("protocol 0000")
    assert reasons["slow"].startswith("failed: achieved_fps 3")
    assert reasons["unmeasured"] == "not_measured: face_detect_rate", \
        "a criterion nobody measured is not a criterion met"


def test_self_tests_and_edited_protocols_only_on_request(tmp_path):
    session(tmp_path, "selftest", audience="developer")
    session(tmp_path, "edited", chash="0" * 16)
    c = select(tmp_path, STUDY, include_developer=True, allow_mixed=True)
    assert sorted(r["session_id"] for r in c.included) == ["edited", "selftest"]


def test_the_analysis_plan_has_its_own_hash_outside_the_protocol(tmp_path):
    edited = {**STUDY, "analysis": {"exclusions": [{"metric": "achieved_fps", "min": 10}]}}
    assert content_hash(edited) == H
    assert analysis_hash(edited) != analysis_hash(STUDY)


def test_resample_interpolates_and_refuses_to_bridge_gaps():
    ts = np.array([0.0, 100.0, 1000.0])
    vs = np.array([0.0, 1.0, 10.0])
    out = resample(ts, vs, np.array([50.0, 100.0, 500.0, 2000.0]), max_gap_ms=250)
    assert out[0] == pytest.approx(0.5)
    assert out[1] == pytest.approx(1.0)
    assert np.isnan(out[2]), "a 900 ms gap is not filled in"
    assert np.isnan(out[3]), "nothing after the last sample"


def _linear_session(tmp_path, onset=5000.0, **kw):
    ts = np.arange(0, 10000, 1000 / 30)
    session(tmp_path, "s1", signals=sig("blendshape.a", ts, ts / 1000.0), events=[ev(onset)], **kw)


def test_epochs_are_baseline_corrected_exactly(tmp_path):
    _linear_session(tmp_path)
    spec = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"],
                     pre_ms=500, post_ms=1000, baseline_ms=(-500, 0), resample_hz=30)
    rows, refusals = epochs(tmp_path, select(tmp_path, STUDY).included, spec)
    assert refusals == []
    rel = np.array([r["t_ms"] for r in rows])
    base = rel[(rel >= -500) & (rel <= 0)].mean()
    for r in rows:
        assert r["value"] == pytest.approx((5000 + r["t_ms"]) / 1000, abs=1e-9)
        assert r["value_bc"] == pytest.approx((r["t_ms"] - base) / 1000, abs=1e-9)
    assert {r["condition"] for r in rows} == {None}


def test_an_epoch_running_past_the_data_is_refused_for_coverage(tmp_path):
    _linear_session(tmp_path, onset=9800.0)
    spec = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"],
                     pre_ms=200, post_ms=3000, baseline_ms=(-200, 0))
    rows, refusals = epochs(tmp_path, select(tmp_path, STUDY).included, spec)
    assert rows == [] and refusals[0]["reason"] == "low_coverage"


def test_an_event_without_a_master_timestamp_is_refused_not_retimed(tmp_path):
    ts = np.arange(0, 10000, 1000 / 30)
    w = CanonicalWriter(tmp_path, SessionContext("s1", "p", "c1"))
    w.set_session_metadata({"study": {"study_id": "c1", "study_content_hash": H,
                                      "audience": "participants"}, "achieved_fps": 30.0})
    w.add_chunks([Chunk(signals=tuple(sig("blendshape.a", ts, ts)),
                        quality=(QualityRow(stream="face", metric="face_detect_rate",
                                            window_start_native_ts=0.0, window_end_native_ts=1.0,
                                            value=0.9),))],
                 source="test@1", params={}, solution=MASTER)
    unaligned = ClockSolution(clock_id="video_pts", offset_ms=0.0, n_anchors=0,
                              unaligned_reason="no anchors")
    w.add_chunks([Chunk(events=(ev(5000.0),))], source="runner", params={}, solution=unaligned)
    w.close()
    spec = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"],
                     pre_ms=200, post_ms=500)
    rows, refusals = epochs(tmp_path, select(tmp_path, STUDY).included, spec)
    assert rows == [] and refusals[0]["reason"] == "unaligned_event"


def test_a_channel_from_two_sources_must_be_told_which(tmp_path):
    ts = np.arange(0, 10000, 1000 / 30)
    session(tmp_path, "s1", signals={"a@1": sig("blendshape.a", ts, ts), "b@1": sig("blendshape.a", ts, ts)},
            events=[ev(5000.0)])
    ambiguous = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"],
                          pre_ms=200, post_ms=500)
    rows, refusals = epochs(tmp_path, select(tmp_path, STUDY).included, ambiguous)
    assert rows == [] and refusals[0]["reason"] == "ambiguous_source"

    chosen = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"],
                       pre_ms=200, post_ms=500, source="b@1")
    rows, refusals = epochs(tmp_path, select(tmp_path, STUDY).included, chosen)
    assert rows and {r["source"] for r in rows} == {"b@1"} and refusals == []


def test_the_condition_travels_with_each_epoch_row(tmp_path):
    ts = np.arange(0, 10000, 1000 / 30)
    session(tmp_path, "s1", condition="B", signals=sig("blendshape.a", ts, ts), events=[ev(5000.0)])
    spec = EpochSpec(name="e", event_type="stimulus", channels=["blendshape.a"], pre_ms=200, post_ms=500)
    rows, _ = epochs(tmp_path, select(tmp_path, STUDY).included, spec)
    assert {r["condition"] for r in rows} == {"B"}
